"""End-to-end smoke for structured-output agents against a real LLM provider.

Runs the three decision-making agents (Research Manager, Trader, Portfolio
Manager) directly with their structured-output bindings and prints the
typed Pydantic instance + the rendered markdown for each.  Use this to
verify a provider's native structured-output mode returns clean instances on
the schemas we ship (tool calling for GLM, response_schema for Gemini, and
tool use for Anthropic).

Usage:
    OPENAI_API_KEY=... python scripts/smoke_structured_output.py openai
    GOOGLE_API_KEY=... python scripts/smoke_structured_output.py google
    ANTHROPIC_API_KEY=... python scripts/smoke_structured_output.py anthropic
    DEEPSEEK_API_KEY=... python scripts/smoke_structured_output.py deepseek
    ./.venv/bin/python scripts/smoke_structured_output.py nvidia --single-call \
        --deep-model deepseek-ai/deepseek-v4.1-flash --max-tokens 256 \
        --confirm-no-charge

The default mode does NOT call propagate(); it exercises the three
structured-output agents and the deterministic rating parser. NVIDIA must use
``--single-call``, which makes exactly one capped structured request from
clearly synthetic input and never falls back to free text.
"""

from __future__ import annotations

import argparse
import fcntl
import os
import sys
import tempfile
import time
from pathlib import Path

from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.agents.rating import run_rating
from tradingagents.agents.schemas import ResearchPlan, render_research_plan
from tradingagents.agents.trader.trader import create_trader
from tradingagents.llm_clients import create_llm_client

PROVIDER_DEFAULTS = {
    "openai": ("gpt-5.4-mini", None),
    "google": ("gemini-3.5-flash", None),
    "anthropic": ("claude-sonnet-4-6", None),
    "deepseek": ("deepseek-v4-flash", None),
    "qwen": ("qwen3.7-plus", None),
    "glm": ("glm-5", None),
    "xai": ("grok-4.3", None),
    "nvidia": ("deepseek-ai/deepseek-v4.1-flash", "z-ai/glm-5.3-flash"),
}
MAX_OUTPUT_TOKENS = 256
MAX_NVIDIA_REQUESTS_PER_RUN = 1
MIN_NVIDIA_REQUEST_INTERVAL_SECONDS = 60
NVIDIA_SMOKE_TIMEOUT_SECONDS = 300
NVIDIA_SMOKE_RATE_LIMIT_FILE = (
    Path(tempfile.gettempdir()) / "tradingagents_nvidia_smoke_last_request"
)


# Minimal but realistic state for the three agents.
DEBATE_HISTORY = """
Bull Analyst: NVDA's data-center revenue grew 60% YoY last quarter, driven by
Blackwell ramp; sovereign AI deals with multiple governments add a $40B+
multi-year tailwind. Margins remain above peer average.

Bear Analyst: Concentration risk is real — top three customers are >40% of
revenue. Any pause in hyperscaler capex would compress the multiple. China
export restrictions still cap a meaningful portion of demand.
"""

SYNTHETIC_SMOKE_PROMPT = """Synthetic contract check only. The fictional case SYNTHETIC-ASSET-001
has two contradictory, invented notes: one says a made-up product may grow,
and the other says demand is uncertain. Do not make claims about real companies,
accounts, holdings, market facts, or returns. Return a concise research plan.
"""


def _run_single_structured_call(
    model: str, max_tokens: int, *, provider: str = "nvidia", http_client=None
):
    """Run one capped NVIDIA request through TradingAgents' client/schema path.

    This intentionally invokes the structured binding directly so a failed
    response cannot trigger the normal agent free-text fallback and a second
    billable request.
    """
    if not 1 <= max_tokens <= MAX_OUTPUT_TOKENS:
        raise ValueError(f"max_tokens must be between 1 and {MAX_OUTPUT_TOKENS}")

    llm = create_llm_client(
        provider=provider,
        model=model,
        max_retries=0,
        timeout=NVIDIA_SMOKE_TIMEOUT_SECONDS,
        extra_body={"max_tokens": max_tokens},
        **({"http_client": http_client} if http_client is not None else {}),
    ).get_llm()
    structured_llm = llm.with_structured_output(ResearchPlan, include_raw=True)
    started = time.monotonic()
    result = structured_llm.invoke(SYNTHETIC_SMOKE_PROMPT)
    return result, time.monotonic() - started


def _usage_counts(raw) -> tuple[int | None, int | None, int | None]:
    usage = getattr(raw, "usage_metadata", None) or raw.response_metadata.get("token_usage", {})
    input_tokens = usage.get("input_tokens", usage.get("prompt_tokens"))
    output_tokens = usage.get("output_tokens", usage.get("completion_tokens"))
    total_tokens = usage.get("total_tokens")
    return input_tokens, output_tokens, total_tokens


