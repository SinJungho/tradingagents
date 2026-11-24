"""Claude Code and Codex hooks enforcing AGENTS.md rules that need no judgement.

Usage: guard.py env|live|ruff|openspec [codex], with the hook payload on stdin.
Codex edits files with ``apply_patch``, whose ``tool_input.command`` is the patch
text, so the files it touches are read from the patch headers.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# `.env` or `.env.bak` as a whole path component; `.env.example` stays readable.
ENV_FILE = re.compile(r"(?:^|[\s/'\"=<:])\.env(?:\.bak)?(?=$|[\s'\";|&)>])")
ENV_NAMES = {".env", ".env.bak"}
# Runs that call a model. Read-only `portfolio live` is pre-authorized (AGENTS.md).
LIVE_RUN = re.compile(
    r"\btradingagents\s+backtest\b"
    r"|\btradingagents\s+market-report\b"
    r"|\btradingagents\b[^|;&]*--ticker\b"
)
# A shell chain or substitution hides a live run from Codex's prefix rules.
COMPOUND = re.compile(r"&&|\|\||[;|`]|\$\(")
# The programs and leading arguments .codex/rules/tradingagents.rules prompts for; keep in sync.
RULE_PROGRAMS = {"tradingagents", "./.venv/bin/tradingagents", ".venv/bin/tradingagents"}
RULE_PREFIXES = (["backtest"], ["--ticker"], ["market-report"])
PATCH_FILE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$|^\*\*\* Move to: (.+)$", re.MULTILINE)
# A heredoc body is text handed to a program, not files the shell opens.
# ponytail: a heredoc piped into an interpreter is not inspected; the ban targets accidents, not evasion.
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n[ \t]*\2[ \t]*(?=\n|$)", re.DOTALL)
SHELLS = {"sh", "bash", "zsh"}
CODE_FLAGS = {"-c", "-e"}
ARCHIVE_STUB = "TBD - created by archiving change"
CHART_DRAW_TOOL = re.compile(
    r"mcp__[^\s]*tratto[^\s]*__(?:draw_[^\s]*|remove_drawing|clear_drawings|undo_drawing|delete_saved_drawing)$",
    re.I,
)
CHART_BLOCKER = re.compile(
    r"미완료|완료하지 못|진행하지 못|수행하지 못|실행하지 못|접근할 수 없|"
    r"사용할 수 없|이용할 수 없|도구가 없|도구를 찾을 수 없|연결할 수 없|연결되지|"
    r"실패했|막혔|중단|unavailable|unable to|cannot connect", re.I
)


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
        _pre_tool("ask", "AGENTS.md: 실제 LLM 분석은 사용자가 명시적으로 요청한 경우에만 실행합니다.")
    elif not _rules_will_prompt(command):
        # Codex hooks cannot ask, and its prefix rules only see a plain command in a known shape.
        _pre_tool("deny", "LLM 실행은 사용자 확인을 받아야 합니다. 다른 명령과 묶지 말고, 환경변수 접두사 "
                          "없이 `tradingagents backtest ...`, `tradingagents market-report ...`, "
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


def _chart_state_path(payload: dict) -> Path | None:
    session = payload.get("session_id")
    turn = payload.get("turn_id", "session")
    if not session:
        return None
    key = hashlib.sha256(f"{session}:{turn}".encode()).hexdigest()
    directory = Path(os.environ.get(
        "TRADINGAGENTS_CHART_GATE_DIR", Path(tempfile.gettempdir()) / "tradingagents-chart-gate"
    ))
    return directory / f"{key}.json"


def _chart_state(payload: dict) -> tuple[Path | None, dict | None]:
    path = _chart_state_path(payload)
    if path is None or not path.is_file():
        return path, None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return path, None
    return path, state if state.get("turn_id") == payload.get("turn_id", "session") else None


def _save_chart_state(path: Path | None, state: dict) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _flatten_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_flatten_text(child) for child in value.values())
    if isinstance(value, (list, tuple)):
        return " ".join(_flatten_text(child) for child in value)
    return ""


def _successful_tool_response(response: object) -> bool:
    if isinstance(response, dict):
        if response.get("isError") is True or response.get("success") is False:
            return False
        return all(_successful_tool_response(value) for value in response.values())
    if isinstance(response, list):
        return all(_successful_tool_response(value) for value in response)
    return True


def _response_symbol(response: object) -> str | None:
    text = _flatten_text(response) + json.dumps(response, ensure_ascii=False, default=str)
    for pattern in (r'"symbol"\s*:\s*"([A-Z0-9.^=_-]+)"', r"\bSymbol:\s*([A-Z0-9.^=_-]+)"):
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(1).upper()
    return None


def _has_price_label(tool_input: dict) -> bool:
    values = [tool_input.get("label"), tool_input.get("text")]
    style = tool_input.get("style")
    if isinstance(style, dict):
        values.append(style.get("text"))
    return any(isinstance(value, str) and re.search(r"\$\s*\d+(?:\.\d+)?", value) for value in values)


def chart_prompt(payload: dict) -> None:
    prompt = str(payload.get("prompt", ""))
    drawing_request = re.search(
        r"(?:차트|종목|QQQ|TQQQ).{0,30}(?:드로잉|그려|표시|선 추가|라벨 추가)"
        r"|(?:드로잉|차트에 선|차트 선|라벨).{0,30}(?:추가|그려|진행|수정|표시)"
        r"|chart.{0,20}(?:draw|annotation|label)",
        prompt, re.I | re.S,
    )
    if not drawing_request:
        return
    path = _chart_state_path(payload)
    if path is None:
        return
    _save_chart_state(path, {
        "turn_id": payload.get("turn_id", "session"), "active": True, "guide": False,
        "summary": False, "before_read": False, "data_validated": False,
        "write_attempted": False, "write_done": False, "read_count": 0, "after_read": False,
        "drawings_check": False,
    })


def chart_pre(payload: dict) -> None:
    tool_name = str(payload.get("tool_name", ""))
    tool_input = payload.get("tool_input") or {}
    path, state = _chart_state(payload)
    if CHART_DRAW_TOOL.search(tool_name):
        if not state or not state.get("active"):
            _pre_tool("deny", "차트 쓰기 요청이 기록되지 않았습니다. 사용자 요청 범위와 차트 작업을 먼저 확인하세요.")
            return
        state["write_attempted"] = True
        missing = [name for name in ("guide", "summary", "before_read", "data_validated")
                   if not state.get(name)]
        if state.get("ticker_mismatch"):
            missing.append("ticker_mismatch")
        if not state.get("target_symbol"):
            missing.append("target_symbol")
        if missing:
            _save_chart_state(path, state)
            _pre_tool("deny", "Tratto 사전 단계가 빠졌습니다: " + ", ".join(missing) +
                      ". get_drawing_guide, get_chart_summary, read_drawings와 chart-check 성공 후 다시 호출하세요.")
            return
        requested_symbol = next((str(tool_input[key]).upper()
                                 for key in ("symbol", "ticker", "ticker_symbol") if tool_input.get(key)), None)
        if requested_symbol and requested_symbol != state["target_symbol"]:
            _save_chart_state(path, state)
            _pre_tool("deny", f"대상 종목 불일치: 차트 조회는 {state['target_symbol']}, "
                      f"드로잉 입력은 {requested_symbol}입니다.")
            return
        leaf = tool_name.rsplit("__", 1)[-1].lower()
        if leaf.startswith("draw_") and not _has_price_label(tool_input):
            _save_chart_state(path, state)
            _pre_tool("deny", "드로잉 입력에 가격이 표시되는 연결 라벨이 없습니다. '$643.28' 형식처럼 가격을 포함하세요.")
            return
        _save_chart_state(path, state)
        return

    if "cua_repl" in tool_name.lower():
        text = _flatten_text(tool_input)
        canvas_edit = state and state.get("active") and (
            re.search(r"\.click\s*\(\s*\[\s*-?\d", text)
            or re.search(r"\.drag\s*\(", text)
            or re.search(r"\.pressKey\s*\([^)]*['\"](?:Delete|BackSpace)['\"]", text, re.I)
        )
        if canvas_edit:
            _pre_tool("deny", "차트 작업 중 CUA 좌표 클릭·드래그·삭제키는 차트 쓰기를 우회할 수 있어 차단했습니다. "
                      "탭은 요소 인덱스로 선택하고, 차트 표시는 Tratto MCP를 사용하세요.")
            return
        direct_layout_edit = (
            re.search(r"finance\.yahoo\.com/chart/", text, re.I)
            and re.search(r"drawings|location\.hash|(?:^|\W)v0(?:\W|$)|#eyJ", text, re.I)
            and re.search(r"paste|typeText|setValue|location\.hash\s*=|goto\s*\(", text, re.I)
        )
        if direct_layout_edit:
            _pre_tool("deny", "Yahoo 차트의 저장 레이아웃·드로잉 상태 직접 편집은 금지합니다. "
                      "Tratto MCP를 사용하고, 사용할 수 없으면 변경을 중단해 미완료로 보고하세요.")


def chart_post(payload: dict) -> None:
    path, state = _chart_state(payload)
    if not state or not state.get("active"):
        return
    tool_name = str(payload.get("tool_name", ""))
    tool_input = payload.get("tool_input") or {}
    response = payload.get("tool_response")
    if not _successful_tool_response(response):
        return
    if "tratto" in tool_name.lower():
        leaf = tool_name.rsplit("__", 1)[-1].lower()
        if "get_drawing_guide" in leaf:
            state["guide"] = True
        elif "get_chart_summary" in leaf:
            state["summary"] = True
            state["target_symbol"] = _response_symbol(response)
        elif "read_drawings" in leaf:
            observed_symbol = _response_symbol(response)
            if observed_symbol and state.get("target_symbol") and observed_symbol != state["target_symbol"]:
                state["ticker_mismatch"] = True
            state["read_count"] = state.get("read_count", 0) + 1
            if state.get("write_done") or state["read_count"] > 1:
                state["after_read"] = True
            else:
                state["before_read"] = True
        elif leaf.startswith("draw_") or leaf in {
            "remove_drawing", "clear_drawings", "undo_drawing", "delete_saved_drawing",
        }:
            state["write_done"] = True
    if tool_name == "Bash":
        command = str(tool_input.get("command", ""))
        exit_code = response.get("exit_code") if isinstance(response, dict) else None
        if ("chart-check" in command and "chart-drawings-check" not in command
                and exit_code == 0):
            state["data_validated"] = True
        if "chart-drawings-check" in command:
            state["drawings_check"] = exit_code == 0
    _save_chart_state(path, state)


def chart_stop(payload: dict) -> None:
    if payload.get("stop_hook_active"):
        return
    path, state = _chart_state(payload)
    complete = state and all(state.get(key) for key in (
        "active", "guide", "summary", "before_read", "data_validated", "after_read", "drawings_check",
    ))
    if not state or not state.get("active") or complete:
        if path:
            path.unlink(missing_ok=True)
        return
    last_message = str(payload.get("last_assistant_message", ""))
    if CHART_BLOCKER.search(last_message):
        if path:
            path.unlink(missing_ok=True)
        return
    print(json.dumps({
        "decision": "block",
        "reason": "차트 드로잉 요청은 chart-drawings-check 성공 후에만 완료로 보고할 수 있습니다. "
                  "증거가 부족하면 확인 범위와 미완료 사유를 명시하세요.",
    }, ensure_ascii=False))


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
        details = "자동 API 사전 진단: 훅 프로세스 연결 검사 완료.\n\n" + details

    details += (
        "\n\n이 결과는 훅 프로세스의 진단이며 에이전트 샌드박스 정책 적용 증거가 아닙니다. "
        "프로젝트 .codex/config.toml의 신뢰·관리형 정책을 확인하고 일반 명령 경로에서 "
        "허용 연결과 미허용 도메인의 명시적 차단을 별도로 검증하세요. "
        "DNS 실패나 시간 초과만으로 정책 차단을 판정하지 마세요."
    )
    report("워커 시작 시 자동 실행한 `tradingagents doctor` 결과:\n\n" + details, status if network_issue else None)


if __name__ == "__main__":
    mode, payload = sys.argv[1], json.load(sys.stdin)
    if mode == "live":
        live(payload, codex=sys.argv[2:] == ["codex"])
    else:
        {
            "env": env, "network": network, "ruff": ruff, "openspec": openspec,
            "chart-prompt": chart_prompt, "chart-pre": chart_pre,
            "chart-post": chart_post, "chart-stop": chart_stop,
        }[mode](payload)
