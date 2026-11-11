"""Portfolio CLI commands kept separate from the interactive single-symbol CLI."""

from __future__ import annotations

import copy
import math
import os
import re
import sys
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

import typer
from langsmith.run_helpers import tracing_context

from tradingagents.api_diagnostics import format_api_failure
from tradingagents.dataflows.errors import drain_source_failures
from tradingagents.portfolio.analytics import (
    PortfolioAnalytics,
    analyze_portfolio,
    map_market_symbol,
)
from tradingagents.portfolio.context import PortfolioContext, Position
from tradingagents.portfolio.history import SnapshotComparison, append_portfolio_snapshot
from tradingagents.portfolio.models import (
    Account,
    Accounts,
    BuyingPower,
    Holding,
    Holdings,
    Order,
    Orders,
)
from tradingagents.portfolio.reporting import (
    PortfolioReport,
    RequestScope,
    SourceReport,
    build_portfolio_report,
    render_markdown,
)
from tradingagents.portfolio.scenarios import (
    DEFAULT_HORIZONS,
    HorizonScenarios,
    HorizonSpec,
    PortfolioScenarioReport,
    PortfolioScenarioWorkflow,
    ScenarioCase,
    ScenarioConfig,
    SymbolResearchResult,
    TradingDecisionResult,
    sanitize_portfolio_text,
)
from tradingagents.portfolio.technical import TechnicalSnapshot, analyze_daily_candles

portfolio_app = typer.Typer(
    name="portfolio",
    help="Read-only portfolio summaries. `demo` uses only synthetic data.",
    no_args_is_help=True,
)

_ACK_VALUE = "I_ACKNOWLEDGE_READ_ONLY"
_MAX_SYMBOLS = 10
_MAX_ORDER_DAYS = 90
_ORDER_PAGE_LIMIT = 3
_TRANSACTION_PAGE_LIMIT = 10
# Three analysts can each use three tool rounds (market history, indicators,
# then the verified market snapshot) while staying within the portfolio cap.
_SYMBOL_RESEARCH_STEP_LIMIT = 24
_ANALYST_SECTION_CHARS = 1800
_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9.-]{0,31}$")
_OUTPUT_DIR = Path.home() / ".tradingagents" / "portfolio"
_KOREA_TIMEZONE = ZoneInfo("Asia/Seoul")


@contextmanager
def _remote_tracing_disabled() -> Iterator[None]:
    """Disable LangSmith/LangChain remote tracing while portfolio data is in use."""
    names = ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2")
    previous = {name: os.environ.get(name) for name in names}
    for name in names:
        os.environ[name] = "false"
    try:
        with tracing_context(enabled=False, parent=False):
            yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _now() -> datetime:
    return datetime.now(UTC)


def _today_kst(now: datetime | None = None) -> date:
    return (now or _now()).astimezone(_KOREA_TIMEZONE).date()


