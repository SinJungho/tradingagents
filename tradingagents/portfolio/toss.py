"""Read-only adapter for the Toss Securities REST portfolio endpoints."""

from __future__ import annotations

import re
import time
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlsplit

import requests

from tradingagents.api_diagnostics import (
    APIFailure,
    classify_api_failure,
    classify_http_status,
)
from tradingagents.portfolio.models import (
    Account,
    Accounts,
    BuyingPower,
    Candle,
    CandlePage,
    CurrencyAmounts,
    ExchangeRate,
    Holding,
    Holdings,
    HoldingsSummary,
    MarketPrice,
    Order,
    Orders,
    Transaction,
    Transactions,
)

_HOST = "https://openapi.tossinvest.com"
_TOKEN_PATH = "/oauth2/token"
_ALLOWED_READ_PATHS = {
    "/api/v1/accounts",
    "/api/v1/holdings",
    "/api/v1/prices",
    "/api/v1/candles",
    "/api/v1/orders",
    "/api/v1/buying-power",
    "/api/v1/exchange-rate",
    "/api/v1/transactions",
}
_ORDER_DETAIL_PATH = re.compile(r"^/api/v1/orders/[A-Za-z0-9_-]{1,128}$")
_SYMBOL = re.compile(r"^[A-Za-z0-9.-]{1,32}$")
_TIMEOUT = (3.05, 10.0)
_MAX_RETRIES = 2
_MAX_PAGES = 3
_MAX_TRANSACTION_PAGES = 10
_PAGE_SIZE = 100
_EXPIRY_SKEW_SECONDS = 30

_ACCOUNT_WARNING = "Only active brokerage accounts are returned by Toss Securities."
_HOLDINGS_WARNING = (
    "Toss holdings cover KR and US stocks; overseas options and bonds are excluded."
)
_ORDERS_WARNING = (
    "Toss order history excludes order types unsupported by its Open API."
)
_TRANSACTIONS_WARNING = (
    "Transaction summaries cover returned records only; transaction amounts are not summed."
)


