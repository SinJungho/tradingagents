import json
import sys
from enum import StrEnum
from typing import Annotated

import typer
from rich.markup import escape

from cli.chatgpt_auth import auth_app
from cli.display import console
from cli.models import AnalystType, AssetType
from cli.portfolio import portfolio_app
from cli.prompts import filter_analysts_for_asset_type, parse_analysts
from cli.run import run_analysis
from tradingagents.backtest import iter_grid, run_backtest, summarize
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients.openai_client import SIGNED_IN_PROVIDERS
from tradingagents.portfolio import load_portfolio
from tradingagents.runtime_diagnostics import (
    codex_network_toml,
    diagnose_runtime,
    worker_network_policy,
)
from tradingagents.stock_discovery import discover_market, discover_nasdaq100, discover_stocks
from tradingagents.style_scores import evaluate_styles

# prompt_toolkit's win32 output module is importable only on Windows (it asserts
# the platform at import time), so gate on the platform rather than catching the
# failure — that way a genuinely broken prompt_toolkit on Windows still surfaces
# instead of silently disabling the handler below. Off Windows this stays an
# empty tuple, which `except` accepts and never matches (#1138).
if sys.platform == "win32":  # pragma: no cover - platform dependent
    from prompt_toolkit.output.win32 import NoConsoleScreenBufferError

    _NO_CONSOLE_ERRORS: tuple[type[BaseException], ...] = (NoConsoleScreenBufferError,)
else:
    _NO_CONSOLE_ERRORS = ()

app = typer.Typer(
    name="TradingAgents",
    help="TradingAgents CLI: Multi-Agents LLM Financial Trading Framework",
    add_completion=True,  # Enable shell completion
)
zone_sample_app = typer.Typer(help="Maintain local, read-only chart-zone sample manifests.")
zone_backtest_app = typer.Typer(help="Evaluate daily chart zones against deterministic baselines.")
app.add_typer(portfolio_app, name="portfolio")
app.add_typer(auth_app, name="auth")
app.add_typer(zone_sample_app, name="zone-sample")
app.add_typer(zone_backtest_app, name="zone-backtest")


@app.command("market-report")
def market_report(
    output_dir: str = typer.Option("results/market-reports", "--output-dir", help="보고서 저장 디렉터리"),
    llm: bool = typer.Option(True, "--llm/--no-llm", help="기존 deep 모델로 근거 기반 해석 작성"),
) -> None:
    """미국 동부시간 20시까지 완료된 시장의 한국어 Markdown·HTML·근거 JSON 보고서."""
    from tradingagents.market_report import (
        collect_report,
        quality_warnings,
        save_report,
        write_narrative,
    )

    report = collect_report()
    if llm:
        write_narrative(report)
    path = save_report(report, output_dir)
    typer.echo(f"보고 대상 거래일: {report['window']['day']} / 기준: {report['window']['cutoff']}")
    typer.echo(f"자료 충족 상태: {'불완전 보고서' if quality_warnings(report) else '수집 범위 내 보고서'}")
    typer.echo(f"저장 경로: {path.resolve()}")


@app.command()
def doctor() -> None:
    """Diagnose API settings and host reachability visible to this process."""
    typer.echo(diagnose_runtime())


@app.command("network-policy")
def network_policy(
    output_format: str = typer.Option("json", "--format", help="Output format: json, text or codex-toml"),
) -> None:
    """Export the DNS and TCP destinations the current worker needs; does not change host policy."""
    if output_format not in {"json", "text", "codex-toml"}:
        typer.echo("--format must be json, text or codex-toml", err=True)
        raise typer.Exit(code=2)
    policy = worker_network_policy()
    if output_format == "codex-toml":
        try:
            fragment = codex_network_toml(policy)
        except ValueError as error:
            typer.echo(str(error), err=True)
            raise typer.Exit(code=2) from None
        typer.echo(fragment, nl=False)
        return
    if output_format == "json":
        typer.echo(json.dumps(policy, ensure_ascii=False, indent=2))
        return

    typer.echo(f"정책 적용 위치: {policy['policy_owner']} (이 명령은 정책을 변경하지 않음)")
    typer.echo("DNS: 워커 resolver로 UDP/TCP 53 허용")
    typer.echo("TCP 목적지:")
    for destination in policy["destinations"]:
        scope = "로컬" if destination["scope"] == "loopback" else "네트워크"
        sources = ", ".join(destination["sources"])
        typer.echo(f"- {destination['hostname']}:{destination['port']} ({scope}; {sources})")
    if policy["unresolved"]:
        typer.echo("확인 불가: " + ", ".join(policy["unresolved"]))