def _reserve_nvidia_smoke_request_slot() -> tuple[bool, int | None]:
    """Reserve one local smoke request slot; persist no credentials or prompts."""
    try:
        fd = os.open(
            NVIDIA_SMOKE_RATE_LIMIT_FILE,
            os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except OSError:
        return False, None

    locked = False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        locked = True
        raw_last_request = os.read(fd, 64).decode("ascii", errors="ignore").strip()
        try:
            last_request = float(raw_last_request) if raw_last_request else None
        except ValueError:
            last_request = None

        now = time.time()
        if last_request is not None:
            remaining = MIN_NVIDIA_REQUEST_INTERVAL_SECONDS - (now - last_request)
            if remaining > 0:
                return False, int(remaining + 0.999)

        os.lseek(fd, 0, os.SEEK_SET)
        os.ftruncate(fd, 0)
        os.write(fd, f"{now:.6f}".encode("ascii"))
        os.fsync(fd)
        return True, 0
    except OSError:
        return False, None
    finally:
        if locked:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _safe_error_summary(exc: Exception) -> str:
    """Summarize an SDK error without exposing its message or request data."""
    parts = [type(exc).__name__]
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int) and not isinstance(status_code, bool):
        parts.append(f"HTTP {status_code}")
    cause = exc.__cause__ or exc.__context__
    if cause is not None:
        parts.append(f"cause={type(cause).__name__}")
    return "; ".join(parts)


def _run_nvidia_single_call(
    model: str, max_tokens: int, *, confirmed_no_charge: bool = False
) -> int:
    if not 1 <= max_tokens <= MAX_OUTPUT_TOKENS:
        print(
            f"Smoke SKIPPED: --max-tokens must be between 1 and {MAX_OUTPUT_TOKENS}; "
            "no API request was made."
        )
        return 2

    if not confirmed_no_charge:
        print(
            "Smoke SKIPPED: no-charge NVIDIA evaluation quota was not confirmed; "
            "no API request was made."
        )
        return 2

    if not os.environ.get("NVIDIA_API_KEY"):
        print("Smoke SKIPPED: NVIDIA_API_KEY is not set; no API request was made.")
        return 2

    reserved, retry_after = _reserve_nvidia_smoke_request_slot()
    if not reserved:
        if retry_after is None:
            print("Smoke SKIPPED: local request limit could not be enforced; no API request was made.")
        else:
            print(
                "Smoke SKIPPED: local safety limit is 1 request per 60 seconds; "
                f"try again in {retry_after}s. No API request was made."
            )
        return 2

    print("Provider: nvidia")
    print(f"Model: {model}")
    print("Synthetic input only; this checks the structured-output contract, not analysis accuracy.")
    print(f"Maximum output tokens: {max_tokens} (hard cap: {MAX_OUTPUT_TOKENS})")
    print(f"Request timeout: {NVIDIA_SMOKE_TIMEOUT_SECONDS}s")
    print(
        "Local request limit: at most "
        f"{MAX_NVIDIA_REQUESTS_PER_RUN} per run and 1 per 60 seconds; "
        "automatic retries disabled"
    )

    try:
        result, elapsed = _run_single_structured_call(
            model, max_tokens, provider="nvidia"
        )
    except Exception as exc:
        # Exception messages may contain request details or provider response data.
        summary = _safe_error_summary(exc)
        print(f"Smoke FAILED: {summary}; no fallback or retry was attempted.")
        return 1

    plan = result.get("parsed")
    if plan is None:
        print("Smoke FAILED: response did not parse as ResearchPlan; no fallback was attempted.")
        return 1

    rendered = render_research_plan(plan)
    required = ("**Recommendation**:", "**Rationale**:", "**Strategic Actions**:")
    if not all(marker in rendered for marker in required):
        print("Smoke FAILED: rendered ResearchPlan is missing a required section.")
        return 1

    raw = result["raw"]
    input_tokens, output_tokens, total_tokens = _usage_counts(raw)
    print("Actual LLM requests: 1")
    print(f"Latency: {elapsed:.2f}s")
    if total_tokens is not None:
        print(
            "Token usage: "
            f"input={input_tokens if input_tokens is not None else 'n/a'}, "
            f"output={output_tokens if output_tokens is not None else 'n/a'}, "
            f"total={total_tokens}"
        )
    else:
        print("Token usage: not provided by response")
    print("Smoke PASSED: one NVIDIA structured response parsed and rendered.")
    print(rendered)
    return 0


def _make_rm_state():
    return {
        "company_of_interest": "NVDA",
        "investment_debate_state": {
            "history": DEBATE_HISTORY,
            "bull_history": "Bull Analyst: NVDA's data-center revenue grew 60% YoY...",
            "bear_history": "Bear Analyst: Concentration risk is real...",
            "current_response": "",
            "judge_decision": "",
            "count": 1,
        },
    }


def _make_trader_state(investment_plan: str):
    return {
        "company_of_interest": "NVDA",
        "investment_plan": investment_plan,
    }


