# Repository guidance

- Keep broker access read-only in application code. Never add order placement, modification, cancellation, conditional-order, or automated trading calls.
- Keep real broker credentials, access tokens, account identifiers, and raw account responses out of prompts, logs, reports, and remote tracing. Use only synthetic values in fixtures.
- Use synthetic fixtures for portfolio tests. Tests must not call a live broker or LLM.
- Preserve unrelated user files and changes. Do not inspect or copy `.env` or `.env.bak` values.

## Investment research requests

Classify each research request into one type and follow its flow. Repeat requests of the same type use the same flow and defaults.

| Type | Trigger | Flow |
| --- | --- | --- |
| Market report | 미국 시장 마감·장후 보고서 | `tradingagents market-report` → 동부시간 20시 기준 직전 완료 거래일 → 자료 충족 상태·Markdown·HTML·JSON 경로. 실제 LLM 평가는 명시적 보고서 생성 요청에서만 실행하며 개발 검증은 합성 자료 또는 `--no-llm`을 사용한다. |
| Portfolio check | "check my portfolio", holdings review | Confirm data source and as-of time → `tradingagents portfolio live` (summary mode by default; add `--full-workflow` only when deep analysis is asked) → portfolio impact and conditional scenarios |
| Stock discovery | User supplies tickers or asks for market-wide candidates | For up to 10 supplied tickers, run `tradingagents discover --tickers <T1,T2>`. For market-wide screening, run `tradingagents discover --universe all` or select sections such as `sp500,russell2000,smallcap`; show deterministic factor candidates and source limits, then use the single-stock workflow only for tickers the user selects. The screen does not call an LLM or rank across factors |
| Single-stock analysis | a ticker is named | Skip discovery → confirm data and date → `tradingagents --ticker <T> --date <D>` → Bull/Bear review → evidence check → Trader/Risk/Portfolio Manager decision |
| Investment scenario | buy/hold/sell, position sizing | If Toss live data is explicitly authorized, run `tradingagents portfolio live --symbol <T>` in summary mode by default; use `--full-workflow` only for a deep-analysis request → conditional scenarios. If the user supplies a holdings JSON file, use `tradingagents --ticker <T> --date <D> --portfolio <file.json>`. |

- Do not ask for what the repo, config, or conversation already answers. Ask only for a missing input that changes the result (ticker, date, holdings).
- Run live account reads and real LLM analysis only when the user explicitly asks; otherwise use `tradingagents portfolio demo` or give the command to run.
- Never report an unimplemented feature as executed. Feature work starts with an OpenSpec change.
- Do not state target prices or returns without a computed basis. Report data as-of times and gaps as unknown, not zero.
- These rules govern the coding agent only; they do not make the app run analyses on its own.

## OpenSpec

- Before implementing a feature or behavior change, inspect `openspec/` and create or update the relevant OpenSpec change with its proposal, requirements/scenarios, and tasks.
- Keep implementation and task status aligned with the approved OpenSpec scope; validate the change and archive it when complete.
- Follow `openspec/config.yaml` for artifact language and formatting conventions.

## Agent skills

- Repeated workflows live in `.agents/skills/` (Codex reads it directly; `.claude/skills` is a symlink to it for Claude Code): `portfolio-check`, `stock-scenario`, `backtest-eval`, `api-doctor`, `model-selection`, `openspec-change`, `next-steps`, `reference-research`. Update a skill when its workflow changes, and keep the rules above authoritative.

## Agent hooks

- `.claude/settings.json` (Claude Code) and `.codex/hooks.json` plus `.codex/rules/` (Codex) enforce the `.env` ban, live-run confirmation, ruff on edited Python, and OpenSpec checks at stop. New Codex sessions also run the API network preflight. Both call `.claude/hooks/guard.py`; change behavior there and keep `tests/test_agent_hooks.py` passing.

## Verification

- Run focused tests for changed behavior, then `./.venv/bin/python -m pytest -q`.
- Run `./.venv/bin/ruff check .`.
- Check the installed CLI with `./.venv/bin/tradingagents --help` or the equivalent module entry point.