class TossAPIError(RuntimeError):
    """A sanitized Toss API error that never includes response bodies or credentials."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        failure: APIFailure | None = None,
    ):
        self.status = status
        self.failure = failure or (
            classify_http_status(status)
            if status is not None
            else APIFailure("provider_response", False)
        )
        self.category = self.failure.category
        self.retryable = self.failure.retryable
        details = []
        if status is not None:
            details.append(f"HTTP {status}")
        details.append(f"{self.category}; retryable={'yes' if self.retryable else 'no'}")
        suffix = f" ({', '.join(details)})" if details else ""
        super().__init__(f"Toss API {message}{suffix}.")


class TossPortfolioAdapter:
    """Fetch normalized Toss account data; business requests are read-only GETs."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        session: requests.Session | None = None,
    ) -> None:
        if not client_id or not client_secret:
            raise ValueError("Toss client credentials are required.")
        self._client_id = client_id
        self._client_secret = client_secret
        self._session = session if session is not None else requests.Session()
        self._access_token: str | None = None
        self._token_expires_at = 0.0

    def get_accounts(self) -> Accounts:
        response = self._get("/api/v1/accounts")
        result = self._result(response)
        if not isinstance(result, list):
            raise TossAPIError("returned an invalid accounts response", status=response.status_code)
        accounts = tuple(
            Account(
                account_seq=int(item["accountSeq"]),
                account_type=_optional_string(item.get("accountType")),
            )
            for item in result
            if isinstance(item, dict) and _is_int(item.get("accountSeq"))
        )
        if len(accounts) != len(result):
            raise TossAPIError("returned an invalid accounts response", status=response.status_code)
        return Accounts(accounts, _retrieved_at(response), (_ACCOUNT_WARNING,))

    def get_holdings(self, account_seq: int, symbol: str | None = None) -> Holdings:
        params: dict[str, str | int] = {}
        if symbol is not None:
            if not _SYMBOL.fullmatch(symbol):
                raise ValueError("symbol must contain only letters, digits, '.', or '-'.")
            params["symbol"] = symbol
        response = self._get("/api/v1/holdings", account_seq=account_seq, params=params)
        result = self._result(response)
        if not isinstance(result, dict) or not isinstance(result.get("items"), list):
            raise TossAPIError("returned an invalid holdings response", status=response.status_code)
        retrieved_at = _retrieved_at(response)
        holdings = tuple(_holding(item, retrieved_at) for item in result["items"])
        summary = _holdings_summary(result)
        return Holdings(
            holdings=holdings,
            retrieved_at=retrieved_at,
            as_of=None,
            coverage_warnings=(_HOLDINGS_WARNING,),
            summary=summary,
        )

    def get_prices(self, symbols: tuple[str, ...] | list[str]) -> tuple[MarketPrice, ...]:
        if not 1 <= len(symbols) <= 200:
            raise ValueError("symbols must contain between 1 and 200 items.")
        if any(not isinstance(symbol, str) or not _SYMBOL.fullmatch(symbol) for symbol in symbols):
            raise ValueError("symbols must contain only letters, digits, '.', or '-'.")
        if len(set(symbols)) != len(symbols):
            raise ValueError("symbols must be unique.")
        response = self._get("/api/v1/prices", params={"symbols": ",".join(symbols)})
        result = self._result(response)
        if not isinstance(result, list):
            raise TossAPIError("returned an invalid prices response", status=response.status_code)
        retrieved_at = _retrieved_at(response)
        prices = tuple(_market_price(item, retrieved_at) for item in result)
        if len({item.symbol for item in prices}) != len(prices):
            raise TossAPIError("returned duplicate market prices", status=response.status_code)
        return prices

    def get_candles(
        self,
        symbol: str,
        *,
        interval: str = "1d",
        count: int = 200,
        before: datetime | None = None,
        adjusted: bool = True,
    ) -> CandlePage:
        if not _SYMBOL.fullmatch(symbol):
            raise ValueError("symbol must contain only letters, digits, '.', or '-'.")
        if interval not in {"1m", "1d"}:
            raise ValueError("interval must be '1m' or '1d'.")
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 200:
            raise ValueError("count must be an integer between 1 and 200.")
        if before is not None and (not isinstance(before, datetime) or before.tzinfo is None):
            raise ValueError("before must be a timezone-aware datetime.")
        if not isinstance(adjusted, bool):
            raise ValueError("adjusted must be a boolean.")
        params: dict[str, str | int | bool] = {
            "interval": interval,
            "count": count,
            "adjusted": adjusted,
        }
        if before is not None:
            params["before"] = before.isoformat()
        response = self._get(
            "/api/v1/candles", params={"symbol": symbol, **params}
        )
        result = self._result(response)
        if not isinstance(result, dict) or not isinstance(result.get("candles"), list):
            raise TossAPIError("returned an invalid candles response", status=response.status_code)
        candles = tuple(_candle(item) for item in result["candles"])
        if len(candles) > count or len({row.timestamp for row in candles}) != len(candles):
            raise TossAPIError("returned invalid candle pagination data", status=response.status_code)
        next_before = _datetime_optional(result.get("nextBefore"), "nextBefore")
        return CandlePage(symbol, interval, candles, _retrieved_at(response), next_before)

    def get_orders(
        self,
        account_seq: int,
        status: str = "OPEN",
        *,
        symbol: str | None = None,
        from_date: date | str | None = None,
        to_date: date | str | None = None,
    ) -> Orders:
        if status not in {"OPEN", "CLOSED"}:
            raise ValueError("status must be 'OPEN' or 'CLOSED'.")
        if symbol is not None and not _SYMBOL.fullmatch(symbol):
            raise ValueError("symbol must contain only letters, digits, '.', or '-'.")
        query: dict[str, str | int] = {"status": status}
        if symbol is not None:
            query["symbol"] = symbol
        if from_date is not None:
            query["from"] = _date_string(from_date)
        if to_date is not None:
            query["to"] = _date_string(to_date)

        orders: list[Order] = []
        warnings = [_ORDERS_WARNING]
        seen_order_ids: set[str] = set()
        duplicates_found = False
        cursor: str | None = None
        retrieved_at: datetime | None = None
        has_more = False
        page_count = 1 if status == "OPEN" else _MAX_PAGES
        for page in range(page_count):
            params = dict(query)
            if status == "CLOSED":
                params["limit"] = _PAGE_SIZE
                if cursor:
                    params["cursor"] = cursor
            response = self._get("/api/v1/orders", account_seq=account_seq, params=params)
            result = self._result(response)
            if not isinstance(result, dict) or not isinstance(result.get("orders"), list):
                raise TossAPIError("returned an invalid orders response", status=response.status_code)
            retrieved_at = _retrieved_at(response)
            for item in result["orders"]:
                order = _order(item, retrieved_at)
                if status == "CLOSED" and order.order_id in seen_order_ids:
                    duplicates_found = True
                    continue
                seen_order_ids.add(order.order_id)
                orders.append(order)
            has_more = result.get("hasNext") is True
            cursor = result.get("nextCursor")
            if not has_more or status == "OPEN":
                has_more = has_more if status == "CLOSED" else False
                break
            if not isinstance(cursor, str) or not cursor or len(cursor) > 4096:
                raise TossAPIError("returned invalid order pagination data", status=response.status_code)
            if page == page_count - 1:
                warnings.append("Order history is truncated at the configured three-page limit.")
        if duplicates_found:
            warnings.append("Duplicate CLOSED order records were collapsed by orderId.")
        return Orders(tuple(orders), retrieved_at, has_more, tuple(warnings))

    def get_order(self, account_seq: int, order_id: str) -> Order:
        if not _ORDER_DETAIL_PATH.fullmatch(f"/api/v1/orders/{order_id}"):
            raise ValueError("order_id contains unsupported characters or is too long.")
        response = self._get(
            f"/api/v1/orders/{order_id}", account_seq=account_seq
        )
        result = self._result(response)
        if not isinstance(result, dict):
            raise TossAPIError("returned an invalid order response", status=response.status_code)
        return _order(result, _retrieved_at(response))

    def get_buying_power(self, account_seq: int, currency: str) -> BuyingPower:
        if currency not in {"KRW", "USD"}:
            raise ValueError("currency must be 'KRW' or 'USD'.")
        response = self._get(
            "/api/v1/buying-power",
            account_seq=account_seq,
            params={"currency": currency},
        )
        result = self._result(response)
        if not isinstance(result, dict) or result.get("currency") != currency:
            raise TossAPIError("returned an invalid buying-power response", status=response.status_code)
        return BuyingPower(
            currency=currency,
            cash_buying_power=_decimal(result.get("cashBuyingPower"), "cashBuyingPower"),
            retrieved_at=_retrieved_at(response),
        )

    def get_exchange_rate(
        self, base_currency: str = "USD", quote_currency: str = "KRW"
    ) -> ExchangeRate:
        if (base_currency, quote_currency) not in {("USD", "KRW"), ("KRW", "USD")}:
            raise ValueError("Only the Toss KRW/USD currency pair is supported.")
        response = self._get(
            "/api/v1/exchange-rate",
            params={"baseCurrency": base_currency, "quoteCurrency": quote_currency},
        )
        result = self._result(response)
        if (
            not isinstance(result, dict)
            or result.get("baseCurrency") != base_currency
            or result.get("quoteCurrency") != quote_currency
        ):
            raise TossAPIError("returned an invalid exchange-rate response", status=response.status_code)
        rate = _decimal(result.get("rate"), "rate")
        mid_rate = _decimal(result.get("midRate"), "midRate")
        valid_from = _datetime_optional(result.get("validFrom"), "validFrom")
        valid_until = _datetime_optional(result.get("validUntil"), "validUntil")
        if (
            rate <= 0
            or mid_rate <= 0
            or valid_from is None
            or valid_until is None
            or valid_from >= valid_until
        ):
            raise TossAPIError("returned an invalid exchange-rate response", status=response.status_code)
        return ExchangeRate(
            base_currency=base_currency,
            quote_currency=quote_currency,
            rate=rate,
            mid_rate=mid_rate,
            valid_from=valid_from,
            valid_until=valid_until,
            retrieved_at=_retrieved_at(response),
        )

    def get_transactions(
        self,
        account_seq: int,
        *,
        from_date: date | str | None = None,
        to_date: date | str | None = None,
    ) -> Transactions:
        query: dict[str, str | int] = {"limit": _PAGE_SIZE}
        if from_date is not None:
            query["from"] = _date_string(from_date)
        if to_date is not None:
            query["to"] = _date_string(to_date)
        if "from" in query and "to" in query and query["from"] > query["to"]:
            raise ValueError("transaction start date must be on or before its end date.")

        transactions: list[Transaction] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        retrieved_at: datetime | None = None
        has_more = False
        warnings = [_TRANSACTIONS_WARNING]
        for page in range(_MAX_TRANSACTION_PAGES):
            params = dict(query)
            if cursor is not None:
                params["cursor"] = cursor
            response = self._get(
                "/api/v1/transactions", account_seq=account_seq, params=params
            )
            result = self._result(response)
            if (
                not isinstance(result, dict)
                or not isinstance(result.get("transactions"), list)
                or not isinstance(result.get("hasNext"), bool)
            ):
                raise TossAPIError("returned an invalid transactions response", status=response.status_code)
            retrieved_at = _retrieved_at(response)
            transactions.extend(
                _transaction(item) for item in result["transactions"]
            )
            has_more = result["hasNext"]
            next_cursor = result.get("nextCursor")
            if not has_more:
                break
            if not isinstance(next_cursor, str) or not next_cursor or len(next_cursor) > 4096:
                raise TossAPIError("returned invalid transaction pagination data", status=response.status_code)
            if next_cursor in seen_cursors:
                raise TossAPIError("returned repeated transaction pagination data", status=response.status_code)
            seen_cursors.add(next_cursor)
            cursor = next_cursor
            if page == _MAX_TRANSACTION_PAGES - 1:
                warnings.append("Transaction history is truncated at the configured ten-page limit.")

        return Transactions(tuple(transactions), retrieved_at, has_more, tuple(warnings))

    def _get(
        self,
        path: str,
        *,
        account_seq: int | None = None,
        params: dict[str, str | int | bool] | None = None,
    ) -> requests.Response:
        url = f"{_HOST}{path}"
        _validate_business_request("GET", url)
        headers: dict[str, str] = {}
        if account_seq is not None:
            if not _is_int(account_seq) or account_seq <= 0:
                raise ValueError("account_seq must be a positive integer.")
            headers["X-Tossinvest-Account"] = str(account_seq)

        retries = 0
        while True:
            headers["Authorization"] = f"Bearer {self._get_token()}"
            try:
                response = self._session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=_TIMEOUT,
                    allow_redirects=False,
                )
            except requests.RequestException as exc:
                failure = classify_api_failure(exc)
                if failure.retryable and retries < _MAX_RETRIES:
                    retries += 1
                    continue
                message = "request timed out" if failure.category == "timeout" else "request failed"
                raise TossAPIError(message, failure=failure) from None

            _validate_response_url(response, url)
            if 300 <= response.status_code < 400 or response.is_redirect:
                raise TossAPIError("refused a redirect", status=response.status_code)
            if response.status_code == 401:
                self._access_token = None
                self._token_expires_at = 0.0
            if response.status_code >= 500 and retries < _MAX_RETRIES:
                retries += 1
                continue
            if not 200 <= response.status_code < 300:
                raise _response_error(response)
            return response

    def _get_token(self) -> str:
        if self._access_token and time.monotonic() < self._token_expires_at:
            return self._access_token
        url = f"{_HOST}{_TOKEN_PATH}"
        _validate_auth_request("POST", url)
        retries = 0
        while True:
            try:
                response = self._session.post(
                    url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=_TIMEOUT,
                    allow_redirects=False,
                )
            except requests.RequestException as exc:
                failure = classify_api_failure(exc)
                if failure.retryable and retries < _MAX_RETRIES:
                    retries += 1
                    continue
                raise TossAPIError("token request failed", failure=failure) from None
            if response.status_code >= 500 and retries < _MAX_RETRIES:
                retries += 1
                continue
            break
        _validate_response_url(response, url)
        if 300 <= response.status_code < 400 or response.is_redirect:
            raise TossAPIError("refused a token redirect", status=response.status_code)
        if not 200 <= response.status_code < 300:
            raise _response_error(response)
        try:
            payload = response.json()
            token = payload.get("access_token")
            lifetime = int(payload.get("expires_in"))
        except (ValueError, TypeError, AttributeError):
            raise TossAPIError("returned an invalid token response", status=response.status_code) from None
        if not isinstance(token, str) or not token or lifetime <= 0:
            raise TossAPIError("returned an invalid token response", status=response.status_code)
        self._access_token = token
        self._token_expires_at = time.monotonic() + max(
            lifetime - _EXPIRY_SKEW_SECONDS, 0
        )
        return token

    @staticmethod
    def _result(response: requests.Response) -> Any:
        try:
            payload = response.json()
        except (ValueError, requests.JSONDecodeError):
            raise TossAPIError("returned invalid JSON", status=response.status_code) from None
        if not isinstance(payload, dict) or "result" not in payload:
            raise TossAPIError("returned an invalid response envelope", status=response.status_code)
        return payload["result"]


