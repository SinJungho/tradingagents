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

from tradingagents.portfolio.models import (
    Account,
    Accounts,
    BuyingPower,
    Holding,
    Holdings,
    Order,
    Orders,
)

_HOST = "https://openapi.tossinvest.com"
_TOKEN_PATH = "/oauth2/token"
_ALLOWED_READ_PATHS = {
    "/api/v1/accounts",
    "/api/v1/holdings",
    "/api/v1/orders",
    "/api/v1/buying-power",
}
_ORDER_DETAIL_PATH = re.compile(r"^/api/v1/orders/[A-Za-z0-9_-]{1,128}$")
_SYMBOL = re.compile(r"^[A-Za-z0-9.-]{1,32}$")
_ERROR_CODE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_TIMEOUT = (3.05, 10.0)
_MAX_RETRIES = 2
_MAX_PAGES = 3
_PAGE_SIZE = 100
_MAX_RATE_LIMIT_WAIT = 2.0
_EXPIRY_SKEW_SECONDS = 30

_ACCOUNT_WARNING = "Only active brokerage accounts are returned by Toss Securities."
_HOLDINGS_WARNING = (
    "Toss holdings cover KR and US stocks; overseas options and bonds are excluded."
)
_ORDERS_WARNING = (
    "Toss order history excludes order types unsupported by its Open API."
)


class TossAPIError(RuntimeError):
    """A sanitized Toss API error that never includes response bodies or credentials."""

    def __init__(self, message: str, *, status: int | None = None, code: str | None = None):
        self.status = status
        self.code = code
        details = []
        if status is not None:
            details.append(f"HTTP {status}")
        if code is not None:
            details.append(f"code={code}")
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
        return Holdings(
            holdings=holdings,
            retrieved_at=retrieved_at,
            as_of=None,
            coverage_warnings=(_HOLDINGS_WARNING,),
        )

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

    def _get(
        self,
        path: str,
        *,
        account_seq: int | None = None,
        params: dict[str, str | int] | None = None,
    ) -> requests.Response:
        url = f"{_HOST}{path}"
        _validate_business_request("GET", url)
        headers: dict[str, str] = {}
        if account_seq is not None:
            if not _is_int(account_seq) or account_seq <= 0:
                raise ValueError("account_seq must be a positive integer.")
            headers["X-Tossinvest-Account"] = str(account_seq)

        refreshed = False
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
            except requests.Timeout:
                if retries < _MAX_RETRIES:
                    retries += 1
                    continue
                raise TossAPIError("request timed out") from None
            except requests.RequestException:
                if retries < _MAX_RETRIES:
                    retries += 1
                    continue
                raise TossAPIError("request failed") from None

            _validate_response_url(response, url)
            if 300 <= response.status_code < 400 or response.is_redirect:
                raise TossAPIError("refused a redirect", status=response.status_code)
            if response.status_code == 401 and not refreshed:
                self._access_token = None
                self._token_expires_at = 0.0
                refreshed = True
                continue
            if response.status_code == 429 and retries < _MAX_RETRIES:
                wait = _retry_wait(response)
                if wait is not None:
                    retries += 1
                    time.sleep(wait)
                    continue
            if response.status_code >= 500 and retries < _MAX_RETRIES:
                retries += 1
                continue
            if not 200 <= response.status_code < 300:
                raise _response_error(
                    response,
                    sensitive=(self._client_id, self._client_secret, self._access_token or ""),
                )
            return response

    def _get_token(self) -> str:
        if self._access_token and time.monotonic() < self._token_expires_at:
            return self._access_token
        url = f"{_HOST}{_TOKEN_PATH}"
        _validate_auth_request("POST", url)
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
        except requests.RequestException:
            raise TossAPIError("token request failed") from None
        _validate_response_url(response, url)
        if 300 <= response.status_code < 400 or response.is_redirect:
            raise TossAPIError("refused a token redirect", status=response.status_code)
        if not 200 <= response.status_code < 300:
            raise _response_error(response, sensitive=(self._client_id, self._client_secret))
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
    response: requests.Response, *, sensitive: tuple[str, ...] = ()
) -> TossAPIError:
    code: str | None = None
    try:
        error = response.json().get("error")
        candidate = error.get("code") if isinstance(error, dict) else None
        leaks_sensitive_value = isinstance(candidate, str) and any(
            secret and (secret in candidate or candidate in secret) for secret in sensitive
        )
        if (
            isinstance(candidate, str)
            and _ERROR_CODE.fullmatch(candidate)
            and not leaks_sensitive_value
        ):
            code = candidate
    except (ValueError, requests.JSONDecodeError, AttributeError):
        pass
    return TossAPIError("request failed", status=response.status_code, code=code)


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
    if not isinstance(market_value, dict) or not isinstance(profit_loss, dict):
        raise TossAPIError("returned an invalid holding item")
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
    raise ValueError("order date filters must be ISO dates.")


def _retry_wait(response: requests.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if not isinstance(value, str) or not value.strip().isdigit():
        return None
    seconds = int(value.strip())
    if seconds > _MAX_RATE_LIMIT_WAIT:
        return None
    return float(seconds)


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _market_country(item: dict[str, Any]) -> str | None:
    market_country = _optional_string(item.get("marketCountry"))
    if market_country is not None:
        return market_country
    return {"KRW": "KR", "USD": "US"}.get(item.get("currency"))


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
