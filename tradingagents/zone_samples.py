"""Local, identifier-minimized chart-zone sample manifests."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from tradingagents.dataflows.files import replace_file

FIXED_SAMPLE = {
    "m7": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"],
    "user_selected": ["KO", "UBER", "BA", "IREN", "IONQ", "NFLX", "AAOI"],
    "sector": ["HD", "PG", "JNJ", "UNH", "JPM", "BRK-B", "CAT", "HON", "XOM", "CVX",
               "NEE", "DUK", "APD", "SHW", "PLD", "AMT"],
    "high_volatility": ["AMD", "MU", "ENPH", "SMCI", "FSLR", "CCL"],
    "etf_1x": ["SPY", "QQQ", "IWM", "GLD", "TLT", "SOXX"],
    "etf_2x": ["SSO", "QLD", "USD"],
    "etf_3x": ["UPRO", "TQQQ", "SOXL"],
}


def sample_directory() -> Path:
    return Path.home() / ".tradingagents" / "zone-backtest" / "samples"


def write_sample(
    *, holdings: list[str], retrieved_at: str, priority_tickers: list[str], root: Path | None = None
) -> dict:
    """Write an immutable sample version with only normalized ticker identifiers."""
    root = root or sample_directory()
    previous_first_seen: dict[str, str] = {}
    if root.exists():
        for path in sorted(root.glob("v1-*.json")):
            try:
                previous = json.loads(path.read_text(encoding="utf-8"))
                previous_first_seen.update(previous.get("holdings_first_seen", {}))
            except (OSError, json.JSONDecodeError):
                continue
    fixed = {group: sorted(tickers) for group, tickers in FIXED_SAMPLE.items()}
    base = sorted({ticker for tickers in fixed.values() for ticker in tickers})
    normalized = set()
    for ticker in holdings:
        value = ticker.strip().upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]*", value):
            raise ValueError("Unsupported ticker in sample input.")
        normalized.add(value)
    normalized_priority = set()
    for ticker in priority_tickers:
        value = ticker.strip().upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]*", value):
            raise ValueError("Unsupported priority ticker in sample input.")
        normalized_priority.add(value)
    additions = sorted((set(previous_first_seen) | normalized) - set(base))
    priority = sorted(normalized_priority & (set(base) | set(additions)))
    all_tickers = sorted(set(base) | set(additions))
    ordered_tickers = priority + [ticker for ticker in all_tickers if ticker not in normalized_priority]
    first_seen = {
        ticker: previous_first_seen.get(ticker, retrieved_at)
        for ticker in additions
    }
    payload = {
        "base_version": "v1", "fixed_groups": fixed, "base_tickers": base,
        "holdings_added": additions, "priority_tickers": priority,
        "holdings_first_seen": first_seen,
        "tickers": all_tickers,
        "ordered_tickers": ordered_tickers,
        "batches": [ordered_tickers[offset:offset + 10] for offset in range(0, len(ordered_tickers), 10)],
        "cohorts": {"base_fixed": base, "holdings_added": additions},
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    payload["sample_id"] = f"v1+holdings-{digest[:12]}"
    payload["sha256"] = digest
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / f"v1-{digest[:12]}.json"
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != encoded:
            raise ValueError("Sample hash collision; existing immutable sample was not changed.")
    else:
        replace_file(path, lambda temporary: Path(temporary).write_text(encoded, encoding="utf-8"))
    latest = {
        "sample_id": payload["sample_id"],
        "sha256": digest,
        "retrieved_at": retrieved_at,
        "priority_tickers": priority,
    }
    latest_path = root / "latest.json"
    latest_encoded = json.dumps(latest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    replace_file(latest_path, lambda temporary: Path(temporary).write_text(latest_encoded, encoding="utf-8"))
    return {**payload, "path": str(path)}


def held_tickers(holdings, *, country: str | None = None) -> tuple[list[str], list[str]]:
    """Return Yahoo symbols for supported holdings and safe unresolved ticker names."""
    from tradingagents.portfolio.analytics import map_market_symbol

    symbols, unresolved = set(), set()
    for item in holdings:
        if country and (item.market_country or "").upper() != country.upper():
            continue
        symbol = map_market_symbol(item.symbol, item.market_country, item.exchange)
        if symbol is None:
            unresolved.add(item.symbol)
        else:
            if (item.market_country or "").upper() == "US" and re.fullmatch(r"[A-Z0-9]+\.[A-Z]", symbol):
                symbol = symbol.replace(".", "-")
            symbols.add(symbol)
    return sorted(symbols), sorted(unresolved)


def latest_sample_id(root: Path | None = None) -> str | None:
    """Return the current sample pointer without exposing account data."""
    root = root or sample_directory()
    try:
        latest = json.loads((root / "latest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return latest.get("sample_id")


def load_current_sample(root: Path | None = None) -> dict:
    """Read the latest immutable manifest, or return the code-fixed universe."""
    root = root or sample_directory()
    current_id = latest_sample_id(root)
    if current_id:
        pointer = json.loads((root / "latest.json").read_text(encoding="utf-8"))
        path = root / f"v1-{pointer['sha256'][:12]}.json"
        sample = json.loads(path.read_text(encoding="utf-8"))
        if sample.get("sha256") != pointer.get("sha256") or sample.get("sample_id") != current_id:
            raise ValueError("Current chart-zone sample pointer does not match its immutable manifest.")
        return sample
    fixed_groups = {group: sorted(tickers) for group, tickers in FIXED_SAMPLE.items()}
    base = sorted({ticker for tickers in fixed_groups.values() for ticker in tickers})
    payload = {
        "base_version": "v1", "sample_id": "v1-fixed", "fixed_groups": fixed_groups,
        "base_tickers": base, "holdings_added": [], "priority_tickers": [],
        "ordered_tickers": base, "tickers": base,
        "cohorts": {"base_fixed": base, "holdings_added": []},
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    return payload


def load_backtest_sample(root: Path | None = None) -> dict:
    """Combine private cohorts while retaining separate 13F eligibility and identity."""
    root = root or sample_directory()
    sample = load_current_sample(root)
    from tradingagents.zone_13f import load_current_sec_sample

    current_sec = load_current_sec_sample(root)
    if current_sec is None:
        return sample
    pointer, sec = current_sec
    base_tickers = set(sample.get("tickers", []))
    sec_tickers = set(sec.get("tickers", []))
    additions = sorted(sec_tickers - base_tickers)
    overlap = sorted(sec_tickers & base_tickers)
    if not additions:
        sample["sec_13f_overlap_count"] = len(overlap)
        sample["sec_13f_sha256"] = sec["sha256"]
        sample["sec_13f_eligible_from"] = pointer["eligible_from"]
        sample["sec_13f_sample_id"] = sec["sample_id"]
        sample["sec_13f_quality"] = sec.get("quality", {})
        sample["sec_13f_bias_flags"] = sec.get("bias_flags", [])
        sample["sample_id"] = f"{sample['sample_id']}+sec13f-{sec['sha256'][:12]}"
        sample["sha256"] = hashlib.sha256(
            f"{sample.get('sha256')}:{sec['sha256']}".encode()
        ).hexdigest()
        sample.setdefault("cohorts", {})["sec_13f"] = []
        return sample
    sample["tickers"] = sorted(base_tickers | set(additions))
    sample["ordered_tickers"] = list(sample.get("ordered_tickers", sample.get("tickers", []))) + additions
    sample.setdefault("cohorts", {})["sec_13f"] = additions
    sample["sec_13f_overlap_count"] = len(overlap)
    sample["sec_13f_sha256"] = sec["sha256"]
    sample["sec_13f_sample_id"] = sec["sample_id"]
    sample["sec_13f_eligible_from"] = pointer["eligible_from"]
    sample["sec_13f_quality"] = sec.get("quality", {})
    sample["sec_13f_bias_flags"] = sec.get("bias_flags", [])
    sample["sample_id"] = f"{sample['sample_id']}+sec13f-{sec['sha256'][:12]}"
    sample["sha256"] = hashlib.sha256(
        f"{sample.get('sha256')}:{sec['sha256']}".encode()
    ).hexdigest()
    return sample