@app.callback(invoke_without_command=True)
def analyze(
    ctx: typer.Context,
    checkpoint: bool | None = typer.Option(
        None,
        "--checkpoint/--no-checkpoint",
        help="Enable/disable checkpoint-resume (save state after each node so a "
        "crashed run can resume). Omit to honor TRADINGAGENTS_CHECKPOINT_ENABLED.",
    ),
    clear_checkpoints: bool = typer.Option(
        False,
        "--clear-checkpoints",
        help="Delete all saved checkpoints before running (force fresh start).",
    ),
    portfolio: str = typer.Option(
        None,
        "--portfolio",
        help="JSON file with current holdings and cash, so the trader, risk and "
        "portfolio agents size against your actual position.",
    ),
    ticker: str = typer.Option(None, "--ticker", help="Ticker to analyze, e.g. NVDA or 0700.HK; skips the prompt"),
    date: str = typer.Option(None, "--date", help="Analysis date, YYYY-MM-DD; skips the prompt"),
    analysts: str = typer.Option(
        None, "--analysts", help="Comma-separated analysts, e.g. market,news; skips the prompt"
    ),
    save: bool | None = typer.Option(
        None, "--save/--no-save", help="Save the report under results_dir without asking"
    ),
    show: bool | None = typer.Option(
        None, "--show/--no-show", help="Show the full report at the end without asking"
    ),
    html: bool | None = typer.Option(
        None, "--html/--no-html",
        help="Save the report as one HTML page too, complete_report.html, without asking (default: yes)",
    ),
):
    """Run an analysis. This is what a bare `tradingagents` does.

    Flags answer their questions; with provider, models, depth and language also
    set through TRADINGAGENTS_* variables, the run asks nothing.
    """
    if ctx.invoked_subcommand is not None:
        return
    if clear_checkpoints:
        from tradingagents.graph.checkpointer import clear_all_checkpoints
        n = clear_all_checkpoints(DEFAULT_CONFIG["data_cache_dir"])
        console.print(f"[yellow]Cleared {n} checkpoint(s).[/yellow]")
    portfolio_context = None
    if portfolio:
        try:
            portfolio_context = load_portfolio(portfolio)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from None

    try:
        flags = {"ticker": ticker, "date": date, "analysts": analysts, "save": save, "show": show, "html": html}
        run_analysis(checkpoint=checkpoint, portfolio=portfolio_context, flags=flags)
    except _NO_CONSOLE_ERRORS:
        # A terminal with no console buffer cannot host the interactive prompts.
        # Emit one actionable line on stderr instead of a prompt_toolkit
        # traceback; plain text, since rich may not render here either (#1138).
        typer.echo(
            "Error: no Windows console available. The interactive CLI needs a real "
            "console buffer — run it from Windows Terminal, PowerShell, or cmd.exe "
            "rather than a piped or embedded terminal.",
            err=True,
        )
        raise typer.Exit(code=1) from None


@app.command()
def backtest(
    tickers: str = typer.Argument(..., help="Comma-separated tickers, e.g. NVDA,AAPL"),
    start: str = typer.Option(..., "--start", help="First analysis date, YYYY-MM-DD"),
    end: str = typer.Option(..., "--end", help="Last analysis date, YYYY-MM-DD"),
    every: int = typer.Option(7, "--every", help="Days between analysis dates"),
    analysts: str = typer.Option(
        None, "--analysts", help="Comma-separated analysts to run: market, sentiment, news, fundamentals; omit for all the asset type allows"
    ),
    asset_type: str = typer.Option("stock", "--asset-type", help="stock or crypto"),
    portfolio: str = typer.Option(
        None, "--portfolio", help="JSON file with holdings and cash, held constant across the grid"
    ),
    run_id: str = typer.Option(
        None, "--run-id", help="Continue an earlier sweep: its cells are skipped and its log reused"
    ),
):
    """Score past decisions over a grid of tickers and dates."""

    try:
        dates = iter_grid(start, end, every)
        book = load_portfolio(portfolio) if portfolio else None
        kind = AssetType(asset_type.strip().lower())
        # The analysts are named and checked as for an analysis; without a
        # choice, every analyst the asset type allows runs.
        chosen = (parse_analysts(analysts, kind) if analysts
                  else filter_analysts_for_asset_type(list(AnalystType), kind))
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None

    names = [t.strip() for t in tickers.split(",") if t.strip()]
    if not names:
        console.print("[red]No ticker to analyze; pass them comma-separated, e.g. NVDA,AAPL[/red]")
        raise typer.Exit(code=1)

    def show_progress(done, total, ticker, date):
        console.print(f"[dim][{done}/{total}] {ticker} {date}[/dim]")

    kwargs = {"asset_type": kind.value, "portfolio": book, "run_id": run_id, "progress": show_progress,
              "selected_analysts": [a.value for a in chosen]}

    try:
        result = run_backtest(names, dates, DEFAULT_CONFIG, **kwargs)
    except Exception as exc:  # a missing key or an unknown analyst is a setup error
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None
    console.print(summarize(result).render())
    console.print(f"\nRan {result.cells_run} cells, skipped {result.skipped}. Log: {result.log_path}")
    console.print(f"Continue or settle this sweep: --run-id {result.run_id}")
    for ticker, date, reason in result.failures:
        console.print(f"[yellow]failed:[/yellow] {ticker} {date}: {reason}")
    for ticker, reason in result.settlement_failures:
        console.print(f"[yellow]unsettled:[/yellow] {ticker}: {reason}")