def _make_pm_state(investment_plan: str, trader_plan: str):
    return {
        "company_of_interest": "NVDA",
        "past_context": "",
        "risk_debate_state": {
            "history": "Aggressive: lean in. Conservative: trim. Neutral: balanced sizing.",
            "aggressive_history": "Aggressive: ...",
            "conservative_history": "Conservative: ...",
            "neutral_history": "Neutral: ...",
            "judge_decision": "",
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "count": 1,
        },
        "market_report": "Market report.",
        "sentiment_report": "Sentiment report.",
        "news_report": "News report.",
        "fundamentals_report": "Fundamentals report.",
        "investment_plan": investment_plan,
        "trader_investment_plan": trader_plan,
    }


def _print_section(title: str, content: str) -> None:
    bar = "=" * 70
    print(f"\n{bar}\n{title}\n{bar}\n{content}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", choices=list(PROVIDER_DEFAULTS.keys()))
    parser.add_argument("--deep-model", default=None, help="Override deep_think_llm")
    parser.add_argument("--quick-model", default=None, help="Override quick_think_llm")
    parser.add_argument(
        "--single-call",
        action="store_true",
        help="Run one synthetic NVIDIA structured-output request; no fallback or retry",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=256,
        help=f"Maximum output tokens for --single-call (1-{MAX_OUTPUT_TOKENS}; default: 256)",
    )
    parser.add_argument(
        "--confirm-no-charge",
        action="store_true",
        help="Confirm your NVIDIA account has a no-charge evaluation quota for this call",
    )
    args = parser.parse_args()

    if args.single_call:
        if args.provider != "nvidia":
            parser.error("--single-call is currently limited to provider 'nvidia'")
        if not 1 <= args.max_tokens <= MAX_OUTPUT_TOKENS:
            parser.error(f"--max-tokens must be between 1 and {MAX_OUTPUT_TOKENS}")
        model = args.deep_model or PROVIDER_DEFAULTS[args.provider][0]
        return _run_nvidia_single_call(
            model, args.max_tokens, confirmed_no_charge=args.confirm_no_charge
        )

    if args.provider == "nvidia":
        parser.error("provider 'nvidia' requires --single-call to enforce local safety limits")

    default_deep_model, default_quick_model = PROVIDER_DEFAULTS[args.provider]
    deep_model = args.deep_model or default_deep_model
    quick_model = args.quick_model or default_quick_model or default_deep_model

    print(f"Provider: {args.provider}")
    print(f"Deep model:  {deep_model}")
    print(f"Quick model: {quick_model}")

    # Build the LLM clients via the framework's factory.
    deep_client = create_llm_client(provider=args.provider, model=deep_model)
    quick_client = create_llm_client(provider=args.provider, model=quick_model)
    deep_llm = deep_client.get_llm()
    quick_llm = quick_client.get_llm()

    # 1) Research Manager
    rm = create_research_manager(deep_llm)
    rm_result = rm(_make_rm_state())
    investment_plan = rm_result["investment_plan"]
    _print_section("[1] Research Manager — investment_plan", investment_plan)

    # 2) Trader (consumes RM's plan)
    trader = create_trader(quick_llm)
    trader_result = trader(_make_trader_state(investment_plan))
    trader_plan = trader_result["trader_investment_plan"]
    _print_section("[2] Trader — trader_investment_plan", trader_plan)

    # 3) Portfolio Manager (consumes both)
    pm = create_portfolio_manager(deep_llm)
    pm_result = pm(_make_pm_state(investment_plan, trader_plan))
    final_decision = pm_result["final_trade_decision"]
    _print_section("[3] Portfolio Manager — final_trade_decision", final_decision)

    # 4) The deterministic parser extracts the rating with zero LLM calls.
    rating = run_rating({"final_trade_decision": final_decision})
    _print_section("[4] Rating parser", rating)

    # 5) Lightweight checks: each rendered output should carry the expected
    #    section headers so downstream consumers (memory log, CLI display,
    #    saved reports) keep working.
    checks = [
        ("Research Manager", investment_plan, ["**Recommendation**:"]),
        ("Trader",           trader_plan,     ["**Action**:", "FINAL TRANSACTION PROPOSAL:"]),
        ("Portfolio Manager", final_decision, ["**Rating**:", "**Executive Summary**:", "**Investment Thesis**:"]),
    ]
    print("\n" + "=" * 70 + "\nStructure checks\n" + "=" * 70)
    failures = 0
    for name, text, required in checks:
        for marker in required:
            ok = marker in text
            print(f"  {'PASS' if ok else 'FAIL'}  {name}: contains {marker!r}")
            failures += int(not ok)

    print()
    if failures:
        print(f"Smoke FAILED: {failures} structure check(s) missing.")
        return 1
    print("Smoke PASSED: structured output → rendered markdown chain works for", args.provider)
    return 0


if __name__ == "__main__":
    sys.exit(main())