def _validate_business_request(method: str, url: str) -> None:
    parts = urlsplit(url)
    valid_path = parts.path in _ALLOWED_READ_PATHS or bool(_ORDER_DETAIL_PATH.fullmatch(parts.path))
    if (
        method != "GET"
        or parts.scheme != "https"
        or parts.netloc != "openapi.tossinvest.com"
        or parts.username is not None
        or parts.password is not None
        or parts.port is not None
        or parts.query
        or parts.fragment
        or not valid_path
    ):
        raise TossAPIError("refused an unapproved business request")


def _validate_auth_request(method: str, url: str) -> None:
    parts = urlsplit(url)
    if (
        method != "POST"
        or parts.scheme != "https"
        or parts.netloc != "openapi.tossinvest.com"
        or parts.path != _TOKEN_PATH
        or parts.query
        or parts.fragment
    ):
        raise TossAPIError("refused an unapproved token request")


def _validate_response_url(response: requests.Response, request_url: str) -> None:
    response_url = getattr(response, "url", None)
    if not isinstance(response_url, str) or not response_url:
        return
    received = urlsplit(response_url)
    requested = urlsplit(request_url)
    if (
        received.scheme != "https"
        or received.netloc != "openapi.tossinvest.com"
        or received.username is not None
        or received.password is not None
        or received.port is not None
        or received.path != requested.path
    ):
        raise TossAPIError("refused a response from an unapproved URL")


