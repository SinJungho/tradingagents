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
from tradingagents.runtime_diagnostics import diagnose_runtime, worker_network_policy
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
app.add_typer(portfolio_app, name="portfolio")
app.add_typer(auth_app, name="auth")


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
    output_format: str = typer.Option("json", "--format", help="Output format: json or text"),
) -> None:
    """Export the DNS and TCP destinations the current worker needs; does not change host policy."""
    policy = worker_network_policy()
    if output_format == "json":
        typer.echo(json.dumps(policy, ensure_ascii=False, indent=2))
        return
    if output_format != "text":
        console.print("--format must be json or text", style="red")
        raise typer.Exit(code=2)

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
