"""Value, growth, quality and momentum scores computed by code, and a check of whether they predict.

A style view an LLM writes cannot be replayed: the same prompt samples a
different answer, and a model shown a ticker and a past date may recall what
happened next. These scores are arithmetic on what was public on the analysis
date, so a date range can be scored without a model and the same inputs always
give the same signal. A narrative layer, if one is added, explains these numbers;
it does not set them.

Scope: one stock's own figures against fixed thresholds. There is no sector or
universe ranking, which would need every stock's figures for every date, and the
thresholds are set once rather than tuned on the results they are judged by.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date as Date
from enum import StrEnum

import pandas as pd

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.date_window import get_current_date
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.vendors import sec_edgar
from tradingagents.dataflows.vendors.yahoo.market import get_splits
from tradingagents.dataflows.vendors.yahoo.ohlcv import load_ohlcv
from tradingagents.memory.settlement import resolve_benchmark


class StyleSignal(StrEnum):
    BULLISH = "Bullish"
    NEUTRAL = "Neutral"
    BEARISH = "Bearish"
    ABSTAIN = "Abstain"   # the inputs were not there; never a neutral reading


STYLES = ("value", "growth", "quality", "momentum")

# Trading days a signal claims to describe. A value or quality view is about the
# year ahead; scoring it over a week measures noise.
HORIZON_DAYS = {"value": 252, "growth": 252, "quality": 252, "momentum": 63}

# (bullish at or above, bearish at or below) for each style's one measure. The
# score maps the same measure onto [-1, 1] around the midpoint of the two.
# ponytail: fixed absolute thresholds; a sector-relative rank needs a point-in-time universe.
THRESHOLDS = {
    "value": (0.06, 0.02),      # earnings yield: diluted EPS over price
    "growth": (0.10, 0.0),      # fiscal-year revenue growth
    "quality": (0.15, 0.05),    # return on equity
    "momentum": (0.10, -0.10),  # 12-month return skipping the latest month
}

_FUNDAMENTAL_LINES = ("Diluted EPS", "Revenue", "Net Income", "Stockholders Equity")
# A fiscal year ended longer ago than this is not the company's current state.
_STALE_DAYS = 550
_YEAR = 252
_MONTH = 21


@dataclass(frozen=True)
class StyleMetric:
    name: str
    value: float
    period_end: str
    source: str


@dataclass(frozen=True)
class StyleScore:
    style: str
    signal: StyleSignal
    score: float | None
    metrics: tuple[StyleMetric, ...] = ()
    missing: tuple[str, ...] = ()

    @property
    def horizon_days(self) -> int:
        return HORIZON_DAYS[self.style]


def _judge(style: str, measure: float, metrics: tuple[StyleMetric, ...]) -> StyleScore:
    bullish, bearish = THRESHOLDS[style]
    signal = (StyleSignal.BULLISH if measure >= bullish
              else StyleSignal.BEARISH if measure <= bearish else StyleSignal.NEUTRAL)
    score = max(-1.0, min(1.0, (measure - (bullish + bearish) / 2) / (bullish - bearish)))
    return StyleScore(style, signal, round(score, 4), metrics)


def _abstain(style: str, *missing: str) -> StyleScore:
    return StyleScore(style, StyleSignal.ABSTAIN, None, missing=missing)


def _fresh(facts: list[dict], as_of: str) -> list[dict]:
    """The facts, or none when the latest fiscal year is too old to describe the company on ``as_of``.

    Only the latest year is held to it: growth compares it with the year before.
    """
    cutoff = Date.fromisoformat(as_of).toordinal() - _STALE_DAYS
    return facts if facts and Date.fromisoformat(facts[-1]["end"]).toordinal() >= cutoff else []


def score_styles(
    as_of: str,
    closes: pd.Series,
    facts: dict[str, list[dict]] | None,
    splits: pd.Series | None = None,
) -> dict[str, StyleScore]:
    """Every style's score on ``as_of`` from inputs that were public then.

    ``closes`` are split-adjusted daily closes indexed by date; rows after
    ``as_of`` are dropped here, so a caller may pass the whole history. ``facts``
    are fiscal-year facts as filed by ``as_of`` (``sec_edgar.get_annual_facts``),
    or None when the company files none. ``splits`` are share split ratios by
    date: adjusted closes state old prices in today's shares, while a filed EPS
    is per share of its filing day, so the price is restated in those shares.
    """
    cutoff = pd.Timestamp(as_of)
    closes = closes[closes.index <= cutoff].dropna()
    splits = splits if splits is not None else pd.Series(dtype=float)
    facts = {label: _fresh(rows, as_of) for label, rows in (facts or {}).items()}
    source = "sec_edgar"
    scores = {}

    eps = facts.get("Diluted EPS") or []
    if not eps or closes.empty:
        scores["value"] = _abstain("value", *(["Diluted EPS"] if not eps else []),
                                   *(["price"] if closes.empty else []))
    else:
        latest = eps[-1]
        factor = float(splits[splits.index > pd.Timestamp(latest["filed"])].prod()) if not splits.empty else 1.0
        price = float(closes.iloc[-1]) * factor
        scores["value"] = _judge("value", latest["val"] / price, (
            StyleMetric("diluted_eps", latest["val"], latest["end"], source),
            StyleMetric("price_in_filing_shares", round(price, 4), closes.index[-1].strftime("%Y-%m-%d"), "yahoo"),
        ))

    revenue = facts.get("Revenue") or []
    if len(revenue) < 2 or not 300 <= (Date.fromisoformat(revenue[-1]["end"])
                                       - Date.fromisoformat(revenue[-2]["end"])).days <= 400:
        scores["growth"] = _abstain("growth", "two consecutive fiscal-year revenues")
    elif revenue[-2]["val"] <= 0:
        scores["growth"] = _abstain("growth", "positive prior-year revenue")
    else:
        prior, latest = revenue[-2], revenue[-1]
        scores["growth"] = _judge("growth", latest["val"] / prior["val"] - 1, (
            StyleMetric("revenue", latest["val"], latest["end"], source),
            StyleMetric("prior_revenue", prior["val"], prior["end"], source),
        ))

    income = {f["end"]: f for f in facts.get("Net Income") or []}
    equity = [f for f in facts.get("Stockholders Equity") or [] if f["end"] in income]
    if not equity:
        scores["quality"] = _abstain("quality", "net income and equity for one fiscal year")
    elif equity[-1]["val"] <= 0:
        scores["quality"] = _abstain("quality", "positive stockholders equity")
    else:
        book, earned = equity[-1], income[equity[-1]["end"]]
        scores["quality"] = _judge("quality", earned["val"] / book["val"], (
            StyleMetric("net_income", earned["val"], earned["end"], source),
            StyleMetric("stockholders_equity", book["val"], book["end"], source),
        ))

    if len(closes) <= _YEAR:
        scores["momentum"] = _abstain("momentum", f"{_YEAR + 1} daily closes")
    else:
        start, end = closes.iloc[-_YEAR - 1], closes.iloc[-_MONTH - 1]
        scores["momentum"] = _judge("momentum", float(end / start - 1), (
            StyleMetric("close_12m_ago", float(start), closes.index[-_YEAR - 1].strftime("%Y-%m-%d"), "yahoo"),
            StyleMetric("close_1m_ago", float(end), closes.index[-_MONTH - 1].strftime("%Y-%m-%d"), "yahoo"),
        ))
    return scores


def _closes(symbol: str) -> pd.Series:
    """The whole cached daily close history, as reported, indexed by date."""
    frame = load_ohlcv(symbol, get_current_date(), fill_gaps=False)
    return frame.set_index("Date")["Close"].dropna()


def _facts(ticker: str, as_of: str) -> dict[str, list[dict]] | None:
    try:
        return sec_edgar.get_annual_facts(ticker, _FUNDAMENTAL_LINES, as_of)
    except NoMarketDataError:
        return None


def compute_style_scores(ticker: str, as_of: str) -> dict[str, StyleScore]:
    """Every style's score for ``ticker`` on ``as_of``, from public data as it stood then."""
    return score_styles(as_of, _closes(ticker), _facts(ticker, as_of), get_splits(ticker))


