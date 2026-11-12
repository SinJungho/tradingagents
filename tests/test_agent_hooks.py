"""Agent hooks (.claude/hooks/guard.py) answer Claude Code and Codex payloads alike."""

from __future__ import annotations

import importlib.util
import json
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

GUARD = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "guard.py"


def _run(mode: str, payload: dict, *extra: str) -> str | None:
    out = subprocess.run([sys.executable, str(GUARD), mode, *extra], input=json.dumps(payload),
                         capture_output=True, text=True, check=True).stdout.strip()
    if not out:
        return None
    data = json.loads(out)
    return data.get("hookSpecificOutput", {}).get("permissionDecision") or data.get("decision")


def _bash(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _patch(*headers: str, body: str = "") -> dict:
    text = "*** Begin Patch\n" + "\n".join(headers) + f"\n{body}\n*** End Patch"
    return {"tool_name": "apply_patch", "tool_input": {"command": text}}


@pytest.mark.unit
@pytest.mark.parametrize("payload, expected", [
    ({"tool_name": "Read", "tool_input": {"file_path": "/repo/.env"}}, "deny"),
    ({"tool_name": "Read", "tool_input": {"file_path": "/repo/.env.bak"}}, "deny"),
    ({"tool_name": "Read", "tool_input": {"file_path": "/repo/.env.example"}}, None),
    (_bash("cat .env | head"), "deny"),
    (_bash("cat .env|head"), "deny"),
    (_bash("source ./.env && run"), "deny"),
    (_bash("docker run --env-file=.env image"), "deny"),
    (_bash("cp .env.bak /tmp/x"), "deny"),
    (_bash("bash -c 'cat .env'"), "deny"),
    (_bash("python3 -c \"print(open('.env').read())\""), "deny"),
    (_bash("grep KEY .env.example"), None),
    # Text that only mentions the file opens nothing.
    (_bash('git commit -m "feat: .env 접근 차단"'), None),
    (_bash("python3 - <<'EOF'\nNAMES = ('.env', '.env.bak')\nEOF"), None),
    (_bash("cat > notes.md <<EOF\ncopy .env.example to .env\nEOF\nwc -l notes.md"), None),
    (_patch("*** Update File: .env"), "deny"),
    (_patch("*** Add File: config/.env.bak"), "deny"),
    # A patch whose text merely mentions the file is not an edit of it.
    (_patch("*** Update File: README.md", body="+copy .env.example to .env"), None),
])
def test_env_files_are_off_limits(payload, expected):
    assert _run("env", payload) == expected


@pytest.mark.unit
@pytest.mark.parametrize("command, claude, codex", [
    ("tradingagents portfolio live --symbol TQQQ", "ask", None),       # Codex: .codex/rules prompts
    ("cd /repo && tradingagents portfolio live", "ask", "deny"),       # hidden from the rules
    ("./.venv/bin/tradingagents backtest NVDA --start 2025-01-01 --end 2025-02-01", "ask", None),
    ("tradingagents --ticker NVDA --date 2026-11-10 | tee out", "ask", "deny"),
    ("tradingagents --ticker NVDA --date 2026-11-10", "ask", None),
    # Shapes the Codex prefix rules cannot see: a flag before --ticker, an absolute path, an env prefix.
    ("tradingagents --checkpoint --ticker NVDA", "ask", "deny"),
    ("/opt/repo/.venv/bin/tradingagents portfolio live", "ask", "deny"),
    ("DEBUG=1 tradingagents portfolio live", "ask", "deny"),
    ("tradingagents portfolio demo", None, None),
    ("tradingagents style-backtest NVDA --start 2025-01-01 --end 2025-02-01", None, None),
])
def test_live_runs_need_the_user(command, claude, codex):
    assert _run("live", _bash(command)) == claude
    assert _run("live", _bash(command), "codex") == codex


@pytest.mark.unit
@pytest.mark.skipif(not (GUARD.parents[2] / ".venv/bin/ruff").is_file() and not shutil.which("ruff"),
                    reason="no ruff in this checkout or on PATH")
def test_ruff_reads_edited_python_from_either_payload(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("import os\n", encoding="utf-8")
    good = tmp_path / "good.py"
    good.write_text("x = 1\n", encoding="utf-8")

    assert _run("ruff", {"tool_name": "Edit", "tool_input": {"file_path": str(bad)}}) == "block"
    assert _run("ruff", {**_patch("*** Update File: bad.py"), "cwd": str(tmp_path)}) == "block"
    assert _run("ruff", {**_patch("*** Update File: good.py"), "cwd": str(tmp_path)}) is None
    assert _run("ruff", {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "notes.md")}}) is None


@pytest.mark.unit
def test_stop_does_not_block_twice_in_one_turn():
    assert _run("openspec", {"stop_hook_active": True}) is None