@app.command("style-backtest")
def style_backtest(
    tickers: str = typer.Argument(..., help="Comma-separated US tickers, e.g. NVDA,AAPL"),
    start: str = typer.Option(..., "--start", help="First analysis date, YYYY-MM-DD"),
    end: str = typer.Option(..., "--end", help="Last analysis date, YYYY-MM-DD"),
    every: int = typer.Option(30, "--every", help="Days between analysis dates"),
):
    """Check whether code-computed style signals predicted alpha. Calls no model."""
    names = [t.strip() for t in tickers.split(",") if t.strip()]
    try:
        dates = iter_grid(start, end, every)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None
    if not names:
        console.print("[red]No ticker to score; pass them comma-separated, e.g. NVDA,AAPL[/red]")
        raise typer.Exit(code=1)
    result = evaluate_styles(names, dates, progress=lambda done, total, ticker: console.print(
        f"[dim][{done}/{total}] {ticker}[/dim]"))
    console.print(escape(result.render()))


@app.command("discover")
def discover(
    tickers: str | None = typer.Option(
        None, "--tickers", help="Comma-separated US stock tickers, up to 10, e.g. NVDA,AAPL"
    ),
    universe: str | None = typer.Option(
        None,
        "--universe",
        help=(
            "Comma-separated sections: us-listed, nasdaq100, sp500, russell1000, "
            "russell2000, sp400, sp600, largecap, midcap, smallcap, microcap, all"
        ),
    ),
):
    """Screen supplied tickers or US market sections with deterministic signals; calls no model."""
    if (tickers is None) == (universe is None):
        console.print("Provide exactly one of --tickers or --universe.", style="red", markup=False)
        raise typer.Exit(code=1)
    try:
        if universe is not None:
            selections = [value.strip().lower() for value in universe.split(",")]
            if selections == ["nasdaq100"]:
                result = discover_nasdaq100()
            else:
                def report_progress(done: int, total: int, ticker: str) -> None:
                    if done == 1 or done % 100 == 0 or done == total:
                        console.print(f"[{done}/{total}] {ticker}", markup=False, style="dim")

                result = discover_market(selections, progress=report_progress)
        else:
            result = discover_stocks([ticker.strip() for ticker in tickers.split(",")])
    except ValueError as exc:
        console.print(str(exc), style="red", markup=False)
        raise typer.Exit(code=1) from None
    console.print(result.render(), markup=False)