# --- Does a signal predict? -------------------------------------------------

_DIRECTION = {StyleSignal.BULLISH: 1, StyleSignal.BEARISH: -1}


@dataclass
class SignalStats:
    alphas: list[float] = field(default_factory=list)
    pending: int = 0

    @property
    def mean_alpha(self) -> float | None:
        return sum(self.alphas) / len(self.alphas) if self.alphas else None


@dataclass
class StyleBacktest:
    # style -> directional or neutral signal -> outcomes
    cells: dict[str, dict[StyleSignal, SignalStats]] = field(default_factory=lambda: {
        s: {sig: SignalStats() for sig in StyleSignal if sig is not StyleSignal.ABSTAIN} for s in STYLES})
    abstained: dict[str, int] = field(default_factory=lambda: dict.fromkeys(STYLES, 0))
    failures: list[tuple[str, str]] = field(default_factory=list)

    def render(self) -> str:
        lines = []
        for style in STYLES:
            by_signal = self.cells[style]
            lines.append(f"{style} (alpha over {HORIZON_DAYS[style]} trading days)")
            for signal, stats in by_signal.items():
                n = len(stats.alphas)
                if not n:
                    lines.append(f"  - {signal}: n=0, pending {stats.pending}")
                    continue
                direction = _DIRECTION.get(signal)
                hit = (f", hit {sum(a * direction > 0 for a in stats.alphas) / n:.0%}"
                       if direction else "")
                lines.append(f"  - {signal}: n={n}{hit}, mean alpha {stats.mean_alpha:+.2%}"
                             f", pending {stats.pending}")
            bull, bear = by_signal[StyleSignal.BULLISH].mean_alpha, by_signal[StyleSignal.BEARISH].mean_alpha
            if bull is not None and bear is not None:
                lines.append(f"  - Bullish minus Bearish: {bull - bear:+.2%}")
            lines.append(f"  - Abstain: {self.abstained[style]}")
        lines += [
            "",
            "Indicative only. The tickers were chosen today, so names that later failed are missing "
            "(survivorship bias). Monthly cells with year-long windows overlap, so cells are not "
            "independent observations. Prices are dividend-adjusted closes, which shifts earnings "
            "yield by about the dividend yield.",
        ]
        for ticker, reason in self.failures:
            lines.append(f"failed: {ticker}: {reason}")
        return "\n".join(lines)


