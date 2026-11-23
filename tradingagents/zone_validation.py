"""Append-only zone evaluation records and effective validation state."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

from tradingagents.dataflows.files import replace_file

EVALUATION_STATUSES = {"passed", "failed", "inconclusive", "not_evaluated"}
ZONE_TYPES = ("support_resistance", "inside")


def append_evaluation(payload: dict, root: Path) -> dict:
    """Save an immutable evaluation record, addressed by its canonical content hash."""
    root.mkdir(parents=True, exist_ok=True)
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    record_id = hashlib.sha256(canonical.encode()).hexdigest()[:12]
    record = {**payload, "record_id": record_id}
    path = root / f"{record_id}.json"
    encoded = json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != encoded:
            raise ValueError("Evaluation record hash collision; existing record was not changed.")
    else:
        replace_file(path, lambda temporary: Path(temporary).write_text(encoded, encoding="utf-8"))
    return record


def load_evaluations(root: Path, zone_type: str) -> list[dict]:
    """Load immutable records projected onto one independently evaluated zone type."""
    if zone_type not in ZONE_TYPES:
        raise ValueError(f"Unsupported zone type: {zone_type}")
    records = []
    if not root.exists():
        return records
    for path in sorted(root.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        result = record.get("results", {}).get(zone_type)
        if result and result.get("status") in EVALUATION_STATUSES and record.get("evaluated_at"):
            records.append({**result, "record_id": record.get("record_id"),
                            "sample": record.get("sample"), "params_version": record.get("params_version"),
                            "baseline_version": record.get("baseline_version"),
                            "research_only": record.get("research_only", False),
                            "data_vintage": record.get("data_vintage"),
                            "evaluated_at": record["evaluated_at"],
                            "quarter_index": record.get("quarter_index")})
    return sorted(records, key=lambda row: (_time_key(row["evaluated_at"]), row.get("record_id", "")))


def _time_key(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def validation_state(
    records: list[dict], *, latest_sample: str | None,
    latest_quarter_index: int | None = None,
) -> dict:
    """Derive current status without allowing an older pass to replace a newer failure."""
    latest = records[-1] if records else None
    passed = next((record for record in reversed(records) if record["status"] == "passed"), None)
    pending = bool(latest_sample and (latest is None or latest.get("sample") != latest_sample))
    evaluated_quarter = latest.get("quarter_index") if latest else None
    stale = (
        latest_quarter_index is not None
        and evaluated_quarter is not None
        and latest_quarter_index - evaluated_quarter >= 2
    )
    status = latest["status"] if latest else "not_evaluated"
    effective = status
    if status == "passed" and (pending or stale):
        effective = "unverified"
    return {
        "status": status,
        "sample": latest.get("sample") if latest else None,
        "evaluated_at": latest.get("evaluated_at") if latest else None,
        "lift": latest.get("lift") if latest else None,
        "ci95": latest.get("ci95") if latest else None,
        "latest_evaluation": ({key: latest.get(key) for key in
                               ("record_id", "sample", "params_version", "baseline_version",
                                "evaluated_at", "status", "lift", "ci95", "research_only",
                                "data_vintage")} if latest else None),
        "last_passed_evaluation": ({"record_id": passed.get("record_id"), "sample": passed.get("sample"),
                                    "evaluated_at": passed.get("evaluated_at")} if passed else None),
        "effective_status": effective,
        "latest_sample": latest_sample,
        "pending": pending,
        "stale": stale,
    }


def current_validation(as_of: str, *, sample_root: Path | None = None,
                       evaluation_root: Path | None = None) -> dict:
    """Build the output contract used by chart-zones from the current local pointers."""
    from tradingagents.zone_samples import load_current_sample, sample_directory

    root = evaluation_root or (Path.home() / ".tradingagents" / "zone-backtest" / "evaluations")
    current_sample = load_current_sample(sample_root or sample_directory()).get("sample_id")
    year, month, _ = date.fromisoformat(as_of).timetuple()[:3]
    latest_quarter = year * 4 + (month - 1) // 3
    types = {
        zone_type: validation_state(load_evaluations(root, zone_type),
                                    latest_sample=current_sample,
                                    latest_quarter_index=latest_quarter)
        for zone_type in ZONE_TYPES
    }
    return {
        **types,
        "latest_sample": current_sample,
        "pending": any(value["pending"] for value in types.values()),
        "stale": any(value["stale"] for value in types.values()),
        "chart_validation": {"status": "not_evaluated"},
    }
