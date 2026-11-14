"""Schema-validated JSON and Korean Markdown portfolio reports."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from tradingagents.api_diagnostics import APIFailure, format_api_failure
from tradingagents.portfolio.analytics import PortfolioAnalytics
from tradingagents.portfolio.history import SnapshotComparison
from tradingagents.portfolio.models import Holdings, HoldingsSummary
from tradingagents.portfolio.scenarios import (
    PortfolioScenarioReport,
    sanitize_portfolio_text,
)
from tradingagents.portfolio.technical import TechnicalSnapshot


class _ReportModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RequestScope(_ReportModel):
    orders_from: date
    orders_to: date
    transactions_from: date | None = None
    transactions_to: date | None = None
    max_pages_per_status: int
    max_transaction_pages: int = 10
    max_symbols: int
    selected_symbols: list[str]
    symbol_selection: Literal["all_returned_holdings", "explicit"]


class UnitDescriptions(_ReportModel):
    money: str
    quantity: str
    weight: str
    fx: str


class SourceReport(_ReportModel):
    source: str
    available: bool
    retrieved_at: datetime | None
    as_of: datetime | None
    coverage_warnings: list[str]


class PositionReport(_ReportModel):
    symbol: str
    provider_symbol: str | None
    market_country: str | None
    currency: str | None
    quantity: Decimal
    last_price: Decimal | None
    market_value: Decimal | None
    market_value_source: str | None
    purchase_amount: Decimal | None
    purchase_amount_source: str | None
    profit_loss: Decimal | None
    profit_loss_source: str | None
    profit_loss_after_cost: Decimal | None
    profit_loss_after_cost_source: str | None
    profit_loss_rate: Decimal | None
    profit_loss_rate_after_cost: Decimal | None
    daily_profit_loss: Decimal | None
    daily_profit_loss_rate: Decimal | None
    commission: Decimal | None
    tax: Decimal | None
    security_weight: Decimal | None
    currency_portfolio_weight: Decimal | None
    retrieved_at: datetime | None
    stale: bool | None
    included_in_totals: bool
    unknowns: list[str]


class CurrencyReport(_ReportModel):
    currency: str
    market_value_total: Decimal | None
    purchase_amount_total: Decimal | None
    profit_loss_total: Decimal | None
    profit_loss_after_cost_total: Decimal | None
    buying_power_total: Decimal | None
    total_value_with_buying_power: Decimal | None
    market_value_complete: bool
    purchase_amount_complete: bool
    profit_loss_complete: bool
    profit_loss_after_cost_complete: bool
    buying_power_complete: bool
    represented_scope_complete: bool
    position_count: int
    market_value_missing_count: int
    purchase_amount_missing_count: int
    profit_loss_missing_count: int


class OrderStatusReport(_ReportModel):
    status: str | None
    count: int
    ordered_quantity_total: Decimal | None
    ordered_quantity_missing_count: int
    filled_quantity_total: Decimal | None
    filled_quantity_missing_count: int


class OrderSideReport(_ReportModel):
    side: str | None
    count: int


class OrdersReport(_ReportModel):
    available: bool
    count: int | None
    by_status: list[OrderStatusReport]
    by_side: list[OrderSideReport]
    ordered_quantity_total: Decimal | None
    ordered_quantity_missing_count: int | None
    filled_quantity_total: Decimal | None
    filled_quantity_missing_count: int | None
    retrieved_at: datetime | None
    has_more: bool | None
    coverage_warnings: list[str]


class CountByReport(_ReportModel):
    key: str
    count: int


class TransactionsReport(_ReportModel):
    available: bool
    count: int | None
    by_type: list[CountByReport]
    by_asset_class: list[CountByReport]
    settled_count: int | None
    unsettled_count: int | None
    cancellation_count: int | None
    retrieved_at: datetime | None
    has_more: bool | None
    coverage_warnings: list[str]
    realized_profit_loss: list[RealizedProfitLossReport] = Field(default_factory=list)


class RealizedProfitLossReport(_ReportModel):
    currency: str
    before_cost: Decimal | None
    after_cost: Decimal | None
    complete: bool
    method: str
    caveat: str | None


class CurrencyAmountsReport(_ReportModel):
    krw: Decimal | None
    usd: Decimal | None


class HoldingsSummaryReport(_ReportModel):
    total_purchase_amount: CurrencyAmountsReport
    market_value: CurrencyAmountsReport
    market_value_after_cost: CurrencyAmountsReport
    profit_loss: CurrencyAmountsReport
    profit_loss_after_cost: CurrencyAmountsReport
    profit_loss_rate: Decimal | None
    profit_loss_rate_after_cost: Decimal | None
    daily_profit_loss: CurrencyAmountsReport
    daily_profit_loss_rate: Decimal | None


class TechnicalAnalysisReport(_ReportModel):
    symbol: str
    currency: str | None
    price: Decimal | None
    latest_close: Decimal | None
    candle_count: int
    price_as_of: datetime | None
    candle_as_of: datetime | None
    return_1d: Decimal | None
    return_5d: Decimal | None
    return_20d: Decimal | None
    sma_20: Decimal | None
    sma_50: Decimal | None
    sma_200: Decimal | None
    rsi_14: Decimal | None
    macd: Decimal | None
    macd_signal: Decimal | None
    atr_14: Decimal | None
    volume_ratio_20: Decimal | None
    caveat: str | None


class SnapshotComparisonReport(_ReportModel):
    previous_at: datetime | None
    change_by_currency: dict[str, Decimal]
    caveat: str | None


class FXReport(_ReportModel):
    rate: Decimal | None
    timestamp: datetime | None
    valid_until: datetime | None
    source_currency: str
    target_currency: str
    applied: bool
    stale: bool | None


class ConvertedTotalsReport(_ReportModel):
    currency: str
    market_value_total: Decimal | None
    purchase_amount_total: Decimal | None
    profit_loss_total: Decimal | None
    buying_power_total: Decimal | None
    portfolio_value_total: Decimal | None


class ExposureReport(_ReportModel):
    currency: str | None
    position_count: int
    quantity: Decimal | None
    market_value: Decimal | None


class SymbolResearchReport(_ReportModel):
    symbol: str
    status: str
    analysis: str | None
    market_country: str
    portfolio_relation: Literal["holding", "watchlist"]
    exposures: list[ExposureReport]
    failure_category: str | None = None
    retryable: bool | None = None


class TradingDecisionReport(_ReportModel):
    symbol: str
    trader_plan: str
    risk_debate: str
    final_decision: str
    rating: str


class ScenarioCaseReport(_ReportModel):
    investment_rationale: str
    evidence: list[str]
    catalysts: list[str]
    risks: list[str]
    watch_conditions: list[str]
    review_conditions: list[str]
    invalidation: list[str]
    portfolio_impact: str


class HorizonReport(_ReportModel):
    name: str
    window: str
    upside: ScenarioCaseReport
    base: ScenarioCaseReport
    downside: ScenarioCaseReport


class ScenarioReport(_ReportModel):
    status: str
    portfolio_analysis_status: str
    summary: str | None
    horizons: list[HorizonReport]
    symbol_research: list[SymbolResearchReport]
    symbols_researched: int
    unmapped_holdings: int
    omitted_symbols: int
    trading_decisions: list[TradingDecisionReport] = Field(default_factory=list)


class PortfolioReport(_ReportModel):
    schema_version: Literal["1.1"]
    mode: Literal["demo", "live"]
    status: Literal["complete", "partial", "unavailable"]
    generated_at: datetime
    request: RequestScope
    units: UnitDescriptions
    sources: list[SourceReport]
    account_wide_coverage: str
    positions: list[PositionReport]
    currencies: list[CurrencyReport]
    orders: OrdersReport
    transactions: TransactionsReport
    fx: FXReport | None
    converted_totals: ConvertedTotalsReport | None
    scenarios: ScenarioReport | None
    source_failures: list[str]
    omissions: list[str]
    caveats: list[str]
    holdings_summary: HoldingsSummaryReport | None = None
    technical_analysis: list[TechnicalAnalysisReport] = Field(default_factory=list)
    snapshot_comparison: SnapshotComparisonReport | None = None


def build_portfolio_report(
    *,
    mode: Literal["demo", "live"],
    generated_at: datetime,
    request: RequestScope,
    analytics: PortfolioAnalytics,
    holdings: Holdings | None,
    scenarios: PortfolioScenarioReport | None,
    source_failures: list[str] | None = None,
    omissions: list[str] | None = None,
    caveats: list[str] | None = None,
    extra_sources: list[SourceReport] | None = None,
    technical_analysis: tuple[TechnicalSnapshot, ...] | list[TechnicalSnapshot] = (),
    snapshot_comparison: SnapshotComparison | None = None,
) -> PortfolioReport:
    """Project the analytics interfaces into a strict, presentation-safe schema."""
    sources = [
        SourceReport(
            source=_display_source_name(source.source),
            available=source.available,
            retrieved_at=source.retrieved_at,
            as_of=source.as_of,
            coverage_warnings=list(source.coverage_warnings),
        )
        for source in analytics.sources
    ]
    sources.extend(extra_sources or [])
    if scenarios is not None and any(
        row.status == "analyzed" for row in scenarios.symbol_research
    ):
        sources.append(
            SourceReport(
                source="TradingAgents analyst research output",
                available=True,
                retrieved_at=generated_at,
                as_of=None,
                coverage_warnings=[
                    "자료별 제공자와 기준 시각은 조사 본문에 확인되는 경우에만 기재했습니다.",
                    "이 시각은 분석 생성 시각이며 개별 시장 데이터의 기준 시각을 뜻하지 않습니다.",
                ],
            )
        )

    order_analytics = analytics.orders
    order_report = OrdersReport(
        available=order_analytics is not None,
        count=order_analytics.count if order_analytics else None,
        by_status=[
            OrderStatusReport(
                status=row.status,
                count=row.count,
                ordered_quantity_total=row.ordered_quantity_total,
                ordered_quantity_missing_count=row.ordered_quantity_missing_count,
                filled_quantity_total=row.filled_quantity_total,
                filled_quantity_missing_count=row.filled_quantity_missing_count,
            )
            for row in order_analytics.by_status
        ]
        if order_analytics
        else [],
        by_side=[OrderSideReport(side=row.side, count=row.count) for row in order_analytics.by_side]
        if order_analytics
        else [],
        ordered_quantity_total=(order_analytics.ordered_quantity_total if order_analytics else None),
        ordered_quantity_missing_count=(
            order_analytics.ordered_quantity_missing_count if order_analytics else None
        ),
        filled_quantity_total=(
            order_analytics.filled_quantity_total if order_analytics else None
        ),
        filled_quantity_missing_count=(
            order_analytics.filled_quantity_missing_count if order_analytics else None
        ),
        retrieved_at=order_analytics.retrieved_at if order_analytics else None,
        has_more=order_analytics.has_more if order_analytics else None,
        coverage_warnings=list(order_analytics.coverage_warnings) if order_analytics else [],
    )
    transaction_analytics = analytics.transactions
    transaction_report = TransactionsReport(
        available=transaction_analytics is not None,
        count=transaction_analytics.count if transaction_analytics else None,
        by_type=[
            CountByReport(key=row.key, count=row.count)
            for row in transaction_analytics.by_type
        ]
        if transaction_analytics
        else [],
        by_asset_class=[
            CountByReport(key=row.key, count=row.count)
            for row in transaction_analytics.by_asset_class
        ]
        if transaction_analytics
        else [],
        settled_count=transaction_analytics.settled_count if transaction_analytics else None,
        unsettled_count=transaction_analytics.unsettled_count if transaction_analytics else None,
        cancellation_count=transaction_analytics.cancellation_count if transaction_analytics else None,
        retrieved_at=transaction_analytics.retrieved_at if transaction_analytics else None,
        has_more=transaction_analytics.has_more if transaction_analytics else None,
        coverage_warnings=(
            list(transaction_analytics.coverage_warnings) if transaction_analytics else []
        ),
        realized_profit_loss=[
            RealizedProfitLossReport.model_validate(row.__dict__)
            for row in transaction_analytics.realized_profit_loss
        ] if transaction_analytics else [],
    )

    scenario_report = None
    if scenarios is not None:
        scenario_report = ScenarioReport(
            status=scenarios.status,
            portfolio_analysis_status=scenarios.portfolio_analysis_status,
            summary=scenarios.summary,
            horizons=[
                HorizonReport(
                    name=row.name,
                    window=row.window,
                    upside=ScenarioCaseReport.model_validate(row.upside.__dict__),
                    base=ScenarioCaseReport.model_validate(row.base.__dict__),
                    downside=ScenarioCaseReport.model_validate(row.downside.__dict__),
                )
                for row in scenarios.horizons
            ],
            symbol_research=[
                SymbolResearchReport(
                    symbol=row.symbol,
                    status=row.status,
                    analysis=row.analysis,
                    market_country=row.market_country,
                    portfolio_relation=row.portfolio_relation,
                    exposures=[ExposureReport.model_validate(exposure.__dict__) for exposure in row.exposures],
                    failure_category=row.failure_category,
                    retryable=row.retryable,
                )
                for row in scenarios.symbol_research
            ],
            trading_decisions=[
                TradingDecisionReport(
                    symbol=row.symbol,
                    trader_plan=sanitize_portfolio_text(row.trader_plan, limit=5000),
                    risk_debate=sanitize_portfolio_text(row.risk_debate, limit=7000),
                    final_decision=sanitize_portfolio_text(row.final_decision, limit=5000),
                    rating=sanitize_portfolio_text(row.rating, limit=40),
                )
                for row in scenarios.trading_decisions
            ],
            symbols_researched=scenarios.symbols_researched,
            unmapped_holdings=scenarios.unmapped_holdings,
            omitted_symbols=scenarios.omitted_symbols,
        )

    failures = source_failures or []
    report_omissions = list(omissions or [])
    report_caveats = list(caveats or [])
    if scenarios is not None:
        if scenarios.unmapped_holdings:
            report_omissions.append(f"{scenarios.unmapped_holdings}개 보유 종목은 분석 심볼로 매핑되지 않았습니다.")
        if scenarios.omitted_symbols:
            report_omissions.append(f"분석 상한으로 {scenarios.omitted_symbols}개 심볼을 생략했습니다.")
    if order_analytics is not None and order_analytics.has_more:
        report_omissions.append("주문 조회 결과에 다음 페이지가 있어 일부 주문이 빠졌을 수 있습니다.")
    if transaction_analytics is not None and transaction_analytics.has_more:
        report_omissions.append("거래내역 조회 결과에 다음 페이지가 있어 일부 거래가 빠졌을 수 있습니다.")
    if failures:
        report_caveats.append("일부 데이터 조회에 실패해 결과가 부분적입니다.")
    if not failures and analytics.account_wide_coverage == "complete" and scenarios is not None:
        status: Literal["complete", "partial", "unavailable"] = (
            "complete" if scenarios.status == "complete" else "partial"
        )
    elif (
        holdings is None
        and not analytics.buying_power
        and analytics.orders is None
        and analytics.transactions is None
    ):
        status = "unavailable"
    else:
        status = "partial"

    return PortfolioReport.model_validate(
        {
            "schema_version": "1.1",
            "mode": mode,
            "status": status,
            "generated_at": generated_at,
            "request": request,
            "units": UnitDescriptions(
                money="통화별 금액이며 서로 다른 통화를 합산하지 않습니다.",
                quantity="주식 수량 또는 제공자가 정의한 수량 단위입니다.",
                weight="같은 통화 범위 내 비중이며 자료가 불완전하면 null입니다.",
                fx="Toss 참고 매매기준율의 역수로 KRW를 USD로 환산하며, 유효기간 밖 환율은 적용하지 않습니다.",
            ),
            "sources": sources,
            "account_wide_coverage": analytics.account_wide_coverage,
            "positions": [
                PositionReport.model_validate(row.__dict__) for row in analytics.positions
            ],
            "currencies": [
                CurrencyReport.model_validate(row.__dict__) for row in analytics.currencies
            ],
            "orders": order_report,
            "transactions": transaction_report,
            "fx": FXReport.model_validate(analytics.fx.__dict__) if analytics.fx else None,
            "converted_totals": (
                ConvertedTotalsReport.model_validate(analytics.converted_totals.__dict__)
                if analytics.converted_totals
                else None
            ),
            "scenarios": scenario_report,
            "source_failures": failures,
            "omissions": report_omissions,
            "caveats": report_caveats + list(analytics.coverage_warnings) + list(analytics.unknowns),
            "holdings_summary": _holdings_summary_report(analytics.holdings_summary),
            "technical_analysis": [
                TechnicalAnalysisReport.model_validate(row.__dict__)
                for row in technical_analysis
            ],
            "snapshot_comparison": (
                SnapshotComparisonReport.model_validate(snapshot_comparison.__dict__)
                if snapshot_comparison is not None else None
            ),
        }
    )


def _holdings_summary_report(summary: HoldingsSummary | None) -> HoldingsSummaryReport | None:
    if summary is None:
        return None
    return HoldingsSummaryReport(
        total_purchase_amount=_currency_amount_report(summary.total_purchase_amount),
        market_value=_currency_amount_report(summary.market_value),
        market_value_after_cost=_currency_amount_report(summary.market_value_after_cost),
        profit_loss=_currency_amount_report(summary.profit_loss),
        profit_loss_after_cost=_currency_amount_report(summary.profit_loss_after_cost),
        profit_loss_rate=summary.profit_loss_rate,
        profit_loss_rate_after_cost=summary.profit_loss_rate_after_cost,
        daily_profit_loss=_currency_amount_report(summary.daily_profit_loss),
        daily_profit_loss_rate=summary.daily_profit_loss_rate,
    )


def _currency_amount_report(amounts) -> CurrencyAmountsReport:
    return CurrencyAmountsReport(krw=amounts.krw, usd=amounts.usd)


def render_markdown(report: PortfolioReport) -> str:
    """Render a Korean summary with source times, scope and data limits."""
    lines = [
        "# 포트폴리오 분석 보고서",
        "",
        f"- 모드: `{report.mode}`",
        f"- 결과 상태: `{report.status}`",
        f"- 생성 시각: {report.generated_at.isoformat()}",
        "",
        "## 요청 범위",
        "",
        f"- 주문 기간: {report.request.orders_from.isoformat()} ~ {report.request.orders_to.isoformat()}",
        f"- 거래내역 기간: {'전체 제공 이력' if report.request.transactions_from is None and report.request.transactions_to is None else report.request.transactions_from.isoformat() if report.request.transactions_from else '시작일 미지정'} ~ {report.request.transactions_to.isoformat() if report.request.transactions_to else '상한 없음 (미결제 포함)'}",
        f"- 주문 페이지 상한: 상태별 {report.request.max_pages_per_status}페이지",
            f"- 거래내역 페이지 상한: {report.request.max_transaction_pages}페이지",
        f"- 분석 종목 상한: {report.request.max_symbols}개",
        f"- 분석 종목: {', '.join(report.request.selected_symbols) if report.request.selected_symbols else '보유 종목에서 자동 선택'}",
        "",
        "## 단위와 데이터 범위",
        "",
        f"- 금액: {report.units.money}",
        f"- 수량: {report.units.quantity}",
        f"- 비중: {report.units.weight}",
        f"- 환율: {report.units.fx}",
        f"- 계좌 전체 커버리지: `{report.account_wide_coverage}`",
        "",
        "## 출처와 조회 시각",
        "",
        "| 출처 | 사용 가능 | 조회 시각 | 기준 시각 | 커버리지 안내 |",
        "|---|---:|---|---|---|",
    ]
    for source in report.sources:
        warnings = "<br>".join(_md_cell(value) for value in source.coverage_warnings) or "—"
        lines.append(
            f"| {_md_cell(source.source)} | {'예' if source.available else '아니오'} | "
            f"{source.retrieved_at.isoformat() if source.retrieved_at else '—'} | "
            f"{source.as_of.isoformat() if source.as_of else '—'} | {warnings} |"
        )

    lines.extend(
        [
            "",
            "## 보유 종목",
            "",
            "| 종목 | 시장 | 통화 | 수량 | 평가액 | 매입액 | 손익 | 손익률 | 당일 손익 | 비용(수수료/세금) | 비중 | 상태 |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    if report.positions:
        for row in report.positions:
            market_value = _money(row.market_value, row.currency)
            purchase_amount = _money(row.purchase_amount, row.currency)
            profit_loss = _money(row.profit_loss, row.currency)
            weight = _percent(row.security_weight)
            daily_profit_loss = _money(row.daily_profit_loss, row.currency)
            costs = f"{row.commission if row.commission is not None else '—'} / {row.tax if row.tax is not None else '—'}"
            lines.append(
                f"| {_md_cell(row.symbol)} | {_md_cell(row.market_country or '—')} | "
                f"{_md_cell(row.currency or '—')} | {row.quantity} | {market_value} | "
                f"{purchase_amount} | {profit_loss} | {_percent(row.profit_loss_rate)} | "
                f"{daily_profit_loss} ({_percent(row.daily_profit_loss_rate)}) | {costs} | {weight} | "
                f"{'포함' if row.included_in_totals else '확인 필요'} |"
            )
    else:
        lines.append("| 반환된 종목 없음 | — | — | — | — | — | — | — | — | — | — | 확인 필요 |")

    if report.holdings_summary is not None:
        summary = report.holdings_summary
        lines.extend(
            [
                "",
                "### Toss 보유 요약",
                "",
                f"- 계좌 평가손익: {_money(summary.profit_loss.krw, 'KRW')} / {_money(summary.profit_loss.usd, 'USD')}",
                f"- 매입 후 손익: {_money(summary.profit_loss_after_cost.krw, 'KRW')} / {_money(summary.profit_loss_after_cost.usd, 'USD')}",
                f"- 손익률 / 매입 후 손익률: {_percent(summary.profit_loss_rate)} / {_percent(summary.profit_loss_rate_after_cost)}",
                f"- 일간 손익: {_money(summary.daily_profit_loss.krw, 'KRW')} / {_money(summary.daily_profit_loss.usd, 'USD')} ({_percent(summary.daily_profit_loss_rate)})",
            ]
        )

    lines.extend(
        [
            "",
            "## 통화별 합계",
            "",
            "| 통화 | 평가액 | 매입액 | 손익 | 매입 후 손익 | 매수 가능 금액 | 합계 커버리지 |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    if report.currencies:
        for row in report.currencies:
            complete = "완전" if row.represented_scope_complete else "부분"
            lines.append(
                f"| {row.currency} | {_money(row.market_value_total, row.currency)} | "
                f"{_money(row.purchase_amount_total, row.currency)} | "
                f"{_money(row.profit_loss_total, row.currency)} | "
                f"{_money(row.profit_loss_after_cost_total, row.currency)} | "
                f"{_money(row.buying_power_total, row.currency)} | {complete} |"
            )
    else:
        lines.append("| — | 알 수 없음 | 알 수 없음 | 알 수 없음 | 알 수 없음 | 알 수 없음 | — |")

    lines.extend(["", "## 통합 환산", ""])
    if report.fx is None:
        lines.append("환율 자료가 없어 KRW/USD 통합 합계를 계산하지 않았습니다.")
    else:
        applied = "적용" if report.fx.applied else "미적용"
        rate = f"1 {report.fx.source_currency} = {report.fx.rate} {report.fx.target_currency}" if report.fx.rate is not None else "환율 미확인"
        valid_until = report.fx.valid_until.isoformat() if report.fx.valid_until else "미확인"
        lines.append(f"- Toss 참고 매매기준율: {rate} ({applied})")
        lines.append(f"- 환율 기준 시각: {report.fx.timestamp.isoformat() if report.fx.timestamp else '미확인'}")
        lines.append(f"- 환율 유효 종료: {valid_until}")
        if report.converted_totals is not None:
            totals = report.converted_totals
            lines.extend(
                [
                    "",
                    f"| 환산 통화 ({totals.currency}) | 평가액 | 매입액 | 손익 | 매수 가능 금액 | 합계 평가액+매수 가능 금액 |",
                    "|---|---:|---:|---:|---:|---:|",
                    f"| {totals.currency} | {_money(totals.market_value_total, totals.currency)} | "
                    f"{_money(totals.purchase_amount_total, totals.currency)} | "
                    f"{_money(totals.profit_loss_total, totals.currency)} | "
                    f"{_money(totals.buying_power_total, totals.currency)} | "
                    f"{_money(totals.portfolio_value_total, totals.currency)} |",
                ]
            )
        lines.append("환산은 참고용 매매기준율을 사용하며 실제 체결 환율과 다를 수 있습니다.")

    lines.extend(["", "## 거래내역 요약", ""])
    if not report.transactions.available:
        lines.append("거래내역 자료를 조회하지 못했습니다.")
    else:
        lines.extend(
            [
                f"- 반환된 거래 건수: {report.transactions.count}",
                f"- 결제 완료 / 미결제 / 취소: {report.transactions.settled_count} / "
                f"{report.transactions.unsettled_count} / {report.transactions.cancellation_count}",
                f"- 다음 페이지 존재: {'예' if report.transactions.has_more else '아니오'}",
                f"- 거래내역 조회 시각: {report.transactions.retrieved_at.isoformat() if report.transactions.retrieved_at else '미확인'}",
            ]
        )
        if report.transactions.by_type:
            lines.extend(["", "| 거래 유형 | 건수 |", "|---|---:|"])
            lines.extend(
                f"| {_md_cell(row.key)} | {row.count} |"
                for row in report.transactions.by_type
            )
        if report.transactions.by_asset_class:
            lines.extend(["", "| 자산군 | 건수 |", "|---|---:|"])
            lines.extend(
                f"| {_md_cell('현금/미분류' if row.key == 'CASH_OR_UNCLASSIFIED' else row.key)} | {row.count} |"
                for row in report.transactions.by_asset_class
            )
        if report.transactions.realized_profit_loss:
            lines.extend(["", "### 실현손익 분석 (통화별)", "", "| 통화 | 비용 전 추정 | 비용 후 추정 | 원장 상태 |", "|---|---:|---:|---|"])
            for row in report.transactions.realized_profit_loss:
                lines.append(
                    f"| {row.currency} | {_money(row.before_cost, row.currency)} | "
                    f"{_money(row.after_cost, row.currency)} | {'완전' if row.complete else '산출 불가'} |"
                )
                if row.caveat:
                    lines.append(f"  - {row.caveat}")
                if row.complete:
                    lines.append(f"  - 계산 방식: {row.method}")
        lines.append("거래별 내역은 보고하지 않으며, 실현손익은 완전한 거래 기록이 확인될 때만 가중평균원가 추정치로 표시합니다.")

    lines.extend(["", "## 기술 분석", ""])
    if not report.technical_analysis:
        lines.append("가격·일봉 기술 자료를 조회하지 않았습니다.")
    else:
        lines.extend(["| 종목 | 현재가 | 최근 종가 | 캔들 수 | 가격 기준 시각 | 일봉 기준 시각 | 1일 / 5일 / 20일 수익률 | RSI(14) | SMA(20/50/200) | MACD / 신호 | ATR(14) | 거래량/20일 평균 |", "|---|---:|---:|---:|---|---|---:|---:|---:|---:|---:|---:|"])
        for row in report.technical_analysis:
            returns = " / ".join(_percent(value) for value in (row.return_1d, row.return_5d, row.return_20d))
            averages = " / ".join(str(value) if value is not None else "—" for value in (row.sma_20, row.sma_50, row.sma_200))
            macd = f"{row.macd if row.macd is not None else '—'} / {row.macd_signal if row.macd_signal is not None else '—'}"
            lines.append(
                f"| {_md_cell(row.symbol)} | {_money(row.price, row.currency)} | "
                f"{_money(row.latest_close, row.currency)} | {row.candle_count} | "
                f"{row.price_as_of.isoformat() if row.price_as_of else '—'} | "
                f"{row.candle_as_of.isoformat() if row.candle_as_of else '—'} | {returns} | "
                f"{row.rsi_14 if row.rsi_14 is not None else '—'} | {averages} | {macd} | "
                f"{row.atr_14 if row.atr_14 is not None else '—'} | "
                f"{row.volume_ratio_20 if row.volume_ratio_20 is not None else '—'} |"
            )
            if row.caveat:
                lines.append(f"  - {row.caveat}")

    lines.extend(["", "## 로컬 스냅샷 비교", ""])
    if report.snapshot_comparison is None:
        lines.append("이 실행에서 로컬 계좌 스냅샷을 기록하지 않았습니다.")
    elif report.snapshot_comparison.previous_at is None:
        lines.append("이전 스냅샷이 없어 이번 자료를 기록했습니다.")
    else:
        lines.append(f"- 비교 기준: {report.snapshot_comparison.previous_at.isoformat()}")
        for currency, change in report.snapshot_comparison.change_by_currency.items():
            lines.append(f"- {currency}: {_money(change, currency)}")
    if report.snapshot_comparison and report.snapshot_comparison.caveat:
        lines.append(report.snapshot_comparison.caveat)

    order_count = str(report.orders.count) if report.orders.count is not None else "알 수 없음"
    lines.extend(
        [
            "",
            "## 주문 이력",
            "",
            f"- 반환 주문 수: {order_count}",
            f"- 다음 페이지 존재: {'예' if report.orders.has_more else '아니오' if report.orders.has_more is False else '알 수 없음'}",
            f"- 주문 조회 시각: {report.orders.retrieved_at.isoformat() if report.orders.retrieved_at else '알 수 없음'}",
        ]
    )
    if report.orders.by_status:
        lines.extend(["", "| 주문 상태 | 건수 | 주문 수량 소계 | 체결 수량 소계 |", "|---|---:|---:|---:|"])
        for row in report.orders.by_status:
            lines.append(
                f"| {_md_cell(row.status or '알 수 없음')} | {row.count} | "
                f"{row.ordered_quantity_total if row.ordered_quantity_total is not None else '알 수 없음'} | "
                f"{row.filled_quantity_total if row.filled_quantity_total is not None else '알 수 없음'} |"
            )

    lines.extend(["", "## 시나리오 분석", ""])
    if report.scenarios is None:
        lines.append("시나리오 분석을 요청하지 않았거나 사용할 수 없습니다.")
    else:
        lines.append(f"- 상태: `{report.scenarios.status}`")
        lines.append(f"- 종목별 조사 건수: {report.scenarios.symbols_researched}")
        if report.scenarios.summary:
            lines.extend(["", report.scenarios.summary])
        for horizon in report.scenarios.horizons:
            lines.extend(["", f"### {horizon.name} ({horizon.window})", ""])
            for label, scenario in (
                ("상승", horizon.upside),
                ("기본", horizon.base),
                ("하락", horizon.downside),
            ):
                lines.append(f"- **{label}:** {_md_cell(scenario.investment_rationale)}")
                for title, values in (
                    ("근거", scenario.evidence),
                    ("촉매", scenario.catalysts),
                    ("주요 위험", scenario.risks),
                    ("관찰 조건", scenario.watch_conditions),
                    ("검토 조건", scenario.review_conditions),
                    ("논리 무효화 조건", scenario.invalidation),
                ):
                    if values:
                        lines.append(f"  - {title}: {'; '.join(_md_cell(value) for value in values)}")
                lines.append(f"  - 포트폴리오 영향: {_md_cell(scenario.portfolio_impact)}")
        if report.scenarios.symbol_research:
            lines.extend(["", "### 종목별 조사 결과", ""])
            for row in report.scenarios.symbol_research:
                relation = "보유" if row.portfolio_relation == "holding" else "관심종목"
                lines.append(f"- `{row.symbol}` — {relation}, `{row.status}`")
                if row.analysis:
                    lines.append(f"  - {row.analysis}")
                if row.failure_category:
                    lines.append(
                        "  - 실패 원인: "
                        f"{format_api_failure(APIFailure(row.failure_category, row.retryable is True))}"
                    )

        if report.scenarios.trading_decisions:
            lines.extend(["", "## Trader · Risk · 최종 결정", ""])
            for row in report.scenarios.trading_decisions:
                lines.extend(
                    [
                        f"### `{_md_cell(row.symbol)}` — { _md_cell(row.rating) }",
                        "",
                        "**Trader 계획**",
                        "",
                        row.trader_plan or "계획을 제공하지 않았습니다.",
                        "",
                        "**Risk 토론**",
                        "",
                        row.risk_debate or "토론 내용을 제공하지 않았습니다.",
                        "",
                        "**Portfolio Manager 최종 결정**",
                        "",
                        row.final_decision or "최종 결정을 제공하지 않았습니다.",
                        "",
                    ]
                )
            lines.append("각 결과는 분석 제안이며 주문을 생성하거나 실행하지 않습니다.")

    lines.extend(["", "## 누락과 실패", ""])
    if report.omissions or report.source_failures:
        lines.extend(f"- {item}" for item in report.omissions + report.source_failures)
    else:
        lines.append("- 보고서에서 별도 누락 항목이 기록되지 않았습니다.")

    lines.extend(["", "## 주의 사항", ""])
    unique_caveats = list(dict.fromkeys(report.caveats))
    if unique_caveats:
        lines.extend(f"- {item}" for item in unique_caveats)
    else:
        lines.append("- 이 자료는 조회 시점의 요약이며 투자 조언이나 주문 지시가 아닙니다.")
    lines.append("")
    return "\n".join(lines)


def _display_source_name(source: str) -> str:
    if source == "holdings":
        return "Toss Securities holdings API"
    if source == "orders":
        return "Toss Securities order history API"
    if source == "transactions":
        return "Toss Securities transactions API"
    if source == "exchange_rate":
        return "Toss Securities exchange-rate API"
    if source.startswith("buying_power:"):
        currency = source.partition(":")[2]
        return f"Toss Securities buying power API ({currency})"
    return source


def _money(value: Decimal | None, currency: str | None) -> str:
    return f"{value} {currency}" if value is not None and currency else "알 수 없음"


def _percent(value: Decimal | None) -> str:
    return f"{value * Decimal(100):.2f}%" if value is not None else "알 수 없음"


def _md_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").replace("\r", " ")