@app.command("chart-zones")
def chart_zones(
    tickers: str = typer.Option(..., "--tickers", help="Comma-separated Yahoo tickers, up to 10"),
    date: str | None = typer.Option(None, "--date", help="As-of date, YYYY-MM-DD"),
    json_output: bool = typer.Option(False, "--json", help="Print result objects as JSON"),
    output_dir: str | None = typer.Option(None, "--output-dir", help="Base directory for immutable runs"),
) -> None:
    """Compute Yahoo daily zones deterministically without calling an LLM."""
    from pathlib import Path

    import pandas as pd

    from tradingagents.dataflows.chart_zones import get_chart_zones_with_snapshot, resolve_as_of
    from tradingagents.dataflows.symbols import normalize_symbol, safe_ticker_component

    names = [normalize_symbol(part.strip()) for part in tickers.split(",") if part.strip()]
    names = list(dict.fromkeys(names))
    if not names:
        raise typer.BadParameter("Pass at least one ticker.", param_hint="--tickers")
    if len(names) > 10:
        raise typer.BadParameter("At most 10 tickers are allowed.", param_hint="--tickers")
    try:
        as_of = resolve_as_of(date)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--date") from None
    base = Path(output_dir).expanduser() if output_dir else Path.home() / ".tradingagents" / "chart-zones"
    results = []
    for symbol in names:
        try:
            result, frame = get_chart_zones_with_snapshot(symbol, as_of)
            digest = result["snapshot_sha256"]
            resolved_as_of = result["as_of"]
            run_dir = base / safe_ticker_component(symbol) / f"{resolved_as_of}-{digest[:8]}"
            run_dir.mkdir(parents=True, exist_ok=True)
            bars = frame.loc[frame.index <= pd.Timestamp(resolved_as_of)].copy()
            bars.to_csv(run_dir / "snapshot.csv", float_format="%.6f", lineterminator="\n")
            (run_dir / "zones.json").write_text(
                json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
            )
            result["run_dir"] = str(run_dir)
            results.append(result)
        except Exception as exc:
            results.append({"ticker": symbol, "as_of": as_of, "status": "failed",
                            "error": f"{type(exc).__name__}: {exc}"})
    if json_output:
        typer.echo(json.dumps(results, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        for result in results:
            zones = result.get("zones", [])
            nearest_support = next((z for z in zones if z["type"] == "support"), None)
            nearest_resistance = next((z for z in zones if z["type"] == "resistance"), None)
            trend = result.get("trend", {}).get("recent_252", {}).get("direction", "unknown")
            pending = result.get("validation", {}).get("pending", False)
            stale = result.get("validation", {}).get("stale", False)
            def fmt(zone):
                return "—" if not zone else (
                    f"{zone['lower']:.2f}–{zone['upper']:.2f} ({zone['distance_atr']:.2f} ATR)"
                )

            typer.echo(f"{result['ticker']} {result['as_of']}: {result['status']} | trend={trend} | "
                       f"support={fmt(nearest_support)} | resistance={fmt(nearest_resistance)} | "
                       f"pending={pending} stale={stale} | {result.get('run_dir', result.get('error', ''))}")
    if any(result["status"] == "failed" for result in results):
        raise typer.Exit(code=1)


@app.command("chart-check")
def chart_check(
    run_dir: str = typer.Option(..., "--run-dir", help="A chart-zones run directory"),
    chart_csv: str = typer.Option(..., "--chart-csv", help="Tratto CSV with date,o,h,l,c,v columns"),
    chart_timezone: str = typer.Option("America/New_York", "--chart-timezone", help="IANA timezone of chart export"),
    json_output: bool = typer.Option(False, "--json", help="Print the comparison as JSON"),
) -> None:
    """Compare a Tratto chart export with the Yahoo snapshot windows."""
    import shutil
    from pathlib import Path
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    from tradingagents.dataflows.chart_check import add_retry_state, compare_chart_csv

    try:
        export_timezone = ZoneInfo(chart_timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise typer.BadParameter("Expected an IANA timezone.", param_hint="--chart-timezone") from None

    root = Path(run_dir).expanduser()
    source = Path(chart_csv).expanduser()
    if not (root / "zones.json").is_file() or not (root / "snapshot.csv").is_file():
        raise typer.BadParameter("Run directory must contain zones.json and snapshot.csv.", param_hint="--run-dir")
    if not source.is_file():
        raise typer.BadParameter("Chart CSV does not exist.", param_hint="--chart-csv")
    prior_path = root / "chart_validation.json"
    prior = json.loads(prior_path.read_text(encoding="utf-8")) if prior_path.is_file() else None
    destination = root / "chart_check.csv"
    if source.resolve() != destination.resolve():
        shutil.copyfile(source, destination)
    comparison = compare_chart_csv(str(root), str(source), chart_timezone=export_timezone)
    result = add_retry_state({**comparison, "chart_timezone": export_timezone.key}, prior)
    (root / "chart_validation.json").write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    if json_output:
        typer.echo(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        typer.echo(f"{result['status']}: {result.get('ticker', '')} {result.get('as_of', '')}; "
                   f"rows={result.get('rows', 0)}/{result.get('expected_rows', 0)}; "
                   f"retry_recommended={result.get('retry_recommended', False)}; "
                   f"saved={root / 'chart_validation.json'}")


@zone_sample_app.command("refresh")
def zone_sample_refresh(
    account_ordinal: int | None = typer.Option(None, "--account-ordinal", min=1,
                                               help="Toss account number; prompt if omitted in an interactive terminal"),
    source: str = typer.Option("toss", "--source", help="Sample source: toss or sec"),
    output_dir: str | None = typer.Option(None, "--output-dir", help="Private sample directory"),
) -> None:
    """Refresh the Toss holdings or SEC 13F sample without trading or LLM calls."""
    from pathlib import Path

    if source not in {"toss", "sec"}:
        raise typer.BadParameter("--source must be toss or sec.")
    root = Path(output_dir).expanduser() if output_dir else None
    if source == "sec":
        from tradingagents.zone_13f import refresh_sec_sample
        from tradingagents.zone_samples import sample_directory

        try:
            sample = refresh_sec_sample(root or sample_directory())
        except Exception as exc:
            typer.echo(f"SEC 13F 표본 갱신 실패({type(exc).__name__}); 기존 표본은 유지했습니다.", err=True)
            raise typer.Exit(code=1) from None
        quality = sample["quality"]
        typer.echo(f"SEC 13F 표본: {sample['sample_id']} / report period {sample['report_period']} / "
                   f"ticker {len(sample['tickers'])}개 / 매핑 후보 {quality['mapped_candidate_cusips']}개 / "
                   f"ambiguous {quality['ambiguous_candidate_cusips'] + quality['ambiguous_security_type_count']}개 / "
                   f"미매핑 {quality['unmapped_candidate_cusips']}개 / "
                   f"상태 {quality['status']} / eligible from {sample['eligible_from']}")
        return

    import os

    from cli.portfolio import _ACK_VALUE, _remote_tracing_disabled, _select_account
    from tradingagents.portfolio.toss import TossPortfolioAdapter
    from tradingagents.zone_samples import held_tickers, sample_directory, write_sample

    if os.environ.get("TOSS_BROKER_READ_ONLY_VERIFIED") != _ACK_VALUE:
        raise typer.BadParameter("Read-only Toss acknowledgement is required.")
    client_id = os.environ.get("TOSS_CLIENT_ID")
    client_secret = os.environ.get("TOSS_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise typer.BadParameter("Set Toss credentials in the environment.")
    try:
        with _remote_tracing_disabled():
            adapter = TossPortfolioAdapter(client_id, client_secret)
            account = _select_account(adapter.get_accounts(), account_ordinal)
            holdings = adapter.get_holdings(account.account_seq)
    except Exception as exc:
        typer.echo(f"보유 종목 조회 실패({type(exc).__name__}); 기존 표본은 변경하지 않았습니다.", err=True)
        raise typer.Exit(code=1) from None
    symbols, unresolved = held_tickers(holdings.holdings, country="US")
    if holdings.retrieved_at is None:
        typer.echo("보유 조회 시각이 없어 point-in-time 표본을 갱신하지 않았습니다.", err=True)
        raise typer.Exit(code=1)
    retrieved_at = holdings.retrieved_at.isoformat()
    excluded_non_us = sum(1 for item in holdings.holdings if (item.market_country or "").upper() != "US")
    sample = write_sample(holdings=symbols, retrieved_at=retrieved_at,
                          priority_tickers=symbols, root=root or sample_directory())
    typer.echo(f"표본: {sample['sample_id']} / ticker {len(sample['tickers'])}개 / "
               f"현재 보유 우선 {len(sample['priority_tickers'])}개 / "
               f"미국 외 제외 {excluded_non_us}개 / 미국 ticker 매핑 불가 {len(unresolved)}개 / "
               f"조회시각 {retrieved_at}")
    typer.echo(f"저장 경로: {sample['path']}")


@zone_backtest_app.command("run")
def zone_backtest_run(
    period: str = typer.Option(..., "--period", help="Run the preregistered tune or validate period"),
    sample_dir: str | None = typer.Option(None, "--sample-dir", help="Private chart-zone sample directory"),
    output_dir: str | None = typer.Option(None, "--output-dir", help="Private backtest data and evaluation directory"),
    json_output: bool = typer.Option(False, "--json", help="Print compact results as JSON"),
) -> None:
    """Run fixed-sample zone research with Yahoo bars and no LLM calls."""
    import hashlib
    from datetime import UTC, datetime, timedelta
    from pathlib import Path
    from zoneinfo import ZoneInfo

    import exchange_calendars as xcals
    import pandas as pd

    from tradingagents.dataflows.chart_zones import resolve_as_of
    from tradingagents.dataflows.files import replace_file
    from tradingagents.dataflows.router import route_to_vendor
    from tradingagents.dataflows.symbols import safe_ticker_component
    from tradingagents.zone_backtest import (
        build_as_of_grid,
        evaluate_sample_frames,
        prepare_sample_history,
        training_as_of_grid,
        training_volatility_cutoffs,
        validate_backtest_history,
        validation_end_date,
    )
    from tradingagents.zone_samples import load_backtest_sample, sample_directory
    from tradingagents.zone_validation import append_evaluation, load_evaluations

    if period not in {"tune", "validate"}:
        raise typer.BadParameter("--period must be tune or validate.")
    sample_root = Path(sample_dir).expanduser() if sample_dir else sample_directory()
    root = Path(output_dir).expanduser() if output_dir else Path.home() / ".tradingagents" / "zone-backtest"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    sample = load_backtest_sample(sample_root)
    sample_id = sample["sample_id"]
    cohort_quality = {}
    if sample.get("sec_13f_sha256"):
        cohort_quality["sec_13f"] = {
            "sample_id": sample.get("sec_13f_sample_id"),
            "sha256": sample["sec_13f_sha256"],
            "eligible_from": sample.get("sec_13f_eligible_from"),
            "overlap_count": sample.get("sec_13f_overlap_count", 0),
            "quality": sample.get("sec_13f_quality", {}),
            "bias_flags": sample.get("sec_13f_bias_flags", []),
        }
    evaluation_root = root / "evaluations"
    prior = [record for zone_type in ("support_resistance", "inside")
             for record in load_evaluations(evaluation_root, zone_type)
             if record.get("sample") == sample_id]
    if prior:
        if period == "tune":
            raise typer.BadParameter("This sample's validation holdout is locked; tuning is not allowed.")
        raise typer.BadParameter("This sample already has an append-only validation result.")

    groups = sample.get("fixed_groups", {})
    groups_by_type = {
        "user_selected": set(groups.get("user_selected", [])),
        "etf_2x": set(groups.get("etf_2x", [])),
        "etf_3x": set(groups.get("etf_3x", [])),
        "holdings_added": set(sample.get("holdings_added", [])),
        "sec_13f": set(sample.get("cohorts", {}).get("sec_13f", [])),
    }
    ticker_cohorts = {}
    for ticker in sample.get("ordered_tickers", sample.get("tickers", [])):
        ticker_cohorts[ticker] = next((name for name, members in groups_by_type.items() if ticker in members),
                                      "primary")
    primary_tickers = {ticker for ticker, cohort in ticker_cohorts.items() if cohort == "primary"}
    if not primary_tickers:
        raise typer.BadParameter("Sample has no primary fixed or 1x ETF tickers.")
    eligibility_dates = {}
    calendar = xcals.get_calendar("XNYS")
    for ticker in groups_by_type["holdings_added"]:
        first_seen = sample.get("holdings_first_seen", {}).get(ticker)
        if not first_seen:
            raise typer.BadParameter(f"No point-in-time eligibility timestamp for holding {ticker}.")
        observed = datetime.fromisoformat(first_seen.replace("Z", "+00:00"))
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=UTC)
        observed_day = observed.astimezone(ZoneInfo("America/New_York")).date()
        sessions = calendar.sessions_in_range(observed_day + timedelta(days=1), observed_day + timedelta(days=31))
        if sessions.empty:
            raise typer.BadParameter(f"No XNYS session found after holding observation for {ticker}.")
        eligibility_dates[ticker] = sessions[0].date().isoformat()
    for ticker in groups_by_type["sec_13f"]:
        eligible = sample.get("sec_13f_eligible_from")
        if not eligible:
            raise typer.BadParameter(f"No point-in-time eligibility date for SEC 13F ticker {ticker}.")
        eligibility_dates[ticker] = eligible

    end = resolve_as_of()
    frames, input_hashes, failures, data_quality = {}, {}, [], {}
    data_root = root / "inputs"
    data_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    for ticker in sample.get("ordered_tickers", sample.get("tickers", [])):
        try:
            frame = route_to_vendor("get_chart_history", ticker, start="2014-01-01", end=end)
            if not isinstance(frame, pd.DataFrame) or frame.empty:
                failures.append({"ticker": ticker, "reason": "NoMarketData"})
                continue
            frame = frame.copy()
            frame.index = pd.DatetimeIndex(pd.to_datetime(frame.index).date)
            frame = frame.loc[~frame.index.duplicated(keep="first")].sort_index()
            frame, bounds = prepare_sample_history(ticker, frame)
            quality = validate_backtest_history(ticker, frame)
            data_quality[ticker] = {**quality, **bounds}
            if quality["status"] != "ok":
                failures.append({"ticker": ticker, "reason": quality["reason"],
                                 "data_quality": quality})
                continue
            frame.index.name = "Date"
            snapshot_bytes = frame.to_csv(float_format="%.6f", lineterminator="\n").encode()
            digest = hashlib.sha256(snapshot_bytes).hexdigest()
            run_dir = data_root / safe_ticker_component(ticker) / digest[:8]
            run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            snapshot_path = run_dir / "snapshot.csv"
            if snapshot_path.exists() and snapshot_path.read_bytes() != snapshot_bytes:
                raise ValueError("snapshot hash collision")
            if not snapshot_path.exists():
                snapshot_path.write_bytes(snapshot_bytes)
            frames[ticker] = frame
            input_hashes[ticker] = digest
        except Exception as exc:
            failures.append({"ticker": ticker, "reason": type(exc).__name__})

    missing_primary = sorted(primary_tickers - set(frames))
    if not frames:
        summary = {"period": period, "sample": sample_id, "loaded_tickers": 0,
                   "missing_primary_tickers": missing_primary, "data_failures": failures,
                   "data_quality": data_quality}
        if json_output:
            typer.echo(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
        else:
            typer.echo(f"{period}: usable Yahoo histories=0; failures={len(failures)}")
            for failure in failures:
                typer.echo(f"failed: {failure['ticker']} ({failure['reason']})")
        raise typer.Exit(code=1)
    if period == "tune":
        validation_start = build_as_of_grid("2024-11-01", "2024-11-15")[0]
        as_of_dates = training_as_of_grid("2019-01-01", "2024-08-31", validation_start)
        if not as_of_dates:
            raise typer.BadParameter("The preregistered tune period has no dates after the 60-session embargo.")
        cutoffs = training_volatility_cutoffs(frames, as_of_dates, primary_tickers=primary_tickers & set(frames))
        sensitivity = {}
        for halflife in (189, 378, 756):
            result = evaluate_sample_frames(
                frames, as_of_dates, sample_id=sample_id, ticker_cohorts=ticker_cohorts,
                ticker_order=sample.get("ordered_tickers"), eligibility_dates=eligibility_dates,
                volatility_cutoffs=tuple(cutoffs["low_high_cutoffs"]),
                recency_halflife=halflife, bootstrap_repetitions=0,
            )
            sensitivity[str(halflife)] = {
                name: {"status": value["status"], "actual": value["actual"],
                       "matched": value["matched"], "matched_lift": value["matched_lift"],
                       "sample_size": value["sample_size"]}
                for name, value in result["results"].items()
            }
        payload = {"sample": sample_id, "params_version": "v1", "baseline_version": "matched-random-v1",
                   "training_dates": [as_of_dates[0], as_of_dates[-1]], "volatility_cutoffs": cutoffs,
                   "validation_start": validation_start, "embargo_sessions": 60,
                   "research_only": True,
                   "data_vintage": "current Yahoo response; historical revisions possible",
                   "daily_input_hashes": input_hashes, "data_quality": data_quality,
                   "cohort_quality": cohort_quality,
                   "missing_primary_tickers": missing_primary,
                   "sensitivity": sensitivity, "evaluated_at": datetime.now(UTC).isoformat()}
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        tune_root = root / "tuning"
        tune_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        tune_path = tune_root / f"{digest[:12]}.json"
        encoded = json.dumps({**payload, "record_id": digest[:12]}, ensure_ascii=False,
                             sort_keys=True, indent=2) + "\n"
        if tune_path.exists() and tune_path.read_text(encoding="utf-8") != encoded:
            raise ValueError("Tuning record hash collision.")
        if not tune_path.exists():
            replace_file(tune_path, lambda temporary: Path(temporary).write_text(encoded, encoding="utf-8"))
        current_tune = {"record_id": digest[:12], "sample": sample_id,
                        "path": str(tune_path), "sha256": digest}
        latest_encoded = json.dumps(current_tune, sort_keys=True, indent=2) + "\n"
        replace_file(tune_root / "latest.json",
                     lambda temporary: Path(temporary).write_text(latest_encoded, encoding="utf-8"))
        summary = {"period": period, "sample": sample_id, "loaded_tickers": len(frames),
                   "missing_primary_tickers": missing_primary, "data_failures": failures,
                   "data_quality": data_quality,
                   "training_dates": [as_of_dates[0], as_of_dates[-1]],
                   "validation_start": validation_start, "volatility_cutoffs": cutoffs,
                   "sensitivity": sensitivity,
                   "cohort_quality": cohort_quality,
                   "tuning_record": current_tune}
    else:
        tune_root = root / "tuning"
        try:
            pointer = json.loads((tune_root / "latest.json").read_text(encoding="utf-8"))
            tuning = json.loads(Path(pointer["path"]).read_text(encoding="utf-8"))
        except (OSError, KeyError, json.JSONDecodeError):
            raise typer.BadParameter("Run --period tune for this sample before validation.") from None
        if tuning.get("sample") != sample_id or pointer.get("sample") != sample_id:
            raise typer.BadParameter("Latest tuning record belongs to a different sample.")
        missing_training_primary = sorted(tuning.get("missing_primary_tickers", []))
        validation_end = validation_end_date(frames)
        as_of_dates = build_as_of_grid("2024-11-01", validation_end)
        cutoffs = tuple(tuning["volatility_cutoffs"]["low_high_cutoffs"])
        result = evaluate_sample_frames(
            frames, as_of_dates, sample_id=sample_id, ticker_cohorts=ticker_cohorts,
            ticker_order=sample.get("ordered_tickers"), eligibility_dates=eligibility_dates,
            volatility_cutoffs=cutoffs,
        )
        if missing_primary or missing_training_primary:
            for value in result["results"].values():
                value["status"] = "inconclusive"
                value["reason"] = ("primary_sample_data_incomplete" if missing_primary
                                    else "training_primary_data_incomplete")
        evaluated_at = datetime.now(UTC).isoformat()
        report_results = {}
        for zone_type, value in result["results"].items():
            primary = value["bootstrap_matched"]["6"]
            report_results[zone_type] = {
                "status": value["status"], "lift": value["matched_lift"],
                "ci95": primary.get("ci95"), "reason": value.get("reason"),
                "research_only": True,
                "data_vintage": "current Yahoo response; historical revisions possible",
                "actual": value["actual"], "random_unconditional": value["random_unconditional"],
                "matched": value["matched"], "matched_event_pairs": value["matched_event_pairs"],
                "sample_size": value["sample_size"],
                "volatility_tercile_lifts": value["volatility_tercile_lifts"],
                "bootstrap_random": value["bootstrap_random"],
                "bootstrap_matched": value["bootstrap_matched"],
                "baseline_diagnostics": result["baseline_diagnostics"],
                "matched_calipers": result["matched_calipers"],
                "cohorts": result["cohorts"],
            }
        as_of_end = as_of_dates[-1] if as_of_dates else validation_end
        evaluated_date = pd.Timestamp(as_of_end)
        quarter_index = evaluated_date.year * 4 + (evaluated_date.month - 1) // 3
        record = append_evaluation({
            "sample": sample_id, "params_version": "v1", "baseline_version": "matched-random-v1",
            "evaluated_at": evaluated_at, "quarter_index": quarter_index,
            "research_only": True,
            "data_vintage": "current Yahoo response; historical revisions possible",
            "period": "validation", "as_of_range": [as_of_dates[0], as_of_end] if as_of_dates else [],
            "input_hashes": {"sample": sample.get("sha256"), "daily_snapshots": input_hashes,
                             "tuning_record": tuning.get("record_id")},
            "cohort_quality": cohort_quality,
            "data_failures": failures, "data_quality": data_quality,
            "missing_training_primary_tickers": missing_training_primary,
            "results": report_results,
        }, evaluation_root)
        summary = {"period": period, "sample": sample_id, "loaded_tickers": len(frames),
                   "missing_primary_tickers": missing_primary, "data_failures": failures,
                   "missing_training_primary_tickers": missing_training_primary,
                   "data_quality": data_quality,
                   "as_of_range": [as_of_dates[0], as_of_end] if as_of_dates else [],
                   "cohort_quality": cohort_quality,
                   "results": report_results, "record_id": record["record_id"],
                   "evaluation_path": str(evaluation_root / f"{record['record_id']}.json")}
    if json_output:
        typer.echo(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        typer.echo(f"{period}: sample={sample_id}, loaded={len(frames)}/{len(sample.get('tickers', []))}, "
                   f"failures={len(failures)}, record={summary.get('record_id', summary.get('tuning_record', {}).get('record_id'))}")
        if period == "validate":
            for name, value in summary["results"].items():
                typer.echo(f"{name}: {value['status']} / lift={value['lift']} / CI={value['ci95']}")
    if period == "validate" and (missing_primary or missing_training_primary):
        raise typer.Exit(code=1)


# The plans `login` and `logout` take: the providers signed in to, not keyed.
Plan = StrEnum("Plan", {name: name for name in SIGNED_IN_PROVIDERS})


@app.command()
def login(plan: Annotated[Plan, typer.Argument(help="The plan to sign in with")]):
    """Sign in with your ChatGPT Plus or Pro plan, for the chatgpt provider."""
    from tradingagents.llm_clients import chatgpt_auth

    try:
        # One unwrapped line, so the sign-in address can be copied whole.
        email = chatgpt_auth.sign_in(
            say=lambda line: console.print(line, soft_wrap=True, markup=False, highlight=False))
    except chatgpt_auth.ChatGPTAuthError as exc:
        console.print(f"[red]{escape(str(exc))}[/red]")
        raise typer.Exit(code=1) from None
    console.print(f"[green]Signed in to ChatGPT as {escape(email)}.[/green]")


@app.command()
def logout(plan: Annotated[Plan, typer.Argument(help="The plan to sign out of")]):
    """Sign out of your ChatGPT plan: revoke this machine's access and forget it."""
    from tradingagents.llm_clients import chatgpt_auth

    outcome = chatgpt_auth.sign_out()
    if outcome == "revoked":
        console.print("Signed out of ChatGPT.")
    elif outcome == "forgotten":
        console.print("[yellow]Signed out here, but OpenAI could not be reached to revoke the sign-in; "
                      "it stays valid at OpenAI until it expires.[/yellow]")
    else:
        console.print("Not signed in to ChatGPT.")


if __name__ == "__main__":
    app()
