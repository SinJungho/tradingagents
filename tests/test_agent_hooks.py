"""Agent hooks (.claude/hooks/guard.py) answer Claude Code and Codex payloads alike."""

from __future__ import annotations

import json
import shutil
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
