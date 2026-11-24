"""Verify recorded Tratto drawing evidence without opening or changing a chart."""

import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import unquote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ANCHOR_COUNTS = {"rectangle": 2, "segment": 2, "horizontal": 1, "callout": 1, "annotation": 1}
READ_PHASES = ("before", "after", "reopened")
STYLE_FIELDS = {"color": "col", "pattern": "ptrn", "line_width": "lw", "text": "text",
                "border_color": "bc", "background_color": "bg"}


def _reject_json_constant(value):
    raise ValueError(f"invalid JSON constant: {value}")


def _read_object(path: Path) -> dict:
    if not path.is_file():
        raise ValueError("expected a file")
    value = json.loads(
        path.read_text(encoding="utf-8"), parse_float=Decimal, parse_constant=_reject_json_constant
    )
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value


_READ_ERRORS = (OSError, ValueError, InvalidOperation, RecursionError)


def _object(value) -> dict:
    return value if isinstance(value, dict) else {}


def _attachment(directory: Path, value) -> Path:
    if not isinstance(value, str) or not value.strip() or Path(value).is_absolute():
        raise ValueError("expected a relative attachment path")
    return (directory / value).resolve()


def _date(value) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("expected an ISO trading date")
    return date.fromisoformat(value)


def _timestamp(value) -> datetime:
    moment = datetime.fromisoformat(value) if isinstance(value, str) else None
    if moment is None or moment.utcoffset() is None:
        raise ValueError("expected a timestamp with a UTC offset")
    return moment


def _coordinate(day, price) -> tuple[date, Decimal]:
    if type(price) not in (str, int, Decimal):
        raise ValueError("expected a decimal price")
    value = Decimal(price)
    if not value.is_finite() or value <= 0:
        raise ValueError("expected a finite positive price")
    return _date(day), value


def _requested_anchors(item: dict, count: int) -> tuple:
    anchors = item.get("anchors")
    if not isinstance(anchors, list) or len(anchors) != count:
        raise ValueError("wrong number of anchors")
    return tuple(sorted(_coordinate(_object(p).get("date"), _object(p).get("price")) for p in anchors))