def _response_error(
    response: requests.Response,
) -> TossAPIError:
    return TossAPIError("request failed", status=response.status_code)


def _retrieved_at(response: requests.Response) -> datetime | None:
    value = response.headers.get("Date")
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _holding(item: Any, retrieved_at: datetime | None) -> Holding:
    if not isinstance(item, dict) or not isinstance(item.get("symbol"), str):
        raise TossAPIError("returned an invalid holding item")
    market_value = item.get("marketValue")
    profit_loss = item.get("profitLoss")
    daily_profit_loss = item.get("dailyProfitLoss")
    cost = item.get("cost")
    if (
        not isinstance(market_value, dict)
        or not isinstance(profit_loss, dict)
        or (daily_profit_loss is not None and not isinstance(daily_profit_loss, dict))
        or (cost is not None and not isinstance(cost, dict))
    ):
        raise TossAPIError("returned an invalid holding item")
    daily_profit_loss = daily_profit_loss or {}
    cost = cost or {}
    return Holding(
        symbol=item["symbol"],
        name=_optional_string(item.get("name")),
        market_country=_market_country(item),
        exchange=_optional_string(item.get("exchange")),
        currency=_optional_string(item.get("currency")),
        quantity=_decimal(item.get("quantity"), "quantity"),
        last_price=_decimal_optional(item.get("lastPrice"), "lastPrice"),
        average_purchase_price=_decimal_optional(
            item.get("averagePurchasePrice"), "averagePurchasePrice"
        ),
        purchase_amount=_decimal_optional(market_value.get("purchaseAmount"), "purchaseAmount"),
        market_value=_decimal_optional(market_value.get("amount"), "amount"),
        market_value_after_cost=_decimal_optional(
            market_value.get("amountAfterCost"), "amountAfterCost"
        ),
        profit_loss=_decimal_optional(profit_loss.get("amount"), "profitLoss.amount"),
        profit_loss_after_cost=_decimal_optional(
            profit_loss.get("amountAfterCost"), "profitLoss.amountAfterCost"
        ),
        retrieved_at=retrieved_at,
        profit_loss_rate=_decimal_optional(profit_loss.get("rate"), "profitLoss.rate"),
        profit_loss_rate_after_cost=_decimal_optional(
            profit_loss.get("rateAfterCost"), "profitLoss.rateAfterCost"
        ),
        daily_profit_loss=_decimal_optional(
            daily_profit_loss.get("amount"), "dailyProfitLoss.amount"
        ),
        daily_profit_loss_rate=_decimal_optional(
            daily_profit_loss.get("rate"), "dailyProfitLoss.rate"
        ),
        commission=_decimal_optional(cost.get("commission"), "cost.commission"),
        tax=_decimal_optional(cost.get("tax"), "cost.tax"),
    )