def _forward_alpha(closes: pd.Series, bench: pd.Series, as_of: str, days: int) -> float | None:
    """Excess return over ``days`` sessions from the first close after ``as_of``, or None if not traded yet."""
    after = closes[closes.index > pd.Timestamp(as_of)]
    if len(after) <= days:
        return None
    entry, exit_ = after.index[0], after.index[days]
    if bench.empty or bench.index[0] > entry or bench.index[-1] < exit_:
        return None
    raw = after.iloc[days] / after.iloc[0] - 1
    bench_ret = bench.asof(exit_) / bench.asof(entry) - 1
    return float(raw - bench_ret)


def evaluate_styles(
    tickers: list[str],
    dates: list[str],
    progress: Callable[[int, int, str], None] | None = None,
) -> StyleBacktest:
    """Score each style on every (ticker, date) and measure the alpha that followed.

    No model is called. Each ticker's prices, splits and filings are fetched once
    and cut to each date, so a cell sees only what was public on its date.
    """
    result = StyleBacktest()
    benches: dict[str, pd.Series] = {}
    tickers = list(dict.fromkeys(tickers))
    for index, ticker in enumerate(tickers, 1):
        if progress:
            progress(index, len(tickers), ticker)
        try:
            closes, splits = _closes(ticker), get_splits(ticker)
            name = resolve_benchmark(ticker, get_config())
            if name not in benches:
                benches[name] = _closes(name)
        except Exception as exc:  # one unreachable ticker must not end the sweep
            result.failures.append((ticker, str(exc)))
            continue
        for as_of in dates:
            try:
                scores = score_styles(as_of, closes, _facts(ticker, as_of), splits)
            except Exception as exc:
                result.failures.append((ticker, f"{as_of}: {exc}"))
                continue
            for style, score in scores.items():
                if score.signal is StyleSignal.ABSTAIN:
                    result.abstained[style] += 1
                    continue
                stats = result.cells[style][score.signal]
                alpha = _forward_alpha(closes, benches[name], as_of, HORIZON_DAYS[style])
                if alpha is None:
                    stats.pending += 1
                else:
                    stats.alphas.append(alpha)
    return result
