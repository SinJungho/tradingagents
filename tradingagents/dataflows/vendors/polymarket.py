"""Polymarket prediction-market vendor.

Surfaces live, market-implied probabilities for forward-looking events (Fed
decisions, recession, elections, geopolitics, crypto) to the news analyst, as a
complement to news (what happened) and FRED macro data (where things stand):
what the crowd actually prices to happen next.

Uses Polymarket's public Gamma API (https://gamma-api.polymarket.com) — no key,
no auth. Each market's ``outcomePrices`` are the implied probabilities of its
outcomes (a "Yes" at 0.76 means the market prices a 76% chance).
"""
import json
import logging
import math
import re
import socket
from datetime import UTC, datetime

import requests

from tradingagents.api_diagnostics import (
    APIFailure,
    EndpointProbe,
    _NoNetrcAuth,
    classify_api_failure,
)
from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.date_window import is_historical
from tradingagents.dataflows.errors import (
    record_source_failure,
    source_circuit_error,
    trip_source_circuit,
)
from tradingagents.dataflows.net import get_with_retry
from tradingagents.default_config import validate_polymarket_transport

logger = logging.getLogger(__name__)

GAMMA_BASE = "https://gamma-api.polymarket.com"

# Network timeout (seconds), consistent with the other vendors.
REQUEST_TIMEOUT = 30

# Default number of markets to return, ranked by traded volume.
DEFAULT_LIMIT = 6


def _unavailable_message(topic: str) -> str:
    return (
        f"Polymarket data is unavailable for '{topic}'. Do not write, invent, or "
        "estimate prediction-market odds or numbers; explicitly state that this "
        "source is unavailable."
    )


def transport_target(config=None):
    config = get_config() if config is None else config
    mode = validate_polymarket_transport(config.get("polymarket_transport", "cloudfront_alias"))
    if mode == "direct":
        return GAMMA_BASE, {}
    try:
        records = socket.getaddrinfo(
            "gamma-api.polymarket.com", 443, flags=socket.AI_CANONNAME,
        )
    except OSError:
        raise requests.ConnectionError("Polymarket alias DNS resolution failed") from None
    names = {record[3].rstrip(".").lower() for record in records if record[3]}
    aliases = {
        name for name in names
        if re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+cloudfront\.net", name)
        and len(name) <= 253
    }
    if len(aliases) != 1:
        raise requests.ConnectionError("Polymarket CloudFront alias unavailable")
    return f"https://{aliases.pop()}", {"Host": "gamma-api.polymarket.com"}


def probe_transport(config):
    """HEAD reachability only; this does not validate search GET."""
    base, headers = transport_target(config)
    with requests.Session() as session:
        session.auth = _NoNetrcAuth()
        try:
            session.head(base, headers=headers, timeout=3, verify=True, allow_redirects=False)
            return EndpointProbe(True)
        except requests.RequestException as error:
            return EndpointProbe(False, classify_api_failure(error))


def _request(path: str, params: dict) -> dict:
    base, headers = transport_target()
    mode = get_config().get("polymarket_transport", "cloudfront_alias")
    response = get_with_retry(
        f"{base}/{path}",
        params=params,
        headers=headers,
        timeout=REQUEST_TIMEOUT,
        provider=f"Polymarket/{mode}",
        request_options={"verify": True, "allow_redirects": False, "auth": _NoNetrcAuth()},
        reject_redirects=True,
    )
    data = response.json()
    if not isinstance(data, dict) or not isinstance(data.get("events"), list):
        error = requests.RequestException("Invalid Polymarket search structure")
        error.failure = APIFailure("provider_response", False)
        raise error
    return data


def _parse_json_list(value) -> list:
    """Gamma encodes ``outcomes``/``outcomePrices`` as JSON-string arrays."""
    if isinstance(value, list):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []


def _is_forward_looking(market: dict, now: datetime) -> bool:
    """Keep only open markets that resolve in the future.

    ``closed`` is the reliable resolved flag (``active`` stays True even for
    settled markets), and a past ``endDate`` means the event already resolved —
    either way it is not a forward-looking signal.
    """
    if market.get("closed"):
        return False
    end_date = market.get("endDate")
    if end_date:
        try:
            if datetime.fromisoformat(end_date.replace("Z", "+00:00")) < now:
                return False
        except ValueError:
            pass
    return bool(_parse_json_list(market.get("outcomePrices"))) and bool(
        _parse_json_list(market.get("outcomes"))
    )