def _holdings_summary(item: dict[str, Any]) -> HoldingsSummary:
    market_value = item.get("marketValue")
    profit_loss = item.get("profitLoss")
    daily_profit_loss = item.get("dailyProfitLoss")
    market_value = market_value if isinstance(market_value, dict) else {}
    profit_loss = profit_loss if isinstance(profit_loss, dict) else {}
    daily_profit_loss = daily_profit_loss if isinstance(daily_profit_loss, dict) else {}
    return HoldingsSummary(
        total_purchase_amount=_currency_amounts(item.get("totalPurchaseAmount")),
        market_value=_currency_amounts(market_value.get("amount")),
        market_value_after_cost=_currency_amounts(market_value.get("amountAfterCost")),
        profit_loss=_currency_amounts(profit_loss.get("amount")),
        profit_loss_after_cost=_currency_amounts(profit_loss.get("amountAfterCost")),
        profit_loss_rate=_decimal_optional(profit_loss.get("rate"), "profitLoss.rate"),
        profit_loss_rate_after_cost=_decimal_optional(
            profit_loss.get("rateAfterCost"), "profitLoss.rateAfterCost"
        ),
        daily_profit_loss=_currency_amounts(daily_profit_loss.get("amount")),
        daily_profit_loss_rate=_decimal_optional(
            daily_profit_loss.get("rate"), "dailyProfitLoss.rate"
        ),
    )


