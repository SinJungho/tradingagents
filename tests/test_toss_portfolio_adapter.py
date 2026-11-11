from datetime import UTC, datetime
from decimal import Decimal

import pytest
import requests

from tradingagents.portfolio.toss import (
    TossAPIError,
    TossPortfolioAdapter,
    _validate_auth_request,
    _validate_business_request,
)

HOST = "https://openapi.tossinvest.com"


class FakeResponse:
    def __init__(self, status=200, payload=None, headers=None, url=None):
        self.status_code = status
        self._payload = payload or {}
        self.headers = headers or {}
        self.url = url
        self.is_redirect = 300 <= status < 400

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    def __init__(self, token_payload=None, responses=None, token_response=None):
        self.token_payload = token_payload or {
            "access_token": "synthetic-token",
            "expires_in": 3600,
        }
        self.token_response = token_response
        self.responses = list(responses or [])
        self.posts = []
        self.gets = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        if self.token_response is not None:
            if isinstance(self.token_response, Exception):
                raise self.token_response
            return self.token_response
        return FakeResponse(payload=self.token_payload)

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        if not self.responses:
            raise AssertionError("unexpected GET")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _ok(result, *, date_header="Mon, 09 Nov 2026 03:00:00 GMT"):
    return FakeResponse(payload={"result": result}, headers={"Date": date_header})


def test_token_post_is_the_only_post_and_uses_fixed_auth_endpoint():
    session = FakeSession(responses=[_ok([])])
    adapter = TossPortfolioAdapter("synthetic-client", "synthetic-secret", session=session)

    assert adapter.get_accounts().accounts == ()

    assert len(session.posts) == 1
    url, options = session.posts[0]
    assert url == f"{HOST}/oauth2/token"
    assert options["data"] == {
        "grant_type": "client_credentials",
        "client_id": "synthetic-client",
        "client_secret": "synthetic-secret",
    }
    assert options["allow_redirects"] is False
    assert options["timeout"] == (3.05, 10.0)
    assert [call[0] for call in session.gets] == [f"{HOST}/api/v1/accounts"]
    assert session.gets[0][1]["allow_redirects"] is False
    assert session.gets[0][1]["headers"]["Authorization"] == "Bearer synthetic-token"


@pytest.mark.parametrize(
    "method,url",
    [
        ("POST", f"{HOST}/api/v1/accounts"),
        ("GET", "https://evil.example/api/v1/accounts"),
        ("GET", f"{HOST}/api/v1/accounts/extra"),
        ("GET", f"{HOST}/api/v1/orders/abc/cancel"),
        ("GET", f"{HOST}/api/v1/orders/abc?extra=1"),
        ("GET", "http://openapi.tossinvest.com/api/v1/accounts"),
        ("GET", "https://openapi.tossinvest.com.evil.example/api/v1/accounts"),
    ],
)
def test_business_validation_denies_method_host_and_unapproved_paths(method, url):
    with pytest.raises(TossAPIError, match="unapproved business request"):
        _validate_business_request(method, url)


@pytest.mark.parametrize(
    "method,url",
    [
        ("GET", f"{HOST}/oauth2/token"),
        ("POST", f"{HOST}/api/v1/orders"),
        ("POST", "https://evil.example/oauth2/token"),
        ("POST", f"{HOST}/oauth2/token/extra"),
    ],
)
def test_auth_validation_allows_only_exact_token_post(method, url):
    with pytest.raises(TossAPIError, match="unapproved token request"):
        _validate_auth_request(method, url)


def test_redirect_response_is_rejected_without_follow_up():
    session = FakeSession(responses=[FakeResponse(302, headers={"Location": "https://evil.example"})])
    adapter = TossPortfolioAdapter("id", "secret", session=session)

    with pytest.raises(TossAPIError, match="refused a redirect"):
        adapter.get_accounts()

    assert len(session.gets) == 1


def test_token_endpoint_failures_and_redirects_are_sanitized():
    failure = FakeSession(
        token_response=FakeResponse(
            401,
            {"error": {"code": "invalid_client", "message": "synthetic secret echoed"}},
        ),
        responses=[_ok([])],
    )
    adapter = TossPortfolioAdapter("synthetic-id", "synthetic-secret", session=failure)
    with pytest.raises(TossAPIError) as exc:
        adapter.get_accounts()
    assert exc.value.status == 401
    assert exc.value.category == "authentication"
    assert failure.posts and len(failure.posts) == 1
    assert "synthetic secret echoed" not in str(exc.value)
    assert "synthetic-secret" not in str(exc.value)
    assert failure.gets == []

    redirect = FakeSession(
        token_response=FakeResponse(302, headers={"Location": "https://evil.example"})
    )
    adapter = TossPortfolioAdapter("id", "secret", session=redirect)
    with pytest.raises(TossAPIError, match="token redirect"):
        adapter.get_accounts()
    assert redirect.gets == []


