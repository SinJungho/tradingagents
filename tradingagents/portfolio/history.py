"""Private local snapshots of normalized portfolio values (never raw API payloads)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from tradingagents.portfolio.models import BuyingPower, Holdings


@dataclass(frozen=True)
class SnapshotComparison:
    previous_at: datetime | None
    change_by_currency: dict[str, Decimal]
    caveat: str | None = None


def append_portfolio_snapshot(
    holdings: Holdings,
    buying_power: tuple[BuyingPower, ...] | list[BuyingPower],
    *,
    account_ordinal: int,
    captured_at: datetime,
    path: Path | None = None,
) -> SnapshotComparison:
    """Append only normalized values and return change from the last same-account snapshot."""
    if account_ordinal < 1:
        raise ValueError("account_ordinal must be positive")
    target = path or Path.home() / ".tradingagents" / "portfolio" / "history.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(target.parent, 0o700)
    if target.is_symlink():
        raise OSError("snapshot path must not be a symbolic link")
    if target.exists():
        os.chmod(target, 0o600)
    previous = _previous_snapshot(target, account_ordinal)
    position_rows = [
        {
            "symbol": row.symbol,
            "currency": row.currency,
            "quantity": str(row.quantity),
            "market_value": str(row.market_value) if row.market_value is not None else None,
        }
        for row in holdings.holdings
    ]
    cash = {
        item.currency: str(item.cash_buying_power)
        for item in buying_power
    }
    record = {
        "account_ordinal": account_ordinal,
        "captured_at": captured_at.isoformat(),
        "positions": position_rows,
        "buying_power": cash,
    }
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(target, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as output:
            descriptor = -1
            output.write(json.dumps(record, separators=(",", ":"), ensure_ascii=True))
            output.write("\n")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return _compare(previous, record)


def _previous_snapshot(path: Path, account_ordinal: int) -> dict | None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return None
    for line in reversed(lines):
        try:
            row = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(row, dict) and row.get("account_ordinal") == account_ordinal:
            return row
    return None


def _compare(previous: dict | None, current: dict) -> SnapshotComparison:
    if previous is None:
        return SnapshotComparison(None, {}, "이전 로컬 스냅샷이 없어 비교하지 않았습니다.")
    try:
        previous_at = datetime.fromisoformat(previous["captured_at"])
        old = _totals(previous)
        new = _totals(current)
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return SnapshotComparison(None, {}, "이전 로컬 스냅샷이 유효하지 않아 비교하지 않았습니다.")
    if set(old) != set(new):
        return SnapshotComparison(
            previous_at, {}, "통화별 보유 또는 매수 가능 금액 범위가 달라 차이를 비교하지 않았습니다."
        )
    return SnapshotComparison(
        previous_at,
        {currency: new[currency] - old[currency] for currency in sorted(new)},
        "같은 화면 계좌 순번의 평가액과 매수 가능 금액 변화입니다. 계좌 식별자를 저장하지 않아 순번이 바뀐 계좌인지는 검증할 수 없으며, 입출금 조정 총수익률도 아닙니다.",
    )


def _totals(record: dict) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = {}
    for row in record["positions"]:
        currency = row.get("currency")
        value = row.get("market_value")
        if not isinstance(currency, str) or value is None:
            raise ValueError("snapshot contains an incomplete position value")
        totals[currency] = totals.get(currency, Decimal(0)) + Decimal(value)
    for currency, amount in record["buying_power"].items():
        totals[currency] = totals.get(currency, Decimal(0)) + Decimal(amount)
    return totals