def _currency_amounts(value: Any) -> CurrencyAmounts:
    if not isinstance(value, dict):
        return CurrencyAmounts()
    return CurrencyAmounts(
        krw=_decimal_optional(value.get("krw"), "amount.krw"),
        usd=_decimal_optional(value.get("usd"), "amount.usd"),
    )


def _order(item: Any, retrieved_at: datetime | None) -> Order:
    if not isinstance(item, dict) or not isinstance(item.get("orderId"), str):
        raise TossAPIError("returned an invalid order item")
    execution = item.get("execution") or {}
    if not isinstance(execution, dict):
        raise TossAPIError("returned an invalid order item")
    return Order(
        order_id=item["orderId"],
        symbol=_optional_string(item.get("symbol")) or "",
        market_country=_market_country(item),
        exchange=_optional_string(item.get("exchange")),
        currency=_optional_string(item.get("currency")),
        side=_optional_string(item.get("side")),
        order_type=_optional_string(item.get("orderType")),
        status=_optional_string(item.get("status")),
        price=_decimal_optional(item.get("price"), "price"),
        quantity=_decimal_optional(item.get("quantity"), "quantity"),
        order_amount=_decimal_optional(item.get("orderAmount"), "orderAmount"),
        filled_quantity=_decimal_optional(execution.get("filledQuantity"), "filledQuantity"),
        average_filled_price=_decimal_optional(
            execution.get("averageFilledPrice"), "averageFilledPrice"
        ),
        filled_amount=_decimal_optional(execution.get("filledAmount"), "filledAmount"),
        ordered_at=_datetime_optional(item.get("orderedAt"), "orderedAt"),
        canceled_at=_datetime_optional(item.get("canceledAt"), "canceledAt"),
        filled_at=_datetime_optional(execution.get("filledAt"), "filledAt"),
        retrieved_at=retrieved_at,
        commission=_decimal_optional(execution.get("commission"), "execution.commission"),
        tax=_decimal_optional(execution.get("tax"), "execution.tax"),
        settlement_date=_date_optional(execution.get("settlementDate"), "execution.settlementDate"),
    )