def _load_guard():
    spec = importlib.util.spec_from_file_location("agent_guard", GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _block_network(monkeypatch):
    def unexpected_network(*args, **kwargs):
        pytest.fail("SessionStart test attempted live network access")

    monkeypatch.setattr(socket, "create_connection", unexpected_network)
    monkeypatch.setattr(socket, "getaddrinfo", unexpected_network)
    monkeypatch.setattr(socket.socket, "connect", unexpected_network)
    monkeypatch.setattr(socket.socket, "connect_ex", unexpected_network)


def _run_network_hook(monkeypatch, tmp_path, capsys, results, *, cli_installed=True):
    _block_network(monkeypatch)
    guard = _load_guard()
    guard.ROOT = tmp_path
    executable = tmp_path / ".venv" / "bin" / "tradingagents"
    if cli_installed:
        executable.parent.mkdir(parents=True)
        executable.touch()

    monkeypatch.setattr(guard.shutil, "which", lambda _: None)
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        result = results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return subprocess.CompletedProcess(command, result[0], result[1], result[2])

    monkeypatch.setattr(guard.subprocess, "run", fake_run)
    guard.network({})
    output = json.loads(capsys.readouterr().out)
    return output, calls, executable


def _assert_session_continues(output):
    assert output["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "permissionDecision" not in output["hookSpecificOutput"]
    assert "decision" not in output


@pytest.mark.unit
def test_session_start_network_diagnostic_success_is_safe_and_non_blocking(
    monkeypatch, tmp_path, capsys,
):
    secret = "SYNTHETIC_SECRET_CANARY"
    auth_response = '{"access_token":"SYNTHETIC_AUTH_RESPONSE_CANARY"}'
    output, calls, executable = _run_network_hook(
        monkeypatch,
        tmp_path,
        capsys,
        [(0, "API 도달 가능: synthetic fixture", f"{secret} {auth_response}")],
    )

    _assert_session_continues(output)
    assert output["hookSpecificOutput"]["additionalContext"].startswith(
        "워커 시작 시 자동 실행한 `tradingagents doctor` 결과:"
    )
    assert "API 도달 가능: synthetic fixture" in output["hookSpecificOutput"]["additionalContext"]
    assert secret not in json.dumps(output)
    assert "SYNTHETIC_AUTH_RESPONSE_CANARY" not in json.dumps(output)
    assert calls[0][0] == [str(executable), "doctor"]
    assert len(calls) == 1


@pytest.mark.unit
def test_session_start_network_failure_emits_policy_and_does_not_leak_auth_output(
    monkeypatch, tmp_path, capsys,
):
    secret = "SYNTHETIC_SECRET_CANARY"
    auth_response = '{"access_token":"SYNTHETIC_AUTH_RESPONSE_CANARY"}'
    policy = '{"version":1,"allow":["api.example.test:443"]}'
    output, calls, executable = _run_network_hook(
        monkeypatch,
        tmp_path,
        capsys,
        [
            (0, "Alpha Vantage 도달 실패: synthetic timeout", f"{secret} {auth_response}"),
            (0, policy, ""),
        ],
    )

    _assert_session_continues(output)
    assert output["systemMessage"] == "API 사전 진단에서 도달 실패를 찾음"
    context = output["hookSpecificOutput"]["additionalContext"]
    assert "Alpha Vantage 도달 실패: synthetic timeout" in context
    assert policy in context
    assert secret not in json.dumps(output)
    assert "SYNTHETIC_AUTH_RESPONSE_CANARY" not in json.dumps(output)
    assert calls[0][0] == [str(executable), "doctor"]
    assert calls[1][0] == [str(executable), "network-policy", "--format", "json"]


@pytest.mark.unit
def test_session_start_without_installed_cli_uses_python_fallback_and_continues(
    monkeypatch, tmp_path, capsys,
):
    secret = "SYNTHETIC_SECRET_CANARY"
    auth_response = '{"access_token":"SYNTHETIC_AUTH_RESPONSE_CANARY"}'
    output, calls, executable = _run_network_hook(
        monkeypatch,
        tmp_path,
        capsys,
        [(1, f"{secret} {auth_response}", f"{secret} {auth_response}")],
        cli_installed=False,
    )

    _assert_session_continues(output)
    assert output["systemMessage"] == "API 사전 진단 실행 실패"
    assert "진단을 완료하지 못했습니다" in output["hookSpecificOutput"]["additionalContext"]
    assert secret not in json.dumps(output)
    assert "SYNTHETIC_AUTH_RESPONSE_CANARY" not in json.dumps(output)
    assert calls[0][0] == [sys.executable, "-m", "cli.main", "doctor"]
    assert not executable.exists()


@pytest.mark.unit
def test_session_start_diagnostic_timeout_is_non_blocking_and_safe(
    monkeypatch, tmp_path, capsys,
):
    secret = "SYNTHETIC_SECRET_CANARY"
    auth_response = '{"access_token":"SYNTHETIC_AUTH_RESPONSE_CANARY"}'
    output, calls, executable = _run_network_hook(
        monkeypatch,
        tmp_path,
        capsys,
        [subprocess.TimeoutExpired(
            cmd="tradingagents doctor",
            timeout=70,
            output=f"{secret} {auth_response}",
            stderr=f"{secret} {auth_response}",
        )],
    )

    _assert_session_continues(output)
    assert output["systemMessage"] == "API 사전 진단 실행 실패"
    assert "진단을 완료하지 못했습니다" in output["hookSpecificOutput"]["additionalContext"]
    assert secret not in json.dumps(output)
    assert "SYNTHETIC_AUTH_RESPONSE_CANARY" not in json.dumps(output)
    assert calls[0][0] == [str(executable), "doctor"]
    assert calls[0][1]["timeout"] == 70
