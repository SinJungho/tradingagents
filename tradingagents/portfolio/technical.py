"""Small deterministic indicators for normalized Toss daily candles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext

from tradingagents.portfolio.models import CandlePage, MarketPrice


@dataclass(frozen=True)
class TechnicalSnapshot:
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
    caveat: str | None = None


def analyze_daily_candles(
    symbol: str, page: CandlePage | None, quote: MarketPrice | None = None
) -> TechnicalSnapshot:
    candles = sorted(page.candles, key=lambda item: item.timestamp) if page else []
    closes = [item.close_price for item in candles]
    last = closes[-1] if closes else None
    price = quote.last_price if quote else last
    with localcontext() as context:
        context.prec = 28
        rsi = _rsi(closes, 14)
        macd, signal = _macd(closes)
        atr = _atr(candles, 14)
        volume_ratio = None
        if len(candles) >= 21:
            average_volume = sum((row.volume for row in candles[-21:-1]), Decimal(0)) / 20
            if average_volume > 0:
                volume_ratio = candles[-1].volume / average_volume
        missing = []
        if len(candles) <= 20:
            missing.append("20일 수익률·거래량 비율")
        if len(candles) < 15:
            missing.append("RSI(14)·ATR(14)")
        if len(candles) < 20:
            missing.append("SMA(20)")
        if len(candles) < 50:
            missing.append("50일 이동평균")
        if len(candles) < 200:
            missing.append("200일 이동평균")
        if len(candles) < 34:
            missing.append("MACD")
        caveat = (
            "일봉 캔들을 가져오지 못해 기술 지표를 계산하지 못했습니다."
            if not candles
            else f"캔들 {len(candles)}개 기준; 자료 부족으로 " + ", ".join(missing) + "은 미확인입니다."
            if missing
            else None
        )
        return TechnicalSnapshot(
            symbol=symbol,
            currency=quote.currency if quote else (candles[-1].currency if candles else None),
            price=price,
            latest_close=last,
            candle_count=len(candles),
            price_as_of=quote.timestamp if quote else None,
            candle_as_of=candles[-1].timestamp if candles else None,
            return_1d=_return(closes, 1),
            return_5d=_return(closes, 5),
            return_20d=_return(closes, 20),
            sma_20=_mean(closes, 20),
            sma_50=_mean(closes, 50),
            sma_200=_mean(closes, 200),
            rsi_14=rsi,
            macd=macd,
            macd_signal=signal,
            atr_14=atr,
            volume_ratio_20=volume_ratio,
            caveat=caveat,
        )


def _mean(values: list[Decimal], count: int) -> Decimal | None:
    if len(values) < count:
        return None
    return sum(values[-count:], Decimal(0)) / count


def _return(values: list[Decimal], days: int) -> Decimal | None:
    if len(values) <= days or values[-days - 1] == 0:
        return None
    return values[-1] / values[-days - 1] - Decimal(1)


def _rsi(values: list[Decimal], period: int) -> Decimal | None:
    if len(values) <= period:
        return None
    changes = [values[index + 1] - values[index] for index in range(len(values) - 1)]
    gains = [max(change, Decimal(0)) for change in changes]
    losses = [max(-change, Decimal(0)) for change in changes]
    average_gain = sum(gains[:period], Decimal(0)) / period
    average_loss = sum(losses[:period], Decimal(0)) / period
    for gain, loss in zip(gains[period:], losses[period:], strict=True):
        average_gain = (average_gain * (period - 1) + gain) / period
        average_loss = (average_loss * (period - 1) + loss) / period
    if average_loss == 0:
        return Decimal(100) if average_gain > 0 else Decimal(50)
    relative_strength = average_gain / average_loss
    return Decimal(100) - Decimal(100) / (Decimal(1) + relative_strength)


def _ema(values: list[Decimal], period: int) -> list[Decimal]:
    if len(values) < period:
        return []
    alpha = Decimal(2) / (period + 1)
    current = sum(values[:period], Decimal(0)) / period
    result = [current]
    for value in values[period:]:
        current = (value - current) * alpha + current
        result.append(current)
    return result


def _macd(values: list[Decimal]) -> tuple[Decimal | None, Decimal | None]:
    if len(values) < 34:
        return None, None
    fast = _ema(values, 12)
    slow = _ema(values, 26)
    offset = 26 - 12
    line = [fast[index + offset] - value for index, value in enumerate(slow)]
    signal = _ema(line, 9)
    return line[-1], signal[-1] if signal else None


def _atr(candles, period: int) -> Decimal | None:
    if len(candles) <= period:
        return None
    true_ranges = []
    for index in range(len(candles) - 1):
        previous, current = candles[index], candles[index + 1]
        true_ranges.append(
            max(
                current.high_price - current.low_price,
                abs(current.high_price - previous.close_price),
                abs(current.low_price - previous.close_price),
            )
        )
    current = sum(true_ranges[:period], Decimal(0)) / period
    for true_range in true_ranges[period:]:
        current = (current * (period - 1) + true_range) / period
    return current