def _odds(prob: float) -> str:
    """A probability as a percentage; within 1% of 0 or 100 its distance from
    there keeps two significant digits, so 0.05% is not 0% and 99.95% not 100%."""
    def decimals(distance: float) -> int:
        return 1 - math.floor(math.log10(distance))

    if 0 < prob < 0.01:
        percent = prob * 100
        return f"{percent:.{decimals(percent)}f}".rstrip("0").rstrip(".") + "%"
    if 0.99 < prob < 1:
        distance = (1 - prob) * 100
        return f"{100 - distance:.{decimals(distance)}f}".rstrip("0").rstrip(".") + "%"
    return f"{prob:.0%}"


def get_prediction_markets(topic: str, limit: int | None = None, as_of_date: str | None = None) -> str:
    """Return live prediction-market probabilities for an event topic.

    Args:
        topic: Event keyword(s), e.g. "Fed rate cut", "recession 2026",
            "US election", or a sector/company event.
        limit: Max markets to return (ranked by traded volume); ``None`` uses
            DEFAULT_LIMIT.
        as_of_date: The analysis date. Polymarket serves only live odds, so a
            date before today withholds them.

    Returns:
        A markdown report of the most-traded open markets matching the topic,
        each with its implied probability, traded volume, resolution date, and
        recent (1-week) move.
    """
    if is_historical(as_of_date):
        return (
            f"Prediction-market odds are withheld for {as_of_date}. Polymarket serves "
            f"only live odds on open markets, with no historical vintage, so serving "
            f"them would put post-decision information into a {as_of_date} analysis."
        )
    if limit is None:
        limit = DEFAULT_LIMIT

    circuit_error = source_circuit_error("get_prediction_markets")
    if circuit_error is not None:
        record_source_failure("get_prediction_markets", circuit_error)
        return _unavailable_message(topic)

    try:
        data = _request("public-search", {"q": topic, "limit_per_type": 20})
    except requests.RequestException as e:
        logger.warning(
            "API fetch failed provider=Polymarket mode=%s category=%s status=%s",
            get_config().get("polymarket_transport", "cloudfront_alias"),
            classify_api_failure(e).category,
            getattr(e, "status_code", None),
        )
        record_source_failure("get_prediction_markets", e)
        if isinstance(e, (requests.ConnectionError, requests.Timeout)):
            trip_source_circuit("get_prediction_markets", e)
        return _unavailable_message(topic)

    now = datetime.now(UTC)
    candidates = [
        m
        for event in data.get("events", [])
        for m in event.get("markets", [])
        if _is_forward_looking(m, now)
    ]
    candidates.sort(key=lambda m: m.get("volumeNum") or 0, reverse=True)

    header = (
        f'## Polymarket prediction markets: "{topic}"\n'
        f"Live, market-implied probabilities (higher traded volume = deeper, "
        f"more reliable). A probability is the crowd's priced odds of the event, "
        f"not a forecast you should take as certain.\n\n"
    )

    if not candidates:
        return header + (
            f"No open prediction markets matched '{topic}'. Polymarket coverage "
            f"is concentrated in macro, political, geopolitical, and crypto "
            f"events; a specific equity may have none."
        )

    lines = []
    for m in candidates[:limit]:
        prices = _parse_json_list(m.get("outcomePrices"))
        outcomes = _parse_json_list(m.get("outcomes"))
        try:
            prob = float(prices[0])
        except (ValueError, IndexError):
            continue
        label = outcomes[0] if outcomes else "Yes"
        volume = m.get("volumeNum") or 0
        end_date = (m.get("endDate") or "")[:10]
        wk = m.get("oneWeekPriceChange")
        wk_str = (
            f", 1-week {wk * 100:+.1f}pp"
            if isinstance(wk, (int, float)) and wk
            else ""
        )
        lines.append(
            f"- **{m.get('question')}** — {label} {_odds(prob)} "
            f"(${volume:,.0f} volume, resolves {end_date}{wk_str})"
        )

    return header + "\n".join(lines) + "\n"
