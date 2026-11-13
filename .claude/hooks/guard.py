"""Claude Code and Codex hooks enforcing AGENTS.md rules that need no judgement.

Usage: guard.py env|live|ruff|openspec [codex], with the hook payload on stdin.
Codex edits files with ``apply_patch``, whose ``tool_input.command`` is the patch
text, so the files it touches are read from the patch headers.
"""

from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# `.env` or `.env.bak` as a whole path component; `.env.example` stays readable.
ENV_FILE = re.compile(r"(?:^|[\s/'\"=<:])\.env(?:\.bak)?(?=$|[\s'\";|&)>])")
ENV_NAMES = {".env", ".env.bak"}
# Runs that read the live broker account or call a model.
LIVE_RUN = re.compile(
    r"\btradingagents\s+portfolio\s+live\b"
    r"|\btradingagents\s+backtest\b"
    r"|\btradingagents\s+market-report\b"
    r"|\btradingagents\b[^|;&]*--ticker\b"
)
# A shell chain or substitution hides a live run from Codex's prefix rules.
COMPOUND = re.compile(r"&&|\|\||[;|`]|\$\(")
# The programs and leading arguments .codex/rules/tradingagents.rules prompts for; keep in sync.
RULE_PROGRAMS = {"tradingagents", "./.venv/bin/tradingagents", ".venv/bin/tradingagents"}
RULE_PREFIXES = (["portfolio", "live"], ["backtest"], ["--ticker"], ["market-report"])
PATCH_FILE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$|^\*\*\* Move to: (.+)$", re.MULTILINE)
# A heredoc body is text handed to a program, not files the shell opens.
# ponytail: a heredoc piped into an interpreter is not inspected; the ban targets accidents, not evasion.
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n[ \t]*\2[ \t]*(?=\n|$)", re.DOTALL)
SHELLS = {"sh", "bash", "zsh"}
CODE_FLAGS = {"-c", "-e"}
ARCHIVE_STUB = "TBD - created by archiving change"


def _pre_tool(decision: str, reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": decision,
        "permissionDecisionReason": reason}}, ensure_ascii=False))


def _patch_files(payload: dict) -> list[str]:
    """The files an ``apply_patch`` call adds, updates, deletes or moves to."""
    command = (payload.get("tool_input") or {}).get("command", "")
    return [(a or b).strip() for a, b in PATCH_FILE.findall(command)]


