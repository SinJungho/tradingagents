"""Claude Code and Codex hooks enforcing AGENTS.md rules that need no judgement.

Usage: guard.py env|live|ruff|openspec [codex], with the hook payload on stdin.
Codex edits files with ``apply_patch``, whose ``tool_input.command`` is the patch
text, so the files it touches are read from the patch headers.
"""

from __future__ import annotations

import json
import re
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
    r"|\btradingagents\b[^|;&]*--ticker\b"
)
# A shell chain or substitution hides a live run from Codex's prefix rules.
COMPOUND = re.compile(r"&&|\|\||[;|`]|\$\(")
PATCH_FILE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$|^\*\*\* Move to: (.+)$", re.MULTILINE)
ARCHIVE_STUB = "TBD - created by archiving change"


def _pre_tool(decision: str, reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": decision,
        "permissionDecisionReason": reason}}, ensure_ascii=False))


def _targets(payload: dict) -> list[str]:
    """What the tool call reads or writes: a command, a path, or the files a patch touches."""
    tool_input = payload.get("tool_input") or {}
    if payload.get("tool_name") == "apply_patch":
        return [(a or b).strip() for a, b in PATCH_FILE.findall(tool_input.get("command", ""))]
    return [tool_input.get("command") or tool_input.get("file_path") or tool_input.get("path") or ""]


def env(payload: dict) -> None:
    if any(ENV_FILE.search(t) or Path(t).name in ENV_NAMES for t in _targets(payload)):
        _pre_tool("deny", "AGENTS.md: .env / .env.bak 값은 읽거나 수정하지 않습니다. "
                          "설정 키 이름이 필요하면 .env.example을 보세요.")


def live(payload: dict, codex: bool = False) -> None:
    command = (payload.get("tool_input") or {}).get("command", "")
    if not LIVE_RUN.search(command):
        return
    if not codex:
        _pre_tool("ask", "AGENTS.md: 실계좌 조회·실제 LLM 분석은 사용자가 명시적으로 요청한 경우에만 실행합니다.")
    elif COMPOUND.search(command):
        # Codex hooks cannot ask; .codex/rules prompts the user, but only for a plain command.
        _pre_tool("deny", "실계좌·LLM 실행은 사용자 확인을 받아야 합니다. 다른 명령과 묶지 말고 "
                          "`tradingagents ...` 단독 명령으로 다시 실행하세요.")


def ruff(payload: dict) -> None:
    cwd = Path(payload.get("cwd") or ROOT)
    paths = [str(cwd / p) for p in _targets(payload) if p.endswith(".py") and (cwd / p).is_file()]
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


if __name__ == "__main__":
    mode, payload = sys.argv[1], json.load(sys.stdin)
    if mode == "live":
        live(payload, codex=sys.argv[2:] == ["codex"])
    else:
        {"env": env, "ruff": ruff, "openspec": openspec}[mode](payload)