def test_token_server_failure_retries_only_to_the_configured_bound():
    session = FakeSession(
        token_response=FakeResponse(
            503,
            {"error": {"code": "synthetic-account-id", "message": "private response"}},
        )
    )
    adapter = TossPortfolioAdapter("synthetic-id", "synthetic-secret", session=session)

    with pytest.raises(TossAPIError) as exc:
        adapter.get_accounts()

    assert len(session.posts) == 3
    assert session.gets == []
    assert exc.value.category == "provider_server"
    assert exc.value.retryable is True
    assert "private response" not in str(exc.value)
    assert "synthetic-account-id" not in str(exc.value)


def test_authentication_rejection_is_not_repeated():
    session = FakeSession(
        responses=[
            FakeResponse(401, {"error": {"code": "invalid-token"}}),
            _ok([]),
        ]
    )
    adapter = TossPortfolioAdapter("id", "secret", session=session)

    with pytest.raises(TossAPIError) as exc:
        adapter.get_accounts()

    assert exc.value.category == "authentication"
    assert exc.value.retryable is False
    assert len(session.posts) == 1
    assert len(session.gets) == 1


def test_cached_token_is_reissued_after_expiry(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("tradingagents.portfolio.toss.time.monotonic", lambda: now[0])
    session = FakeSession(
        token_payload={"access_token": "synthetic-token", "expires_in": 60},
        responses=[_ok([]), _ok([])],
    )
    adapter = TossPortfolioAdapter("id", "secret", session=session)

    adapter.get_accounts()
    now[0] = 131.0
    adapter.get_accounts()

    assert len(session.posts) == 2


def test_rate_limit_is_classified_without_retry():
    session = FakeSession(
        responses=[
            FakeResponse(429, {"error": {"code": "rate-limit-exceeded"}}, {"Retry-After": "1"}),
        ]
    )
    adapter = TossPortfolioAdapter("id", "secret", session=session)

    with pytest.raises(TossAPIError) as exc:
        adapter.get_accounts()

    assert exc.value.category == "rate_limit"
    assert exc.value.retryable is False
    assert len(session.gets) == 1


def test_account_quota_error_does_not_retry_or_expose_response():
    session = FakeSession(
        responses=[
            FakeResponse(
                429,
                {"error": {"code": "synthetic-account-id", "message": "private quota details"}},
                {"Retry-After": "999"},
            ),
        ]
    )
    adapter = TossPortfolioAdapter("id", "secret", session=session)

    with pytest.raises(TossAPIError) as exc:
        adapter.get_accounts()

    assert exc.value.status == 429
    assert exc.value.category == "rate_limit"
    assert len(session.gets) == 1
    assert "private quota details" not in str(exc.value)
    assert "synthetic-account-id" not in str(exc.value)


def test_failures_exhaust_finite_retries_and_do_not_expose_raw_body():
    session = FakeSession(
        responses=[
            FakeResponse(500, {"error": {"code": "internal-error", "message": "private account data"}}),
            FakeResponse(500, {"error": {"code": "internal-error", "message": "private account data"}}),
            FakeResponse(500, {"error": {"code": "internal-error", "message": "private account data"}}),
        ]
    )
    adapter = TossPortfolioAdapter("synthetic-id", "synthetic-secret", session=session)

    with pytest.raises(TossAPIError) as exc:
        adapter.get_accounts()

    assert len(session.gets) == 3
    assert exc.value.status == 500
    assert exc.value.category == "provider_server"
    assert exc.value.retryable is True
    assert "private account data" not in str(exc.value)
    assert "synthetic-secret" not in str(exc.value)


def test_error_code_that_echoes_credentials_is_not_returned():
    session = FakeSession(
        responses=[
            FakeResponse(500, {"error": {"code": "synthetic-secret"}}),
            FakeResponse(500, {"error": {"code": "synthetic-secret"}}),
            FakeResponse(500, {"error": {"code": "synthetic-secret"}}),
        ]
    )
    adapter = TossPortfolioAdapter("id", "synthetic-secret", session=session)

    with pytest.raises(TossAPIError) as exc:
        adapter.get_accounts()

    assert exc.value.category == "provider_server"
    assert "synthetic-secret" not in str(exc.value)


def test_timeout_retries_are_bounded_and_sanitized():
    session = FakeSession(
        responses=[requests.Timeout("synthetic token in exception"), requests.Timeout("still private"), requests.Timeout()]
    )
    adapter = TossPortfolioAdapter("id", "secret", session=session)

    with pytest.raises(TossAPIError, match="request timed out") as exc:
        adapter.get_accounts()

    assert len(session.gets) == 3
    assert "synthetic token" not in str(exc.value)


def test_account_holdings_and_buying_power_are_normalized():
    retrieved_at = datetime(2026, 11, 9, 0, 3, 21, tzinfo=UTC)
    session = FakeSession(
        responses=[
            _ok(
                [{"accountSeq": 7, "accountType": "BROKERAGE"}],
                date_header="Mon, 09 Nov 2026 00:03:21 GMT",
            ),
            _ok(
                {
                    "totalPurchaseAmount": {"krw": "130000", "usd": "45"},
                    "marketValue": {
                        "amount": {"krw": "140000.5", "usd": "50"},
                        "amountAfterCost": {"krw": "139000", "usd": "49"},
                    },
                    "profitLoss": {
                        "amount": {"krw": "10000.5", "usd": "5"},
                        "amountAfterCost": {"krw": "9000", "usd": "4"},
                        "rate": "0.08",
                        "rateAfterCost": "0.06",
                    },
                    "dailyProfitLoss": {
                        "amount": {"krw": "2000", "usd": "1"},
                        "rate": "0.01",
                    },
                    "items": [
                        {
                            "symbol": "005930",
                            "name": "Synthetic KR",
                            "marketCountry": "KR",
                            "exchange": "KRX",
                            "currency": "KRW",
                            "quantity": "2",
                            "lastPrice": "70000.25",
                            "averagePurchasePrice": "65000",
                            "marketValue": {
                                "purchaseAmount": "130000",
                                "amount": "140000.5",
                                "amountAfterCost": "139000",
                            },
                            "profitLoss": {"amount": "10000.5", "amountAfterCost": "9000", "rate": "0.08", "rateAfterCost": "0.06"},
                            "dailyProfitLoss": {"amount": "2000", "rate": "0.01"},
                            "cost": {"commission": "10", "tax": "20"},
                        },
                        {
                            "symbol": "SYNUS",
                            "name": "Synthetic US",
                            "marketCountry": "US",
                            "exchange": "NASDAQ",
                            "currency": "USD",
                            "quantity": "0.5",
                            "lastPrice": "100",
                            "averagePurchasePrice": "90",
                            "marketValue": {"purchaseAmount": "45", "amount": "50", "amountAfterCost": "49"},
                            "profitLoss": {"amount": "5", "amountAfterCost": "4"},
                        },
                    ]
                },
                date_header="Mon, 09 Nov 2026 00:03:21 GMT",
            ),
            _ok(
                {"currency": "USD", "cashBuyingPower": "3500.50"},
                date_header="Mon, 09 Nov 2026 00:03:21 GMT",
            ),
        ]
    )
    adapter = TossPortfolioAdapter("id", "secret", session=session)

    accounts = adapter.get_accounts()
    holdings = adapter.get_holdings(7)
    buying_power = adapter.get_buying_power(7, "USD")

    assert accounts.accounts[0].account_seq == 7
    assert accounts.accounts[0].account_type == "BROKERAGE"
    assert not hasattr(accounts.accounts[0], "account_no")
    assert accounts.retrieved_at == retrieved_at
    assert accounts.coverage_warnings
    assert holdings.retrieved_at == retrieved_at
    assert holdings.as_of is None
    assert [(item.market_country, item.exchange, item.currency) for item in holdings.holdings] == [
        ("KR", "KRX", "KRW"),
        ("US", "NASDAQ", "USD"),
    ]
    assert holdings.holdings[0].quantity == Decimal("2")
    assert holdings.holdings[0].last_price == Decimal("70000.25")
    assert holdings.holdings[0].market_value == Decimal("140000.5")
    assert holdings.holdings[0].profit_loss_rate == Decimal("0.08")
    assert holdings.holdings[0].daily_profit_loss == Decimal("2000")
    assert holdings.holdings[0].commission == Decimal("10")
    assert holdings.summary.total_purchase_amount.krw == Decimal("130000")
    assert holdings.summary.daily_profit_loss_rate == Decimal("0.01")
    assert holdings.holdings[0].retrieved_at == retrieved_at
    assert buying_power.cash_buying_power == Decimal("3500.50")
    assert buying_power.currency == "USD"
    assert buying_power.retrieved_at == retrieved_at
    assert [url for url, _ in session.gets] == [
        f"{HOST}/api/v1/accounts",
        f"{HOST}/api/v1/holdings",
        f"{HOST}/api/v1/buying-power",
    ]


def test_orders_preserve_order_and_filled_quantities_times_market_and_exchange():
    session = FakeSession(
        responses=[
            _ok(
                {
                    "orders": [
                        {
                            "orderId": "synthetic-order-1",
                            "symbol": "SYNUS",
                            "marketCountry": "US",
                            "exchange": "NASDAQ",
                            "side": "BUY",
                            "orderType": "LIMIT",
                            "status": "PARTIAL_FILLED",
                            "price": "100.5",
                            "quantity": "3",
                            "orderAmount": None,
                            "currency": "USD",
                            "orderedAt": "2026-11-09T09:30:00+09:00",
                            "canceledAt": None,
                            "execution": {
                                "filledQuantity": "1.25",
                                "averageFilledPrice": "100.25",
                                "filledAmount": "125.3125",
                                "filledAt": "2026-11-09T09:31:00+09:00",
                                "commission": "0.25",
                                "tax": "0.10",
                                "settlementDate": "2026-11-11",
                            },
                        }
                    ],
                    "nextCursor": None,
                    "hasNext": False,
                }
            )
        ]
    )
    adapter = TossPortfolioAdapter("id", "secret", session=session)

    orders = adapter.get_orders(7, "OPEN")
    order = orders.orders[0]

    assert order.quantity == Decimal("3")
    assert order.filled_quantity == Decimal("1.25")
    assert order.market_country == "US"
    assert order.exchange == "NASDAQ"
    assert order.currency == "USD"
    assert order.ordered_at.isoformat() == "2026-11-09T09:30:00+09:00"
    assert order.filled_at.isoformat() == "2026-11-09T09:31:00+09:00"
    assert order.commission == Decimal("0.25")
    assert order.tax == Decimal("0.10")
    assert order.settlement_date.isoformat() == "2026-11-11"
    assert orders.retrieved_at == datetime(2026, 11, 9, 3, 0, tzinfo=UTC)
    assert order.retrieved_at == datetime(2026, 11, 9, 3, 0, tzinfo=UTC)
    assert order.ordered_at != order.retrieved_at
    assert orders.coverage_warnings


def test_order_details_and_closed_order_pagination_are_bounded():
    page = {
        "orders": [
            {
                "orderId": "synthetic-order-2",
                "symbol": "005930",
                "currency": "KRW",
                "quantity": "2",
                "execution": {"filledQuantity": "2"},
            }
        ],
        "hasNext": True,
        "nextCursor": "synthetic-cursor",
    }
    detail = {
        "orderId": "synthetic-order-2",
        "symbol": "005930",
        "currency": "KRW",
        "quantity": "2",
        "execution": {"filledQuantity": "2"},
    }
    session = FakeSession(responses=[_ok(page), _ok(page), _ok(page), _ok(detail)])
    adapter = TossPortfolioAdapter("id", "secret", session=session)

    listed = adapter.get_orders(7, "CLOSED")
    detail = adapter.get_order(7, "synthetic-order-2")

    assert len(listed.orders) == 1
    assert listed.has_more is True
    assert any("three-page limit" in warning for warning in listed.coverage_warnings)
    assert any("Duplicate CLOSED order records" in warning for warning in listed.coverage_warnings)
    assert detail.order_id == "synthetic-order-2"
    assert detail.quantity == Decimal("2")
    assert detail.filled_quantity == Decimal("2")
    assert detail.market_country == "KR"
    assert len(session.gets) == 4
    assert all(url == f"{HOST}/api/v1/orders" for url, _ in session.gets[:3])
    assert session.gets[3][0] == f"{HOST}/api/v1/orders/synthetic-order-2"
    assert session.gets[1][1]["params"]["cursor"] == "synthetic-cursor"


def test_closed_orders_dedupe_order_ids_and_report_duplicate_coverage():
    duplicate = {
        "orderId": "synthetic-duplicate-order",
        "symbol": "005930",
        "currency": "KRW",
        "quantity": "2",
        "execution": {"filledQuantity": "2"},
    }
    final = {**duplicate, "orderId": "synthetic-final-order"}
    first_page = {"orders": [duplicate], "hasNext": True, "nextCursor": "cursor-1"}
    repeated_page = {"orders": [duplicate], "hasNext": True, "nextCursor": "cursor-2"}
    final_page = {"orders": [final], "hasNext": False, "nextCursor": None}
    session = FakeSession(responses=[_ok(first_page), _ok(repeated_page), _ok(final_page)])
    adapter = TossPortfolioAdapter("id", "secret", session=session)

    orders = adapter.get_orders(7, "CLOSED")

    assert [order.order_id for order in orders.orders] == [
        "synthetic-duplicate-order",
        "synthetic-final-order",
    ]
    assert orders.has_more is False
    assert any("Duplicate CLOSED order records" in warning for warning in orders.coverage_warnings)


def test_final_response_url_is_checked_even_when_session_says_success():
    session = FakeSession(
        responses=[
            FakeResponse(
                200,
                {"result": []},
                url="https://evil.example/api/v1/accounts",
            )
        ]
    )
    adapter = TossPortfolioAdapter("id", "secret", session=session)

    with pytest.raises(TossAPIError, match="unapproved URL"):
        adapter.get_accounts()

    assert len(session.gets) == 1


def test_invalid_order_id_is_rejected_before_any_request():
    session = FakeSession()
    adapter = TossPortfolioAdapter("id", "secret", session=session)

    with pytest.raises(ValueError, match="order_id"):
        adapter.get_order(7, "../cancel")

    assert session.posts == []
    assert session.gets == []


def test_non_finite_decimal_is_rejected():
    session = FakeSession(
        responses=[
            _ok({"currency": "USD", "cashBuyingPower": "NaN"}),
        ]
    )
    adapter = TossPortfolioAdapter("id", "secret", session=session)

    with pytest.raises(TossAPIError, match="invalid numeric field"):
        adapter.get_buying_power(7, "USD")


def test_exchange_rate_uses_official_pair_and_preserves_validity_window():
    session = FakeSession(
        responses=[
            _ok(
                {
                    "baseCurrency": "USD",
                    "quoteCurrency": "KRW",
                    "rate": "1380.5",
                    "midRate": "1375",
                    "validFrom": "2026-11-09T12:00:00+09:00",
                    "validUntil": "2026-11-09T12:01:00+09:00",
                }
            )
        ]
    )
    adapter = TossPortfolioAdapter("synthetic-id", "synthetic-secret", session=session)

    rate = adapter.get_exchange_rate()

    assert rate.base_currency == "USD"
    assert rate.quote_currency == "KRW"
    assert rate.rate == Decimal("1380.5")
    assert rate.mid_rate == Decimal("1375")
    assert rate.valid_until.isoformat() == "2026-11-09T12:01:00+09:00"
    assert session.gets[0][0] == f"{HOST}/api/v1/exchange-rate"
    assert session.gets[0][1]["params"] == {"baseCurrency": "USD", "quoteCurrency": "KRW"}
    assert "X-Tossinvest-Account" not in session.gets[0][1]["headers"]


def test_transactions_are_privacy_minimized_and_paginated():
    first = {
        "transactions": [
            {
                "transactionType": "BUY",
                "assetClass": "OPTION",
                "settled": True,
                "isCancellation": False,
                "symbol": "SYNTHETIC-OPTION",
                "currency": "USD",
                "quantity": "2",
                "filledPrice": "49.995",
                "amount": "99.99",
                "commission": "0.01",
                "tax": "0",
                "netAmount": "100",
                "exchangeRate": "1380.5",
                "settlementDate": "2026-11-10",
                "transactionTime": "2026-11-09T10:00:00+09:00",
            }
        ],
        "nextCursor": "synthetic-cursor",
        "hasNext": True,
    }
    second = {
        "transactions": [
            {
                "transactionType": "INTEREST",
                "assetClass": "BOND",
                "settled": False,
                "isCancellation": True,
                "symbol": "SYNTHETIC-BOND",
                "amount": "15.25",
            },
            {
                "transactionType": "DEPOSIT",
                "assetClass": None,
                "settled": True,
                "isCancellation": False,
                "amount": "500",
            },
        ],
        "nextCursor": None,
        "hasNext": False,
    }
    session = FakeSession(responses=[_ok(first), _ok(second)])
    adapter = TossPortfolioAdapter("synthetic-id", "synthetic-secret", session=session)

    transactions = adapter.get_transactions(
        7, from_date="2026-10-01", to_date="2026-11-01"
    )

    assert [(row.transaction_type, row.asset_class, row.settled, row.is_cancellation) for row in transactions.transactions] == [
        ("BUY", "OPTION", True, False),
        ("INTEREST", "BOND", False, True),
        ("DEPOSIT", None, True, False),
    ]
    assert "SYNTHETIC-OPTION" not in repr(transactions)
    assert "99.99" not in repr(transactions)
    assert transactions.transactions[0].currency == "USD"
    assert transactions.transactions[0].filled_price == Decimal("49.995")
    assert transactions.transactions[0].net_amount == Decimal("100")
    assert "49.995" not in repr(transactions)
    assert transactions.has_more is False
    assert len(session.gets) == 2
    first_params = session.gets[0][1]["params"]
    assert first_params == {"limit": 100, "from": "2026-10-01", "to": "2026-11-01"}
    assert session.gets[1][1]["params"]["cursor"] == "synthetic-cursor"
    assert session.gets[0][1]["headers"]["X-Tossinvest-Account"] == "7"


def test_market_data_prices_and_candles_use_only_approved_get_paths():
    session = FakeSession(
        responses=[
            _ok([{"symbol": "SYNUS", "timestamp": "2026-11-09T09:30:00+09:00", "lastPrice": "101.5", "currency": "USD"}]),
            _ok({"candles": [{"timestamp": "2026-11-09T00:00:00+09:00", "openPrice": "100", "highPrice": "103", "lowPrice": "99", "closePrice": "101", "volume": "1000", "currency": "USD"}], "nextBefore": None}),
        ]
    )
    adapter = TossPortfolioAdapter("id", "secret", session=session)

    price = adapter.get_prices(["SYNUS"])[0]
    candles = adapter.get_candles("SYNUS", count=1)

    assert price.last_price == Decimal("101.5")
    assert price.timestamp.isoformat() == "2026-11-09T09:30:00+09:00"
    assert candles.candles[0].close_price == Decimal("101")
    assert candles.candles[0].volume == Decimal("1000")
    assert [url for url, _ in session.gets] == [f"{HOST}/api/v1/prices", f"{HOST}/api/v1/candles"]
    assert session.gets[0][1]["params"] == {"symbols": "SYNUS"}
    assert session.gets[1][1]["params"] == {"symbol": "SYNUS", "interval": "1d", "count": 1, "adjusted": True}


@pytest.mark.parametrize(
    "symbol,kwargs",
    [("bad/symbol", {}), ("SYNUS", {"count": 201}), ("SYNUS", {"interval": "5m"})],
)
def test_market_data_invalid_requests_are_rejected_before_network(symbol, kwargs):
    session = FakeSession()
    adapter = TossPortfolioAdapter("id", "secret", session=session)

    with pytest.raises(ValueError):
        adapter.get_candles(symbol, **kwargs)

    assert not session.posts and not session.gets


def test_transaction_pagination_stops_at_ten_pages_and_marks_remaining_data():
    pages = [
        _ok(
            {
                "transactions": [],
                "nextCursor": f"synthetic-cursor-{index}",
                "hasNext": True,
            }
        )
        for index in range(10)
    ]
    session = FakeSession(responses=pages)
    adapter = TossPortfolioAdapter("id", "secret", session=session)

    transactions = adapter.get_transactions(7)

    assert len(session.gets) == 10
    assert transactions.has_more is True
    assert any("ten-page limit" in warning for warning in transactions.coverage_warnings)


def test_unauthorized_error_body_never_appears_in_exception():
    session = FakeSession(
        responses=[
            FakeResponse(
                401,
                {"error": {"code": "invalid-token", "message": "synthetic account response"}},
            ),
            FakeResponse(
                401,
                {"error": {"code": "invalid-token", "message": "synthetic account response"}},
            ),
        ]
    )
    adapter = TossPortfolioAdapter("synthetic-id", "synthetic-secret", session=session)

    with pytest.raises(TossAPIError) as exc:
        adapter.get_accounts()

    assert "synthetic account response" not in str(exc.value)
    assert "synthetic-secret" not in str(exc.value)