def _portfolio_tool_round_limit(configured_rounds: int, step_limit: int, analyst_count: int) -> int:
    per_analyst_steps = step_limit // analyst_count
    return min(configured_rounds, max(1, (per_analyst_steps - 1) // 2))


def _default_order_dates(today: date | None = None) -> tuple[date, date]:
    end = today or _today_kst()
    return end - timedelta(days=29), end


def _validate_request(
    orders_from: date | None,
    orders_to: date | None,
    symbols: list[str] | None,
    max_symbols: int,
) -> tuple[date, date, list[str]]:
    if not 1 <= max_symbols <= _MAX_SYMBOLS:
        raise typer.BadParameter(f"--max-symbols must be between 1 and {_MAX_SYMBOLS}.")
    today = _today_kst()
    if orders_from is not None:
        start = orders_from
        end = orders_to or today
    elif orders_to is not None:
        end = orders_to
        start = end - timedelta(days=29)
    else:
        start, end = _default_order_dates(today)
    if start > end:
        raise typer.BadParameter("--orders-from must be on or before --orders-to.")
    if (end - start).days >= _MAX_ORDER_DAYS:
        raise typer.BadParameter(f"The order date range must be at most {_MAX_ORDER_DAYS} days.")
    if end > today:
        raise typer.BadParameter("--orders-to cannot be in the future.")

    normalized = [symbol.strip().upper() for symbol in symbols or []]
    if len(normalized) > max_symbols:
        raise typer.BadParameter(f"At most {max_symbols} --symbol values may be selected.")
    if any(not _SYMBOL.fullmatch(symbol) for symbol in normalized):
        raise typer.BadParameter("Each --symbol must use letters, digits, '.' or '-'.")
    if len(set(normalized)) != len(normalized):
        raise typer.BadParameter("--symbol values must be unique.")
    return start, end, normalized


def _scenario_horizons_from_env() -> tuple[HorizonSpec, ...]:
    settings = (
        ("short", "TRADINGAGENTS_PORTFOLIO_SHORT_DAYS", 1, 20, "trading_days"),
        ("medium", "TRADINGAGENTS_PORTFOLIO_MEDIUM_MONTHS", 1, 6, "months"),
        ("long", "TRADINGAGENTS_PORTFOLIO_LONG_MONTHS", 6, 24, "months"),
    )
    horizons = []
    for name, env_name, default_minimum, default_maximum, unit in settings:
        value = os.environ.get(env_name)
        if value is None:
            minimum, maximum = default_minimum, default_maximum
        else:
            match = re.fullmatch(r"\s*([0-9]+)\s*-\s*([0-9]+)\s*", value)
            if match is None:
                raise typer.BadParameter(f"{env_name} must use MIN-MAX integer format.")
            minimum, maximum = (int(part) for part in match.groups())
        try:
            horizons.append(HorizonSpec(name, minimum, maximum, unit))
        except ValueError as exc:
            raise typer.BadParameter(f"Invalid {env_name}: {exc}") from None
        maximum_allowed = 250 if unit == "trading_days" else 120
        if maximum > maximum_allowed:
            raise typer.BadParameter(f"{env_name} cannot exceed {maximum_allowed}.")
    return tuple(horizons)


def _parse_order_date(value: str | None, option_name: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise typer.BadParameter(f"{option_name} must use YYYY-MM-DD format.") from None


def _request_scope(
    start: date,
    end: date,
    max_symbols: int,
    selected_symbols: list[str],
    explicit: bool,
) -> RequestScope:
    return RequestScope(
        orders_from=start,
        orders_to=end,
        transactions_from=None,
        max_pages_per_status=_ORDER_PAGE_LIMIT,
        max_transaction_pages=_TRANSACTION_PAGE_LIMIT,
        max_symbols=max_symbols,
        selected_symbols=selected_symbols,
        symbol_selection="explicit" if explicit else "all_returned_holdings",
    )


def _write_reports(report: PortfolioReport, output_dir: Path) -> tuple[Path, Path]:
    output_dir = output_dir.expanduser()
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = report.generated_at.strftime("%Y%m%dT%H%M%S%fZ")
    json_path = output_dir / f"portfolio_{report.mode}_{stamp}.json"
    markdown_path = output_dir / f"portfolio_{report.mode}_{stamp}.md"
    for path, content in (
        (json_path, report.model_dump_json(indent=2)),
        (markdown_path, render_markdown(report)),
    ):
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(content)
            output.write("\n")
    return json_path, markdown_path


def _finish_report(report: PortfolioReport, output_dir: Path) -> None:
    try:
        json_path, markdown_path = _write_reports(report, output_dir)
    except OSError:
        typer.echo("Could not save portfolio reports to the selected output directory.", err=True)
        raise typer.Exit(code=1) from None
    typer.echo(f"JSON report: {json_path}")
    typer.echo(f"Markdown report: {markdown_path}")
    typer.echo(f"Status: {report.status}")


def _demo_data(now: datetime) -> tuple[Holdings, tuple[BuyingPower, ...], Orders]:
    holdings = Holdings(
        holdings=(
            Holding(
                symbol="005930",
                name="Synthetic Electronics",
                market_country="KR",
                exchange="KRX",
                currency="KRW",
                quantity=Decimal("2"),
                last_price=Decimal("72000"),
                average_purchase_price=Decimal("68000"),
                purchase_amount=Decimal("136000"),
                market_value=Decimal("144000"),
                market_value_after_cost=Decimal("143500"),
                profit_loss=Decimal("8000"),
                profit_loss_after_cost=Decimal("7500"),
                retrieved_at=now,
            ),
            Holding(
                symbol="SYNTH",
                name="Synthetic Systems",
                market_country="US",
                exchange="NASDAQ",
                currency="USD",
                quantity=Decimal("3"),
                last_price=Decimal("42.5"),
                average_purchase_price=Decimal("40"),
                purchase_amount=Decimal("120"),
                market_value=Decimal("127.5"),
                market_value_after_cost=Decimal("126.8"),
                profit_loss=Decimal("7.5"),
                profit_loss_after_cost=Decimal("6.8"),
                retrieved_at=now,
            ),
        ),
        retrieved_at=now,
        coverage_warnings=("합성 예시는 KR/US 주식 두 종목만 포함합니다.",),
    )
    buying_power = (
        BuyingPower("KRW", Decimal("50000"), now),
        BuyingPower("USD", Decimal("25"), now),
    )
    orders = Orders(
        orders=(
            Order(
                order_id="SYNTHETIC-ORDER-1",
                symbol="SYNTH",
                market_country="US",
                exchange="NASDAQ",
                currency="USD",
                side="BUY",
                order_type="LIMIT",
                status="PARTIALLY_FILLED",
                price=Decimal("41"),
                quantity=Decimal("2"),
                order_amount=Decimal("82"),
                filled_quantity=Decimal("1"),
                average_filled_price=Decimal("41"),
                filled_amount=Decimal("41"),
                ordered_at=now - timedelta(days=1),
                canceled_at=None,
                filled_at=now,
                retrieved_at=now,
            ),
        ),
        retrieved_at=now,
        coverage_warnings=("합성 주문은 데모용 단일 예시입니다.",),
    )
    return holdings, buying_power, orders


def _demo_scenarios(holdings: Holdings) -> PortfolioScenarioReport:
    case = ScenarioCase(
        investment_rationale="합성 예시 데이터에 대한 설명용 조건부 시나리오입니다.",
        evidence=("합성 가격과 보유 수량만 사용했습니다.",),
        catalysts=("새로운 합성 실적 정보가 추가되는 경우",),
        risks=("합성 입력은 실제 시장 위험을 반영하지 않습니다.",),
        watch_conditions=("예시 가격 변동과 다음 데이터 갱신을 확인합니다.",),
        review_conditions=("데모 기간 종료 후 가정을 다시 검토합니다.",),
        invalidation=("합성 예시의 전제가 바뀌면 시나리오를 폐기합니다.",),
        portfolio_impact="실제 계좌나 투자 판단에 적용할 수 없는 설명용 값입니다.",
    )
    horizons = tuple(
        HorizonScenarios(
            name=horizon.name,
            window=(
                f"{horizon.minimum}-{horizon.maximum} 거래일"
                if horizon.unit == "trading_days"
                else f"{horizon.minimum}-{horizon.maximum}개월"
            ),
            upside=case,
            base=case,
            downside=case,
        )
        for horizon in DEFAULT_HORIZONS
    )
    research = tuple(
        SymbolResearchResult(
            symbol=holding.symbol,
            status="analyzed",
            analysis="합성 데모 자료이며 실시간 조사나 모델 추론을 수행하지 않았습니다.",
            market_country=holding.market_country or "US",
            exposures=(),
        )
        for holding in holdings.holdings
    )
    return PortfolioScenarioReport(
        status="partial",
        portfolio_analysis_status="partial",
        summary="아래 내용은 CLI 동작을 보여 주기 위한 합성 예시입니다.",
        horizons=horizons,
        symbol_research=research,
        symbols_researched=0,
        unmapped_holdings=0,
        omitted_symbols=0,
    )


@portfolio_app.command("demo")
def demo(
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", help="Report directory (default: ~/.tradingagents/portfolio)."),
    ] = _OUTPUT_DIR,
) -> None:
    """Write a portfolio report from fixed synthetic fixtures only."""
    now = _now()
    holdings, buying_power, orders = _demo_data(now)
    analytics = analyze_portfolio(
        holdings,
        buying_power,
        orders,
        as_of=now,
        stale_after=timedelta(hours=24),
    )
    start, end = _default_order_dates(_today_kst(now))
    report = build_portfolio_report(
        mode="demo",
        generated_at=now,
        request=_request_scope(start, end, 2, [row.symbol for row in holdings.holdings], True),
        analytics=analytics,
        holdings=holdings,
        scenarios=_demo_scenarios(holdings),
        caveats=[
            "합성 데모 데이터이며 실제 계좌·시장 자료가 아닙니다.",
            "데모 실행은 브로커, 데이터 공급자, LLM 또는 원격 tracing에 연결하지 않습니다.",
        ],
        extra_sources=[
            SourceReport(
                source="synthetic demo fixtures",
                available=True,
                retrieved_at=now,
                as_of=now,
                coverage_warnings=["고정된 합성 데이터입니다."],
            )
        ],
    )
    _finish_report(report, output_dir)


def _select_account(accounts: Accounts, account_ordinal: int | None) -> Account:
    if not accounts.accounts:
        raise typer.BadParameter("No active account was returned.")
    for index, _account in enumerate(accounts.accounts, start=1):
        account_type = re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]", " ", _account.account_type or ""))[:40]
        account_type = account_type or "유형 미제공"
        typer.echo(f"{index}. 계좌 ({account_type})")
    if account_ordinal is None:
        if not sys.stdin.isatty():
            raise typer.BadParameter("Pass --account-ordinal in non-interactive mode.")
        account_ordinal = typer.prompt("조회할 계좌 번호를 선택하세요", type=int)
    if account_ordinal < 1 or account_ordinal > len(accounts.accounts):
        raise typer.BadParameter("--account-ordinal is outside the displayed account list.")
    return accounts.accounts[account_ordinal - 1]


def _combine_orders(results: list[Orders], missing_statuses: list[str]) -> Orders | None:
    if not results:
        return None
    by_id: dict[str, Order] = {}
    duplicates_found = False
    for result in results:
        for order in result.orders:
            existing = by_id.get(order.order_id)
            if existing is None:
                by_id[order.order_id] = order
                continue
            duplicates_found = True
            existing_at = existing.retrieved_at
            order_at = order.retrieved_at
            if order_at is not None and (existing_at is None or order_at > existing_at):
                by_id[order.order_id] = order
    rows = tuple(by_id.values())
    timestamps = [result.retrieved_at for result in results if result.retrieved_at]
    warnings = [warning for result in results for warning in result.coverage_warnings]
    warnings.extend(f"{status} order history was unavailable." for status in missing_statuses)
    if duplicates_found:
        warnings.append("Duplicate order records across status queries were collapsed by orderId.")
    return Orders(
        orders=rows,
        retrieved_at=max(timestamps) if timestamps else None,
        has_more=any(result.has_more for result in results),
        coverage_warnings=tuple(dict.fromkeys(warnings)),
    )


def _fetch_portfolio(adapter, account: Account, start: date, end: date):
    failures: list[str] = []
    try:
        holdings = adapter.get_holdings(account.account_seq)
    except Exception as exc:
        holdings = None
        failures.append(f"holdings retrieval failed: {format_api_failure(exc)}")

    buying_power: list[BuyingPower] = []
    for currency in ("KRW", "USD"):
        try:
            buying_power.append(adapter.get_buying_power(account.account_seq, currency))
        except Exception as exc:
            failures.append(
                f"buying-power retrieval failed for {currency}: {format_api_failure(exc)}"
            )

    order_results: list[Orders] = []
    missing_statuses: list[str] = []
    for status in ("OPEN", "CLOSED"):
        try:
            order_results.append(
                adapter.get_orders(
                    account.account_seq,
                    status,
                    from_date=start,
                    to_date=end,
                )
            )
        except Exception as exc:
            missing_statuses.append(status)
            failures.append(
                f"{status.lower()} order-history retrieval failed: {format_api_failure(exc)}"
            )
    orders = _combine_orders(order_results, missing_statuses)

    try:
        transactions = adapter.get_transactions(account.account_seq)
    except Exception as exc:
        transactions = None
        failures.append(f"transactions retrieval failed: {format_api_failure(exc)}")

    try:
        exchange_rate = adapter.get_exchange_rate("USD", "KRW")
    except Exception as exc:
        exchange_rate = None
        failures.append(f"exchange-rate retrieval failed: {format_api_failure(exc)}")
    return holdings, tuple(buying_power), orders, transactions, exchange_rate, failures


def _market_symbols(holdings: Holdings | None, selected_symbols: list[str], limit: int) -> list[str]:
    available = holdings.holdings if holdings else ()
    candidates = selected_symbols or [row.symbol for row in available]
    output = []
    for candidate in candidates:
        symbol = candidate if isinstance(candidate, str) else None
        matching = next(
            (
                row for row in available
                if row.symbol.strip().upper() == (symbol or "").strip().upper()
                or map_market_symbol(row.symbol, row.market_country, row.exchange)
                == (symbol or "").strip().upper()
            ),
            None,
        )
        if matching and matching.market_country == "KR" and re.fullmatch(r"[0-9]{6}", matching.symbol):
            mapped = matching.symbol
        else:
            mapped = (
                map_market_symbol(matching.symbol, matching.market_country, matching.exchange)
                if matching else None
            )
        if mapped is None and symbol:
            korean = re.fullmatch(r"([0-9]{6})\.(KS|KQ)", symbol.upper())
            if korean:
                mapped = korean.group(1)
        if mapped is None and symbol:
            mapped = map_market_symbol(symbol, "US", None)
        if mapped is None and symbol:
            mapped_pair = _watchlist_symbol(symbol.upper())
            mapped = mapped_pair[0] if mapped_pair else None
        if mapped and mapped not in output:
            output.append(mapped)
        if len(output) >= limit:
            break
    return output


def _fetch_technical_analysis(adapter, symbols: list[str]):
    if not symbols:
        return (), [], []
    failures: list[str] = []
    quotes = {}
    try:
        quotes = {row.symbol: row for row in adapter.get_prices(symbols)}
    except Exception as exc:
        failures.append(f"market-price retrieval failed: {format_api_failure(exc)}")
    snapshots: list[TechnicalSnapshot] = []
    sources: list[SourceReport] = []
    for symbol in symbols:
        page = None
        try:
            page = adapter.get_candles(symbol, interval="1d", count=200, adjusted=True)
        except Exception as exc:
            failures.append(f"daily-candle retrieval failed for {symbol}: {format_api_failure(exc)}")
        quote = quotes.get(symbol)
        snapshots.append(analyze_daily_candles(symbol, page, quote))
        sources.append(
            SourceReport(
                source=f"Toss market data ({symbol})",
                available=quote is not None or page is not None,
                retrieved_at=max(
                    (value for value in (
                        quote.retrieved_at if quote else None,
                        page.retrieved_at if page else None,
                    ) if value is not None),
                    default=None,
                ),
                as_of=(quote.timestamp if quote and quote.timestamp else max((row.timestamp for row in page.candles), default=None) if page else None),
                coverage_warnings=(
                    ["가격·캔들 응답의 기준 시각은 각 제공 시각입니다."]
                    + (["현재가를 받지 못했습니다."] if quote is None else [])
                    + (["일봉 캔들을 받지 못했습니다."] if page is None or not page.candles else [])
                ),
            )
        )
    return tuple(snapshots), sources, failures


def _watchlist_symbol(symbol: str) -> tuple[str, str] | None:
    korean = re.fullmatch(r"([0-9]{6})\.(KS|KQ)", symbol)
    if korean:
        exchange = "KRX" if korean.group(2) == "KS" else "KOSDAQ"
        provider_symbol = map_market_symbol(korean.group(1), "KR", exchange)
        return (provider_symbol, "KR") if provider_symbol else None
    provider_symbol = map_market_symbol(symbol, "US", None)
    return (provider_symbol, "US") if provider_symbol else None


def _selected_holdings(
    holdings: Holdings | None, selected_symbols: list[str]
) -> tuple[Holdings, list[str], list[tuple[str, str]]]:
    base = holdings or Holdings((), retrieved_at=None)
    if not selected_symbols:
        return base, [], []

    selected_rows = []
    watchlist_symbols = []
    omissions = []
    for requested in selected_symbols:
        requested_upper = requested.upper()
        matching = [
            row
            for row in base.holdings
            if row.symbol.strip().upper() == requested_upper
            or map_market_symbol(row.symbol, row.market_country, row.exchange) == requested_upper
        ]
        if matching:
            selected_rows.extend(matching)
            continue
        watch_symbol = _watchlist_symbol(requested_upper)
        if watch_symbol is None:
            omissions.append(
                f"요청한 종목을 지원되는 보유·관심종목으로 매핑하지 못했습니다: {requested}"
            )
        else:
            watchlist_symbols.append(watch_symbol)

    selected_rows = list(dict.fromkeys(selected_rows))
    return (
        Holdings(
            holdings=tuple(selected_rows),
            retrieved_at=base.retrieved_at,
            as_of=base.as_of,
            coverage_warnings=base.coverage_warnings,
        ),
        omissions,
        watchlist_symbols,
    )


def _build_symbol_research_graph(analysts):
    from langchain_core.messages import RemoveMessage
    from langgraph.graph import END, START, StateGraph

    from tradingagents.agents.state import AgentState

    workflow = StateGraph(AgentState)
    if not analysts:
        raise ValueError("at least one symbol research analyst is required")

    def clear_analyst_messages(state):
        messages = state.get("messages", ())
        return {"messages": [RemoveMessage(id=message.id) for message in messages[1:]]}

    for index, (name, analyst, tools) in enumerate(analysts):
        analyst_node = f"{name}_analyst"
        tool_node = f"{name}_tools"
        clear_node = f"{name}_clear"
        next_node = f"{analysts[index + 1][0]}_analyst" if index + 1 < len(analysts) else END
        workflow.add_node(analyst_node, analyst)
        workflow.add_node(tool_node, tools)
        workflow.add_node(clear_node, clear_analyst_messages)

        def route(state, *, _tool_node=tool_node, _clear_node=clear_node):
            messages = state.get("messages", ())
            return _tool_node if messages and messages[-1].tool_calls else _clear_node

        workflow.add_conditional_edges(analyst_node, route, [tool_node, clear_node])
        workflow.add_edge(tool_node, analyst_node)
        workflow.add_edge(clear_node, next_node)
    workflow.add_edge(START, f"{analysts[0][0]}_analyst")
    return workflow.compile()


def _trim_analyst_section(value: str) -> str:
    if len(value) <= _ANALYST_SECTION_CHARS:
        return value
    head = 1500
    tail = _ANALYST_SECTION_CHARS - head - len("\n[…중략…]\n")
    return f"{value[:head]}\n[…중략…]\n{value[-tail:]}"


def _portfolio_decision_context(holdings: Holdings | None) -> PortfolioContext | None:
    """Project known positions into the graph without carrying broker/account data."""
    if holdings is None:
        return None
    positions = []
    for holding in holdings.holdings:
        ticker = map_market_symbol(
            holding.symbol, holding.market_country, holding.exchange
        )
        if ticker is None or not holding.quantity.is_finite():
            continue
        quantity = float(holding.quantity)
        if not math.isfinite(quantity):
            continue
        average_price = holding.average_purchase_price
        average_value = float(average_price) if average_price is not None and average_price.is_finite() else None
        positions.append(
            Position(
                ticker=ticker,
                quantity=quantity,
                average_price=average_value if average_value is None or math.isfinite(average_value) else None,
                currency=holding.currency,
            )
        )
    # Toss buying power is not an actual cash balance, so cash is deliberately unknown.
    return PortfolioContext(cash=None, currency=None, positions=positions)


def _make_scenario_workflow(
    max_symbols: int,
    horizons: tuple[HorizonSpec, ...] = DEFAULT_HORIZONS,
    *,
    full_workflow: bool = False,
    portfolio_context: PortfolioContext | None = None,
) -> tuple[PortfolioScenarioWorkflow, list[TradingDecisionResult]]:
    from langgraph.graph import END, START, StateGraph

    from tradingagents.default_config import DEFAULT_CONFIG

    if full_workflow:
        from tradingagents.agents.rating import run_rating
        from tradingagents.dataflows.config import run_config
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        selected_analysts = ("market", "social", "news", "fundamentals")
        graph_config = copy.deepcopy(DEFAULT_CONFIG)
        graph_config["max_tool_rounds"] = _portfolio_tool_round_limit(
            graph_config["max_tool_rounds"], _SYMBOL_RESEARCH_STEP_LIMIT, len(selected_analysts)
        )
        graph = TradingAgentsGraph(
            selected_analysts=selected_analysts,
            config=graph_config,
        )
        # Portfolio reports must not read or write the per-symbol decision memory.
        full_graph = graph.graph_setup.setup_graph(selected_analysts, memory_node=None).compile()
        decisions: list[TradingDecisionResult] = []

        def analyze_full_workflow(research_input) -> str:
            ticker = research_input.symbol
            trade_date = _today_kst().isoformat()
            initial_state = graph.create_run_state(
                ticker,
                trade_date,
                asset_type="stock",
                portfolio=portfolio_context,
            )
            with run_config(graph.config):
                state = full_graph.invoke(
                    initial_state,
                    config={"recursion_limit": graph.config["max_recur_limit"]},
                )
            reports = []
            for title, field in (
                ("Market research", "market_report"),
                ("Sentiment research", "sentiment_report"),
                ("News research", "news_report"),
                ("Fundamentals research", "fundamentals_report"),
            ):
                value = state.get(field)
                if isinstance(value, str) and value.strip():
                    reports.append(f"## {title}\n{_trim_analyst_section(value.strip())}")
            if not reports:
                raise RuntimeError("Full TradingAgents research was unavailable.")

            risk_state = state.get("risk_debate_state") or {}
            risk_debate = risk_state.get("history") or "\n\n".join(
                value
                for key in (
                    "aggressive_history",
                    "conservative_history",
                    "neutral_history",
                )
                if isinstance((value := risk_state.get(key)), str) and value.strip()
            )
            trader_plan = state.get("trader_investment_plan")
            final_decision = state.get("final_trade_decision")
            if not all(
                isinstance(value, str) and value.strip()
                for value in (trader_plan, risk_debate, final_decision)
            ):
                raise RuntimeError("Trader, Risk, or final decision output was unavailable.")
            decisions.append(
                TradingDecisionResult(
                    symbol=ticker,
                    trader_plan=sanitize_portfolio_text(
                        trader_plan, limit=5000
                    ),
                    risk_debate=sanitize_portfolio_text(risk_debate, limit=7000),
                    final_decision=sanitize_portfolio_text(
                        final_decision, limit=5000
                    ),
                    rating=run_rating(state),
                )
            )
            return "\n\n".join(reports)

        workflow = PortfolioScenarioWorkflow(
            analyze_full_workflow,
            graph.quick_thinking_llm,
            ScenarioConfig(
                max_holdings=max_symbols,
                max_symbol_researches=max_symbols,
                horizons=horizons,
            ),
        )
        return workflow, decisions

    from tradingagents.agents import (
        create_fundamentals_analyst,
        create_market_analyst,
        create_news_analyst,
    )
    from tradingagents.agents.state import AgentState
    from tradingagents.graph.analyst_execution import build_analyst_execution_plan
    from tradingagents.graph.setup import _analyst_graph
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph = TradingAgentsGraph(
        selected_analysts=("market", "news", "fundamentals"),
        config=copy.deepcopy(DEFAULT_CONFIG),
    )
    plan = build_analyst_execution_plan(("market", "news", "fundamentals"))
    analyst_factories = {
        "market": create_market_analyst,
        "news": create_news_analyst,
        "fundamentals": create_fundamentals_analyst,
    }
    # Keep the total number of tool/agent steps below the portfolio symbol cap.
    max_tool_rounds = _portfolio_tool_round_limit(
        graph.config["max_tool_rounds"], _SYMBOL_RESEARCH_STEP_LIMIT, len(plan.specs)
    )
    research = StateGraph(AgentState)
    for index, spec in enumerate(plan.specs):
        node = _analyst_graph(
            spec,
            analyst_factories[spec.key](graph.quick_thinking_llm),
            max_tool_rounds,
        )
        research.add_node(spec.agent_node, node)
        research.add_edge(START if index == 0 else plan.specs[index - 1].agent_node, spec.agent_node)
    research.add_edge(plan.specs[-1].agent_node, END)
    research_graph = research.compile()

    def analyze_symbol(research_input) -> str:
        ticker = research_input.symbol
        trade_date = _today_kst().isoformat()
        instrument_context = graph.resolve_instrument_context(ticker, "stock")
        initial_state = graph.propagator.create_initial_state(
            ticker,
            trade_date,
            asset_type="stock",
            past_context="",
            instrument_context=instrument_context,
        )
        state = research_graph.invoke(
            initial_state,
            config={"recursion_limit": _SYMBOL_RESEARCH_STEP_LIMIT},
        )
        reports = []
        for title, field in (
            ("Market research", "market_report"),
            ("News research", "news_report"),
            ("Fundamentals research", "fundamentals_report"),
        ):
            value = state.get(field)
            if isinstance(value, str) and value.strip():
                reports.append(f"## {title}\n{_trim_analyst_section(value.strip())}")
        if not reports:
            raise RuntimeError("Market, news, and fundamentals research were unavailable.")
        return "\n\n".join(reports)

    return (
        PortfolioScenarioWorkflow(
            analyze_symbol,
            graph.quick_thinking_llm,
            ScenarioConfig(
                max_holdings=max_symbols,
                max_symbol_researches=max_symbols,
                horizons=horizons,
            ),
        ),
        [],
    )


def _run_scenarios(
    holdings: Holdings | None,
    analytics: PortfolioAnalytics,
    max_symbols: int,
    selected_symbols: list[str],
    horizons: tuple[HorizonSpec, ...] = DEFAULT_HORIZONS,
    *,
    full_workflow: bool = False,
) -> tuple[PortfolioScenarioReport | None, list[str]]:
    if holdings is None and not selected_symbols:
        return None, []
    target_holdings, omissions, watchlist_symbols = _selected_holdings(
        holdings, selected_symbols
    )
    if not target_holdings.holdings and not watchlist_symbols:
        return None, omissions
    workflow, decisions = _make_scenario_workflow(
        max_symbols,
        horizons,
        full_workflow=full_workflow,
        portfolio_context=_portfolio_decision_context(holdings),
    )
    report = workflow.invoke(
        target_holdings,
        portfolio_analysis=analytics,
        watchlist_symbols=watchlist_symbols,
    )
    if decisions:
        report = replace(report, trading_decisions=tuple(decisions))
    return report, omissions


@portfolio_app.command("live")
def live(
    account_ordinal: Annotated[
        int | None,
        typer.Option("--account-ordinal", min=1, help="Select the account by its displayed 1-based ordinal."),
    ] = None,
    orders_from: Annotated[
        str | None,
        typer.Option("--orders-from", help="Order history start date (YYYY-MM-DD; maximum 90-day window)."),
    ] = None,
    orders_to: Annotated[
        str | None,
        typer.Option("--orders-to", help="Order history end date (YYYY-MM-DD; cannot be in the future)."),
    ] = None,
    symbol: Annotated[
        list[str] | None,
        typer.Option(
            "--symbol",
            help="Select a held symbol or KR/US watchlist ticker; repeat up to --max-symbols times.",
        ),
    ] = None,
    max_symbols: Annotated[
        int,
        typer.Option(
            "--max-symbols",
            min=1,
            max=_MAX_SYMBOLS,
            help=f"Maximum number of symbols sent to research and analysis (1-{_MAX_SYMBOLS}).",
        ),
    ] = _MAX_SYMBOLS,
    scenarios: Annotated[
        bool,
        typer.Option("--scenarios/--no-scenarios", help="Run per-symbol TradingAgents research and portfolio scenarios."),
    ] = True,
    full_workflow: Annotated[
        bool,
        typer.Option(
            "--full-workflow",
            help="Include Bull/Bear debate, Trader, Risk and Portfolio Manager decisions; increases LLM usage.",
        ),
    ] = False,
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", help="Report directory (default: ~/.tradingagents/portfolio)."),
    ] = _OUTPUT_DIR,
) -> None:
    """Query Toss portfolio data after an explicit operator read-only acknowledgement."""
    if full_workflow and not scenarios:
        raise typer.BadParameter("--full-workflow requires --scenarios.")
    if os.environ.get("TOSS_BROKER_READ_ONLY_VERIFIED") != _ACK_VALUE:
        raise typer.BadParameter(
            "Live mode requires TOSS_BROKER_READ_ONLY_VERIFIED=I_ACKNOWLEDGE_READ_ONLY. "
            "This records your own verification; it does not set broker permissions."
        )
    client_id = os.environ.get("TOSS_CLIENT_ID")
    client_secret = os.environ.get("TOSS_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise typer.BadParameter("Set TOSS_CLIENT_ID and TOSS_CLIENT_SECRET in the environment.")
    parsed_from = _parse_order_date(orders_from, "--orders-from")
    parsed_to = _parse_order_date(orders_to, "--orders-to")
    start, end, selected_symbols = _validate_request(
        parsed_from, parsed_to, symbol, max_symbols
    )
    horizons = _scenario_horizons_from_env() if scenarios else DEFAULT_HORIZONS

    from tradingagents.portfolio.toss import TossPortfolioAdapter

    with _remote_tracing_disabled():
        adapter = TossPortfolioAdapter(client_id, client_secret)
        try:
            accounts = adapter.get_accounts()
        except Exception as exc:
            typer.echo(
                "Account-list retrieval failed "
                f"({format_api_failure(exc)}); no portfolio report was written.",
                err=True,
            )
            raise typer.Exit(code=1) from None
        try:
            account = _select_account(accounts, account_ordinal)
        except typer.BadParameter as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from None

        (
            holdings,
            buying_power,
            orders,
            transactions,
            exchange_rate,
            failures,
        ) = _fetch_portfolio(adapter, account, start, end)
        now = _now()
        fx_rate = None
        if exchange_rate is not None:
            with localcontext() as context:
                context.prec = 28
                fx_rate = Decimal(1) / exchange_rate.mid_rate
        analytics = analyze_portfolio(
            holdings,
            buying_power,
            orders,
            transactions,
            fx_rate=fx_rate,
            fx_timestamp=exchange_rate.valid_from if exchange_rate else None,
            fx_valid_until=exchange_rate.valid_until if exchange_rate else None,
            fx_retrieved_at=exchange_rate.retrieved_at if exchange_rate else None,
            as_of=now,
            stale_after=timedelta(hours=24),
        )
        scenario_report = None
        omissions: list[str] = []
        if scenarios:
            drain_source_failures()
            try:
                scenario_report, scenario_omissions = _run_scenarios(
                    holdings,
                    analytics,
                    max_symbols,
                    selected_symbols,
                    horizons,
                    full_workflow=full_workflow,
                )
                omissions.extend(scenario_omissions)
            except Exception as exc:
                failures.append(f"scenario analysis failed: {format_api_failure(exc)}")
            finally:
                counts = Counter(
                    (method, format_api_failure(error))
                    for method, error in drain_source_failures()
                )
                failures.extend(
                    f"{method} data retrieval failed: {label} ({count}회)"
                    for (method, label), count in counts.items()
                )
        if scenario_report is not None and not selected_symbols:
            selected_symbols = [row.symbol for row in scenario_report.symbol_research]
        market_symbols = _market_symbols(holdings, selected_symbols, max_symbols)
        technical_analysis, market_sources, market_failures = _fetch_technical_analysis(
            adapter, market_symbols
        )
        failures.extend(market_failures)
        snapshot_comparison: SnapshotComparison | None = None
        if holdings is not None and len(buying_power) == 2:
            try:
                account_ordinal_selected = accounts.accounts.index(account) + 1
                snapshot_comparison = append_portfolio_snapshot(
                    holdings,
                    buying_power,
                    account_ordinal=account_ordinal_selected,
                    captured_at=now,
                )
            except (OSError, ValueError):
                failures.append("local portfolio snapshot could not be saved.")
        report = build_portfolio_report(
            mode="live",
            generated_at=now,
            request=_request_scope(
                start,
                end,
                max_symbols,
                selected_symbols,
                bool(symbol),
            ),
            analytics=analytics,
            holdings=holdings,
            scenarios=scenario_report,
            technical_analysis=technical_analysis,
            snapshot_comparison=snapshot_comparison,
            source_failures=failures,
            omissions=omissions,
            caveats=[
                "브로커 어댑터는 조회용 HTTP 요청만 보냅니다. API 키 단위 읽기 전용 권한을 보장하지 않습니다.",
                "금융 분석 중 LangSmith/LangChain 원격 tracing을 비활성화했습니다.",
                "주문 요약은 조회된 기록이며 체결 원장이나 실현 손익으로 해석할 수 없습니다.",
                *(
                    [
                        "전체 TradingAgents 결정 그래프를 종목별로 실행했습니다. Trader·Risk·Portfolio Manager 결과는 분석 제안이며 주문을 생성하거나 실행하지 않습니다."
                    ]
                    if full_workflow
                    else []
                ),
            ],
            extra_sources=[
                SourceReport(
                    source="Toss Securities account list",
                    available=True,
                    retrieved_at=accounts.retrieved_at,
                    as_of=None,
                    coverage_warnings=list(accounts.coverage_warnings),
                ),
                *market_sources,
            ],
        )
    _finish_report(report, output_dir)
