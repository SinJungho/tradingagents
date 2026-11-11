"""Normalized, immutable portfolio data returned by broker adapters."""

from dataclasses import dataclass
from datetime import date, datetime
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
class CurrencyAmounts:
    krw: Decimal | None = None
    usd: Decimal | None = None


@dataclass(frozen=True, repr=False)
class HoldingsSummary:
    total_purchase_amount: CurrencyAmounts
    market_value: CurrencyAmounts
    market_value_after_cost: CurrencyAmounts
    profit_loss: CurrencyAmounts
    profit_loss_after_cost: CurrencyAmounts
    profit_loss_rate: Decimal | None
    profit_loss_rate_after_cost: Decimal | None
    daily_profit_loss: CurrencyAmounts
    daily_profit_loss_rate: Decimal | None


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
    profit_loss_rate: Decimal | None = None
    profit_loss_rate_after_cost: Decimal | None = None
    daily_profit_loss: Decimal | None = None
    daily_profit_loss_rate: Decimal | None = None
    commission: Decimal | None = None
    tax: Decimal | None = None


@dataclass(frozen=True, repr=False)
class Holdings:
    holdings: tuple[Holding, ...]
    retrieved_at: datetime | None
    as_of: datetime | None = None  # HoldingsOverview has no financial as-of timestamp.
    coverage_warnings: tuple[str, ...] = ()
    summary: HoldingsSummary | None = None


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
    commission: Decimal | None = None
    tax: Decimal | None = None
    settlement_date: date | None = None


@dataclass(frozen=True, repr=False)
class Orders:
    orders: tuple[Order, ...]
    retrieved_at: datetime | None
    has_more: bool = False
    coverage_warnings: tuple[str, ...] = ()


@dataclass(frozen=True, repr=False)
class ExchangeRate:
    base_currency: str
    quote_currency: str
    rate: Decimal
    mid_rate: Decimal
    valid_from: datetime
    valid_until: datetime
    retrieved_at: datetime | None


@dataclass(frozen=True, repr=False)
class Transaction:
    """Normalized transaction facts; repr stays private and reports use aggregates only."""

    transaction_type: str
    asset_class: str | None
    settled: bool
    is_cancellation: bool
    symbol: str | None = None
    market_country: str | None = None
    currency: str | None = None
    quantity: Decimal | None = None
    filled_price: Decimal | None = None
    amount: Decimal | None = None
    commission: Decimal | None = None
    tax: Decimal | None = None
    net_amount: Decimal | None = None
    exchange_rate: Decimal | None = None
    settlement_date: date | None = None
    transaction_time: datetime | None = None


@dataclass(frozen=True, repr=False)
class Transactions:
    transactions: tuple[Transaction, ...]
    retrieved_at: datetime | None
    has_more: bool = False
    coverage_warnings: tuple[str, ...] = ()


@dataclass(frozen=True, repr=False)
class MarketPrice:
    symbol: str
    currency: str
    last_price: Decimal
    timestamp: datetime | None
    retrieved_at: datetime | None


@dataclass(frozen=True, repr=False)
class Candle:
    timestamp: datetime
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: Decimal
    currency: str


@dataclass(frozen=True, repr=False)
class CandlePage:
    symbol: str
    interval: str
    candles: tuple[Candle, ...]
    retrieved_at: datetime | None
    next_before: datetime | None = None


@dataclass(frozen=True, repr=False)
class BuyingPower:
    currency: str
    cash_buying_power: Decimal
    retrieved_at: datetime | None
    coverage_warnings: tuple[str, ...] = ()