def _tokens(command: str) -> list[str] | None:
    """Shell words with ``;&|<>()`` split off, or None when the command does not parse."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:
        return None


def _is_env_path(text: str) -> bool:
    # `--env-file=.env` and `host:.env` name the file after the separator.
    return any(Path(part).name in ENV_NAMES for part in re.split(r"[=:]", text))


def _shell_touches_env(command: str) -> bool:
    """Whether a shell command names an env file as a word, not just mentions it in text.

    A commit message or a heredoc that says ".env" opens nothing. Code passed to
    a shell with ``-c`` is a command of its own; code passed to another
    interpreter with ``-c``/``-e`` is searched for the file name.
    """
    tokens = _tokens(HEREDOC.sub("", command))
    if tokens is None:
        return bool(ENV_FILE.search(command))   # unparseable: judge the raw text
    for index, token in enumerate(tokens):
        if _is_env_path(token):
            return True
        if index >= 2 and tokens[index - 1] in CODE_FLAGS:
            if Path(tokens[index - 2]).name in SHELLS:
                if _shell_touches_env(token):
                    return True
            elif ENV_FILE.search(token):
                return True
    return False


def env(payload: dict) -> None:
    tool_input = payload.get("tool_input") or {}
    if payload.get("tool_name") == "apply_patch":
        touched = any(_is_env_path(path) for path in _patch_files(payload))
    elif payload.get("tool_name") == "Bash":
        touched = _shell_touches_env(tool_input.get("command", ""))
    else:
        touched = _is_env_path(tool_input.get("file_path") or tool_input.get("path") or "")
    if touched:
        _pre_tool("deny", "AGENTS.md: .env / .env.bak 값은 읽거나 수정하지 않습니다. "
                          "설정 키 이름이 필요하면 .env.example을 보세요.")


def _rules_will_prompt(command: str) -> bool:
    """Whether .codex/rules matches this command, so Codex itself asks the user."""
    tokens = None if COMPOUND.search(command) else _tokens(command)
    return bool(tokens) and tokens[0] in RULE_PROGRAMS and any(
        tokens[1:1 + len(prefix)] == prefix for prefix in RULE_PREFIXES)


def live(payload: dict, codex: bool = False) -> None:
    command = (payload.get("tool_input") or {}).get("command", "")
    if not LIVE_RUN.search(command):
        return
    if not codex:
        _pre_tool("ask", "AGENTS.md: 실계좌 조회·실제 LLM 분석은 사용자가 명시적으로 요청한 경우에만 실행합니다.")
    elif not _rules_will_prompt(command):
        # Codex hooks cannot ask, and its prefix rules only see a plain command in a known shape.
        _pre_tool("deny", "실계좌·LLM 실행은 사용자 확인을 받아야 합니다. 다른 명령과 묶지 말고, 환경변수 접두사 "
                          "없이 `tradingagents portfolio live ...`, `tradingagents backtest ...`, "
                          "`tradingagents --ticker ...`(--ticker를 첫 인자로) 형태의 단독 명령으로 다시 실행하세요.")


def ruff(payload: dict) -> None:
    cwd = Path(payload.get("cwd") or ROOT)
    edited = (_patch_files(payload) if payload.get("tool_name") == "apply_patch"
              else [(payload.get("tool_input") or {}).get("file_path", "")])
    paths = [str(cwd / p) for p in edited if p.endswith(".py") and (cwd / p).is_file()]
    # A fresh worktree has no .venv of its own; fall back to ruff on PATH, else skip.
    venv_ruff = ROOT / ".venv/bin/ruff"
    ruff_bin = str(venv_ruff) if venv_ruff.is_file() else shutil.which("ruff")
    if not paths or not ruff_bin:
        return
    result = subprocess.run([ruff_bin, "check", *paths],
                            cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        print(json.dumps({"decision": "block", "reason": f"ruff check 실패:\n{result.stdout.strip()}"},
                         ensure_ascii=False))


def openspec(payload: dict) -> None:
    if payload.get("stop_hook_active"):
        return  # already blocked once this turn; do not loop
    problems = [f"{p.relative_to(ROOT)}: Purpose가 아카이브 기본 문구(TBD)입니다"
                for p in sorted((ROOT / "openspec/specs").glob("*/spec.md"))
                if ARCHIVE_STUB in p.read_text(encoding="utf-8")]
    changes = [p.name for p in sorted((ROOT / "openspec/changes").iterdir())
               if p.is_dir() and p.name != "archive"]
    for name in changes:
        result = subprocess.run(["npx", "--offline", "@fission-ai/openspec", "validate", name, "--strict"],
                                cwd=ROOT, capture_output=True, text=True)
        if result.returncode:
            problems.append(f"openspec/changes/{name}: 검증 실패\n{(result.stdout + result.stderr).strip()}")
    if problems:
        print(json.dumps({"decision": "block", "reason": "\n".join(problems)}, ensure_ascii=False))


def network(payload: dict) -> None:
    """Run the safe API doctor once when a new Codex session starts."""
    candidates = (
        ROOT / ".venv/bin/tradingagents",
        ROOT / ".venv/Scripts/tradingagents.exe",
    )
    executable = next((path for path in candidates if path.is_file()), None)
    installed_command = shutil.which("tradingagents")
    command = [str(executable)] if executable else ([installed_command] if installed_command else None)
    if command is None:
        python_candidates = (ROOT / ".venv/bin/python", ROOT / ".venv/Scripts/python.exe")
        python = next((path for path in python_candidates if path.is_file()), None)
        command = [str(python or sys.executable), "-m", "cli.main"]

    def report(message: str, status: str | None = None) -> None:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": message,
            },
        }
        if status:
            output["systemMessage"] = status
        print(json.dumps(output, ensure_ascii=False))

    try:
        result = subprocess.run(
            [*command, "doctor"], cwd=ROOT, capture_output=True, text=True, timeout=70,
        )
    except (OSError, subprocess.TimeoutExpired):
        report(
            "워커 시작 API 사전 진단을 완료하지 못했습니다. "
            "필요하면 `tradingagents doctor`를 직접 실행하세요.",
            "API 사전 진단 실행 실패",
        )
        return

    details = result.stdout.strip()
    if result.returncode != 0 or not details:
        report(
            "워커 시작 API 사전 진단을 완료하지 못했습니다. "
            "필요하면 `tradingagents doctor`를 직접 실행하세요.",
            "API 사전 진단 실행 실패",
        )
        return

    network_issue = any("도달 실패:" in line for line in details.splitlines())
    if network_issue:
        try:
            policy = subprocess.run(
                [*command, "network-policy", "--format", "json"],
                cwd=ROOT, capture_output=True, text=True, timeout=10,
            )
            if policy.returncode == 0 and policy.stdout.strip():
                details += "\n\n실행 호스트에 전달할 제한형 네트워크 정책:\n" + policy.stdout.strip()
            else:
                details += "\n\n정책 JSON을 내보내지 못했습니다. "
                "`tradingagents network-policy --format json`을 실행하세요."
        except (OSError, subprocess.TimeoutExpired):
            details += "\n\n제한형 정책 내보내기를 완료하지 못했습니다. "
            "`tradingagents network-policy --format json`을 실행하세요."
        details += "\n\n네트워크 정책은 Orca 실행 호스트에서 적용한 뒤 이 워커에서 다시 확인해야 합니다."
        status = "API 사전 진단에서 도달 실패를 찾음"
    else:
        details = "자동 API 사전 진단 통과.\n\n" + details

    report("워커 시작 시 자동 실행한 `tradingagents doctor` 결과:\n\n" + details, status if network_issue else None)


if __name__ == "__main__":
    mode, payload = sys.argv[1], json.load(sys.stdin)
    if mode == "live":
        live(payload, codex=sys.argv[2:] == ["codex"])
    else:
        {"env": env, "network": network, "ruff": ruff, "openspec": openspec}[mode](payload)
