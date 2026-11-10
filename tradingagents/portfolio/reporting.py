"""Schema-validated JSON and Korean Markdown portfolio reports."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from tradingagents.portfolio.analytics import PortfolioAnalytics
from tradingagents.portfolio.models import Holdings
from tradingagents.portfolio.scenarios import PortfolioScenarioReport


class _ReportModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RequestScope(_ReportModel):
    orders_from: date
    orders_to: date
    max_pages_per_status: int
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


class PortfolioReport(_ReportModel):
    schema_version: Literal["1.0"]
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
    scenarios: ScenarioReport | None
    source_failures: list[str]
    omissions: list[str]
    caveats: list[str]


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
                )
                for row in scenarios.symbol_research
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
    if failures:
        report_caveats.append("일부 데이터 조회에 실패해 결과가 부분적입니다.")
    if not failures and analytics.account_wide_coverage == "complete" and scenarios is not None:
        status: Literal["complete", "partial", "unavailable"] = (
            "complete" if scenarios.status == "complete" else "partial"
        )
    elif holdings is None and not analytics.buying_power and analytics.orders is None:
        status = "unavailable"
    else:
        status = "partial"

    return PortfolioReport.model_validate(
        {
            "schema_version": "1.0",
            "mode": mode,
            "status": status,
            "generated_at": generated_at,
            "request": request,
            "units": UnitDescriptions(
                money="통화별 금액이며 서로 다른 통화를 합산하지 않습니다.",
                quantity="주식 수량 또는 제공자가 정의한 수량 단위입니다.",
                weight="같은 통화 범위 내 비중이며 자료가 불완전하면 null입니다.",
                fx="FX 입력이 없으면 환산 합계를 만들지 않습니다.",
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
            "scenarios": scenario_report,
            "source_failures": failures,
            "omissions": report_omissions,
            "caveats": report_caveats + list(analytics.coverage_warnings) + list(analytics.unknowns),
        }
    )


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
        f"- 주문 페이지 상한: 상태별 {report.request.max_pages_per_status}페이지",
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
            "| 종목 | 시장 | 통화 | 수량 | 평가액 | 매입액 | 손익 | 비중 | 상태 |",
            "|---|---|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    if report.positions:
        for row in report.positions:
            market_value = _money(row.market_value, row.currency)
            purchase_amount = _money(row.purchase_amount, row.currency)
            profit_loss = _money(row.profit_loss, row.currency)
            weight = _percent(row.security_weight)
            lines.append(
                f"| {_md_cell(row.symbol)} | {_md_cell(row.market_country or '—')} | "
                f"{_md_cell(row.currency or '—')} | {row.quantity} | {market_value} | "
                f"{purchase_amount} | {profit_loss} | {weight} | "
                f"{'포함' if row.included_in_totals else '확인 필요'} |"
            )
    else:
        lines.append("| 반환된 종목 없음 | — | — | — | — | — | — | — | 확인 필요 |")

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