def _observed_anchors(drawing: dict, count: int) -> tuple:
    raw = _object(drawing.get("raw"))
    anchors = []
    for i in range(count):
        stamp = raw.get(f"d{i}")
        if not isinstance(stamp, str) or not re.fullmatch(r"[0-9]{17}", stamp):
            raise ValueError("invalid ChartIQ anchor date")
        anchors.append(_coordinate(f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}", raw.get(f"v{i}")))
    return tuple(sorted(anchors))


def _verify_data(directory: Path, validation: dict, target: dict) -> str | None:
    try:
        record = _read_object(_attachment(directory, validation.get("path")))
    except _READ_ERRORS:
        return "data_validation.unreadable"
    source = validation.get("source")
    if source == "chart-zones":
        missing_dates = record.get("missing_dates")
        if isinstance(missing_dates, list) and target.get("as_of") in missing_dates:
            return "data_validation.as_of_bar_missing"
        if record.get("status") != "ok" or record.get("missing_dates"):
            return "data_validation.chart_check_not_ok"
    elif source in {"five-year-ohlcv", "daily-ohlcv"}:
        if record.get("sessions") != "passed" or record.get("ohlcv") != "passed":
            return "data_validation.ohlcv_not_passed"
    else:
        return "data_validation.unsupported_source"
    if any(record.get(k) != target.get(k) for k in ("ticker", "as_of")):
        return "data_validation.target_mismatch"
    return None


def _read_tratto(path: Path) -> dict:
    payload = _read_object(path)
    if "result" in payload:
        result = _object(payload["result"])
        content = result.get("content")
        if result.get("isError") or not isinstance(content, list) or len(content) != 1:
            raise ValueError("invalid Tratto response")
        block = _object(content[0])
        if block.get("type") != "text" or not isinstance(block.get("text"), str):
            raise ValueError("missing Tratto response text")
        payload = _object(json.loads(
            block["text"], parse_float=Decimal, parse_constant=_reject_json_constant
        ))
    return payload


def _read_drawings(path: Path, ticker: str) -> list:
    payload = _read_tratto(path)
    data = _object(payload.get("data"))
    if payload.get("ok") is not True or data.get("symbol") != ticker or payload.get("symbol", ticker) != ticker:
        raise ValueError("failed response or different ticker")
    drawings = data.get("drawings")
    if (
        not isinstance(drawings, list)
        or type(data.get("count")) is not int
        or data["count"] != len(drawings)
        or any(not isinstance(_object(obj).get("type"), str) for obj in drawings)
    ):
        raise ValueError("invalid drawing list")
    return drawings


def _verify_view(directory: Path, view, target: dict) -> str | None:
    from datetime import timedelta

    import exchange_calendars as xcals

    from tradingagents.dataflows.chart_check import _date as chart_date

    view = _object(view)
    if not target.get("tab_id") or view.get("tab_id") != target["tab_id"]:
        return "reopened_view.target_mismatch"
    try:
        ticker = target.get("ticker")
        payload = _read_tratto(_attachment(directory, view.get("summary_path")))
        data = _object(payload.get("data"))
        if (payload.get("ok") is not True or payload.get("symbol", ticker) != ticker
                or data.get("symbol") != ticker or data.get("interval") != "day"):
            return "reopened_view.target_mismatch"
        tz = ZoneInfo(view["chart_timezone"])
        loaded = _object(data.get("loaded_range"))
        loaded_start, loaded_end = (_date(chart_date(loaded[k], tz)) for k in ("start", "end"))
        first, last = (_date(view.get(k)) for k in ("first_date", "last_date"))
        count, minimum, total = view.get("visible_bars"), view.get("minimum_bars"), data.get("total_bars_loaded")
        if not all(type(x) is int and x > 0 for x in (count, minimum, total)):
            return "reopened_view.invalid_counts"
        if not loaded_start <= first <= last <= loaded_end or count > total:
            return "reopened_view.outside_loaded_range"
        cal = xcals.get_calendar("XNYS", start=first - timedelta(days=15), end=last + timedelta(days=15))
        if not cal.is_session(first) or not cal.is_session(last) or len(cal.sessions_in_range(first, last)) != count:
            return "reopened_view.visible_count_mismatch"
        if count < minimum:
            return "reopened_view.minimum_bars_not_met"
    except (*_READ_ERRORS, KeyError, TypeError, ZoneInfoNotFoundError, OverflowError):
        return "reopened_view.invalid_evidence"
    return None


def _role_palette(value) -> dict:
    if not isinstance(value, dict) or not all(
        isinstance(role, str) and role.strip() and isinstance(color, str)
        and re.fullmatch(r"#[0-9a-fA-F]{6}", color) for role, color in value.items()
    ):
        raise ValueError("Expected role names mapped to RGB hex colors.")
    result = {role: color.lower() for role, color in value.items()}
    if len(set(result.values())) != len(result):
        raise ValueError("Different roles must use different colors.")
    return result


def verify_drawings(path: Path) -> tuple[dict, int]:
    try:
        manifest = _read_object(path)
    except _READ_ERRORS:
        return {"status": "input_error", "issues": ["manifest.unreadable"], "items": []}, 2
    if type(manifest.get("version")) is not int or manifest["version"] != 1:
        return {"status": "incomplete", "issues": ["manifest.version_missing_or_unsupported"], "items": []}, 1

    issues = []
    target = _object(manifest.get("target"))
    ticker, tab_id = target.get("ticker"), target.get("tab_id")
    try:
        _date(target.get("as_of"))
        if not all(isinstance(v, str) and v.strip() for v in (ticker, tab_id)) or target.get("interval") != "day":
            raise ValueError("invalid tab, ticker or interval")
    except ValueError:
        issues.append("target.invalid")
    data_issue = _verify_data(path.parent, _object(manifest.get("data_validation")), target)
    if data_issue:
        issues.append(data_issue)
    if "reopened_view" in manifest:
        view_issue = _verify_view(path.parent, manifest["reopened_view"], target)
        if view_issue:
            issues.append(view_issue)
    try:
        palette = _role_palette(manifest.get("role_colors", {}))
    except ValueError:
        issues.append("role_colors.invalid_or_repeated")
        palette = {}

    observed = {}
    timestamps = {}
    used_paths = set()
    reads = _object(manifest.get("reads"))
    for phase in READ_PHASES:
        read = _object(reads.get(phase))
        if tab_id is None or read.get("tab_id") != tab_id or read.get("interval") != "day":
            issues.append(f"reads.{phase}.target_mismatch")
            continue
        try:
            raw_path = _attachment(path.parent, read.get("path"))
            if raw_path in used_paths:
                raise ValueError("read attachment already used")
            timestamps[phase] = _timestamp(read.get("observed_at"))
            observed[phase] = _read_drawings(raw_path, ticker)
            used_paths.add(raw_path)
        except _READ_ERRORS:
            issues.append(f"reads.{phase}.invalid_evidence")
    if len(observed) == len(READ_PHASES) and not timestamps["before"] < timestamps["after"] < timestamps["reopened"]:
        issues.append("reads.out_of_order")

    items = manifest.get("items")
    if not isinstance(items, list) or not items:
        issues.append("items.missing")
        items = []
    results = []
    item_ids = set()
    for index, value in enumerate(items):
        item = _object(value)
        item_id = item.get("id")
        item_issues = []
        if not isinstance(item_id, str) or not item_id.strip() or item_id in item_ids:
            item_issues.append("item.invalid_or_duplicate_id")
            item_id = None
        else:
            item_ids.add(item_id)
        counts = _verify_item(item, observed, timestamps, item_issues, palette)
        screen = _object(item.get("reopened_screen"))
        if screen.get("tab_id") != tab_id or screen.get("visible") is not (item.get("action") != "remove"):
            item_issues.append("reopened_screen.not_confirmed_on_target_tab")
        try:
            capture = _attachment(path.parent, screen.get("capture_path"))
            if not capture.is_file() or not capture.stat().st_size:
                raise ValueError("missing or empty capture")
        except _READ_ERRORS:
            item_issues.append("reopened_screen.capture_missing")
        results.append({
            "id": item_id, "index": index, "status": "incomplete" if issues or item_issues else "complete",
            "match_counts": counts, "issues": item_issues,
        })

    complete = not issues and all(item["status"] == "complete" for item in results)
    return {"status": "complete" if complete else "incomplete", "issues": issues, "items": results}, 0 if complete else 1


def _style(value) -> dict:
    if not isinstance(value, dict) or value.keys() - STYLE_FIELDS.keys():
        raise ValueError("Unknown style field.")
    for key, field in value.items():
        if key == "line_width":
            if type(field) not in (int, Decimal) or not Decimal(field).is_finite() or field <= 0:
                raise ValueError("Expected a positive line width.")
        elif not isinstance(field, str) or not field.strip():
            raise ValueError("Expected a nonempty style value.")
    return value


def _matches_style(drawing: dict, style: dict) -> bool:
    raw = _object(drawing.get("raw"))
    for key, expected in style.items():
        actual = raw.get(STYLE_FIELDS[key])
        if key == "text" and isinstance(actual, str):
            actual = unquote(actual)
        if key in {"color", "border_color", "background_color"} and isinstance(actual, str):
            actual, expected = actual.lower(), expected.lower()
        if actual != expected:
            return False
    return True


def _verify_item(item: dict, observed: dict, timestamps: dict, issues: list, palette: dict) -> dict:
    kind, action = item.get("type"), item.get("action")
    counts = {}
    try:
        if not isinstance(kind, str) or kind not in ANCHOR_COUNTS or action not in ("add", "reuse", "replace", "remove"):
            raise ValueError("unsupported drawing type or action")
        count = ANCHOR_COUNTS[kind]
        expected = _requested_anchors(item, count)
        style = _style(item.get("style", {}))
        previous = None
        previous_style = {}
        if action == "replace":
            old = _object(item.get("previous"))
            previous = _requested_anchors(old, count)
            previous_style = _style(old.get("style", {}))
            if previous == expected and not any(k in style and v != style[k] for k, v in previous_style.items()):
                raise ValueError("Same-coordinate replacement needs differing old and new styles.")
        if "role" in item:
            role = item["role"]
            color = style.get("color", "").lower()
            if (not isinstance(role, str) or palette.get(role) != color
                    or (kind == "callout" and style.get("border_color", "").lower() != color)):
                issues.append("item.role_color_mismatch")
        requested_at = _timestamp(item.get("requested_at"))
        if "before" in timestamps and requested_at > timestamps["before"]:
            raise ValueError("request must be recorded by the pre-change read")
    except (ValueError, InvalidOperation):
        issues.append("item.invalid_request")
        return counts

    for phase, drawings in observed.items():
        try:
            by_anchor = [(drawing, _observed_anchors(drawing, count))
                         for drawing in drawings if drawing["type"] == kind]
        except (ValueError, InvalidOperation):
            issues.append(f"reads.{phase}.invalid_coordinates")
            continue
        matches = [drawing for drawing, anchors in by_anchor if anchors == expected]
        counts[phase] = len(matches)
        if previous is not None:
            old_matches = [drawing for drawing, anchors in by_anchor if anchors == previous]
            old_count = sum(_matches_style(drawing, previous_style) for drawing in old_matches)
            old_required = int(phase == "before")
            if old_count != old_required:
                issues.append(f"reads.{phase}.replacement_expected_{old_required}_old_found_{old_count}")
            if previous != expected and len(old_matches) != old_required and old_count == old_required:
                issues.append(f"reads.{phase}.replacement_old_coordinate_count_mismatch")
        required = (int(action in {"reuse", "remove"} or previous == expected)
                    if phase == "before" else int(action != "remove"))
        if counts[phase] != required:
            issues.append(f"reads.{phase}.expected_{required}_found_{counts[phase]}")
        elif required and (phase != "before" or action == "remove") and not _matches_style(matches[0], style):
            issues.append(f"reads.{phase}.style_mismatch")
    return counts
