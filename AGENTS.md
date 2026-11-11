# Repository guidance

- Keep broker access read-only in application code. Never add order placement, modification, cancellation, conditional-order, or automated trading calls.
- Keep real broker credentials, access tokens, account identifiers, and raw account responses out of prompts, logs, reports, and remote tracing. Use only synthetic values in fixtures.
- Use synthetic fixtures for portfolio tests. Tests must not call a live broker or LLM.
- Preserve unrelated user files and changes. Do not inspect or copy `.env` or `.env.bak` values.

## Investment research requests

Classify each research request into one type and follow its flow. Repeat requests of the same type use the same flow and defaults.

| Type | Trigger | Flow |
| --- | --- | --- |
| Portfolio check | "check my portfolio", holdings review | Confirm data source and as-of time → `tradingagents portfolio live` (summary mode by default; add `--full-workflow` only when deep analysis is asked) → portfolio impact and conditional scenarios |
| Stock discovery | "find stocks", screening without tickers | Not implemented. Say so, do not invent candidates, and point to an OpenSpec change for it |
| Single-stock analysis | a ticker is named | Skip discovery → confirm data and date → `tradingagents --ticker <T> --date <D>` → Bull/Bear review → evidence check → Trader/Risk/Portfolio Manager decision |
| Investment scenario | buy/hold/sell, position sizing | Run the single-stock flow (with `--portfolio` when holdings are given) → conditional buy/hold/sell scenarios with their triggers |

- Do not ask for what the repo, config, or conversation already answers. Ask only for a missing input that changes the result (ticker, date, holdings).
- Run live account reads and real LLM analysis only when the user explicitly asks; otherwise use `tradingagents portfolio demo` or give the command to run.
- Never report an unimplemented feature as executed. Feature work starts with an OpenSpec change.
- Do not state target prices or returns without a computed basis. Report data as-of times and gaps as unknown, not zero.
- These rules govern the coding agent only; they do not make the app run analyses on its own.

## OpenSpec

- Before implementing a feature or behavior change, inspect `openspec/` and create or update the relevant OpenSpec change with its proposal, requirements/scenarios, and tasks.
- Keep implementation and task status aligned with the approved OpenSpec scope; validate the change and archive it when complete.
- Follow `openspec/config.yaml` for artifact language and formatting conventions.

## Verification

- Run focused tests for changed behavior, then `./.venv/bin/python -m pytest -q`.
- Run `./.venv/bin/ruff check .`.
- Check the installed CLI with `./.venv/bin/tradingagents --help` or the equivalent module entry point.