def _transaction(item: Any) -> Transaction:
    if not isinstance(item, dict):
        raise TossAPIError("returned an invalid transaction item")
    transaction_type = item.get("transactionType")
    asset_class = item.get("assetClass")
    settled = item.get("settled")
    is_cancellation = item.get("isCancellation")
    if (
        not isinstance(transaction_type, str)
        or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,39}", transaction_type)
        or (asset_class is not None and (
            not isinstance(asset_class, str)
            or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,39}", asset_class)
        ))
        or not isinstance(settled, bool)
        or not isinstance(is_cancellation, bool)
    ):
        raise TossAPIError("returned an invalid transaction item")
    transaction_time = _datetime_optional(item.get("transactionTime"), "transactionTime")
    if transaction_time is not None and transaction_time.tzinfo is None:
        raise TossAPIError("returned an invalid transaction timestamp")
    return Transaction(
        transaction_type=transaction_type,
        asset_class=asset_class,
        settled=settled,
        is_cancellation=is_cancellation,
        symbol=_optional_string(item.get("symbol")),
        market_country=_optional_string(item.get("marketCountry")),
        currency=_optional_string(item.get("currency")),
        quantity=_decimal_optional(item.get("quantity"), "quantity"),
        filled_price=_decimal_optional(item.get("filledPrice"), "filledPrice"),
        amount=_decimal_optional(item.get("amount"), "amount"),
        commission=_decimal_optional(item.get("commission"), "commission"),
        tax=_decimal_optional(item.get("tax"), "tax"),
        net_amount=_decimal_optional(item.get("netAmount"), "netAmount"),
        exchange_rate=_decimal_optional(item.get("exchangeRate"), "exchangeRate"),
        settlement_date=_date_optional(item.get("settlementDate"), "settlementDate"),
        transaction_time=transaction_time,
    )


def _market_price(item: Any, retrieved_at: datetime | None) -> MarketPrice:
    if not isinstance(item, dict):
        raise TossAPIError("returned an invalid price item")
    symbol = item.get("symbol")
    currency = item.get("currency")
    if (
        not isinstance(symbol, str)
        or not _SYMBOL.fullmatch(symbol)
        or not isinstance(currency, str)
        or currency not in {"KRW", "USD"}
    ):
        raise TossAPIError("returned an invalid price item")
    timestamp = _datetime_optional(item.get("timestamp"), "timestamp")
    if timestamp is not None and timestamp.tzinfo is None:
        raise TossAPIError("returned an invalid price timestamp")
    price = _decimal(item.get("lastPrice"), "lastPrice")
    if price <= 0:
        raise TossAPIError("returned an invalid price item")
    return MarketPrice(
        symbol=symbol,
        currency=currency,
        last_price=price,
        timestamp=timestamp,
        retrieved_at=retrieved_at,
    )


def _candle(item: Any) -> Candle:
    if not isinstance(item, dict):
        raise TossAPIError("returned an invalid candle item")
    currency = item.get("currency")
    timestamp = _datetime_optional(item.get("timestamp"), "timestamp")
    if currency not in {"KRW", "USD"} or timestamp is None or timestamp.tzinfo is None:
        raise TossAPIError("returned an invalid candle item")
    open_price = _decimal(item.get("openPrice"), "openPrice")
    high_price = _decimal(item.get("highPrice"), "highPrice")
    low_price = _decimal(item.get("lowPrice"), "lowPrice")
    close_price = _decimal(item.get("closePrice"), "closePrice")
    volume = _decimal(item.get("volume"), "volume")
    if (
        min(open_price, high_price, low_price, close_price) <= 0
        or volume < 0
        or high_price < max(open_price, close_price, low_price)
        or low_price > min(open_price, close_price, high_price)
    ):
        raise TossAPIError("returned an invalid candle item")
    return Candle(
        timestamp=timestamp,
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        close_price=close_price,
        volume=volume,
        currency=currency,
    )


def _decimal(value: Any, field: str) -> Decimal:
    parsed = _decimal_optional(value, field)
    if parsed is None:
        raise TossAPIError("returned a missing numeric field")
    return parsed


def _decimal_optional(value: Any, field: str) -> Decimal | None:
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise TossAPIError(f"returned an invalid numeric field {field}") from None
    if not parsed.is_finite():
        raise TossAPIError(f"returned an invalid numeric field {field}")
    return parsed


def _datetime_optional(value: Any, field: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TossAPIError(f"returned an invalid timestamp field {field}")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise TossAPIError(f"returned an invalid timestamp field {field}") from None


def _date_optional(value: Any, field: str) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TossAPIError(f"returned an invalid date field {field}")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise TossAPIError(f"returned an invalid date field {field}") from None


def _date_string(value: date | str) -> str:
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            pass
    raise ValueError("date filters must be ISO dates.")


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _market_country(item: dict[str, Any]) -> str | None:
    market_country = _optional_string(item.get("marketCountry"))
    if market_country is not None:
        return market_country
    return {"KRW": "KR", "USD": "US"}.get(item.get("currency"))


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
