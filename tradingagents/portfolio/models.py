"""Normalized, immutable portfolio data returned by broker adapters."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, repr=False)
class Account:
    account_seq: int
    account_type: str | None


@dataclass(frozen=True, repr=False)
class Accounts:
    accounts: tuple[Account, ...]
    retrieved_at: datetime | None
    coverage_warnings: tuple[str, ...] = ()


@dataclass(frozen=True, repr=False)
class Holding:
    symbol: str
    name: str | None
    market_country: str | None
    exchange: str | None
    currency: str | None
    quantity: Decimal
    last_price: Decimal | None
    average_purchase_price: Decimal | None
    purchase_amount: Decimal | None
    market_value: Decimal | None
    market_value_after_cost: Decimal | None
    profit_loss: Decimal | None
    profit_loss_after_cost: Decimal | None
    retrieved_at: datetime | None


@dataclass(frozen=True, repr=False)
class Holdings:
    holdings: tuple[Holding, ...]
    retrieved_at: datetime | None
    as_of: datetime | None = None  # HoldingsOverview has no financial as-of timestamp.
    coverage_warnings: tuple[str, ...] = ()


@dataclass(frozen=True, repr=False)
class Order:
    order_id: str
    symbol: str
    market_country: str | None
    exchange: str | None
    currency: str | None
    side: str | None
    order_type: str | None
    status: str | None
    price: Decimal | None
    quantity: Decimal | None
    order_amount: Decimal | None
    filled_quantity: Decimal | None
    average_filled_price: Decimal | None
    filled_amount: Decimal | None
    ordered_at: datetime | None
    canceled_at: datetime | None
    filled_at: datetime | None
    retrieved_at: datetime | None


@dataclass(frozen=True, repr=False)
class Orders:
    orders: tuple[Order, ...]
    retrieved_at: datetime | None
    has_more: bool = False
    coverage_warnings: tuple[str, ...] = ()


@dataclass(frozen=True, repr=False)
class BuyingPower:
    currency: str
    cash_buying_power: Decimal
    retrieved_at: datetime | None
    coverage_warnings: tuple[str, ...] = ()
