import json

import pytest
from typer.testing import CliRunner

from cli.main import app

DAY = "2026-11-20"
TICKER = "SYNTH"
TAB = "synthetic-tab"
DRAWING = {
    "type": "segment",
    "raw": {
        "d0": "20261118000000000", "v0": "100.000000000000000001",
        "d1": "20261120000000000", "v1": 110.5,
    },
}


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def write_read(path, drawings, *, ticker=TICKER, request_id="read"):
    value = {
        "id": request_id, "ok": True, "symbol": ticker,
        "data": {"symbol": ticker, "count": len(drawings), "drawings": drawings},
    }
    write_json(path, {
        "jsonrpc": "2.0",
        "result": {"isError": False, "content": [{"type": "text", "text": json.dumps(value)}]},
    })


@pytest.fixture
def evidence(tmp_path):
    directory = tmp_path / "artifacts"
    directory.mkdir()
    manifest = {
        "version": 1,
        "target": {"tab_id": TAB, "ticker": TICKER, "interval": "day", "as_of": DAY},
        "data_validation": {"source": "chart-zones", "path": "artifacts/chart_validation.json"},
        "reads": {},
        "items": [{
            "id": "trend",
            "action": "add",
            "type": "segment",
            "requested_at": f"{DAY}T19:00:01-05:00",
            "anchors": [
                {"date": DAY, "price": "110.500"},
                {"date": "2026-11-18", "price": "100.000000000000000001"},
            ],
            "reopened_screen": {"tab_id": TAB, "visible": True, "capture_path": "artifacts/reopened.png"},
        }],
    }
    for minute, phase in enumerate(("before", "after", "reopened"), start=1):
        manifest["reads"][phase] = {
            "tab_id": TAB, "interval": "day", "path": f"artifacts/{phase}.json",
            "observed_at": f"{DAY}T19:0{minute}:00-05:00",
        }
        write_read(directory / f"{phase}.json", [] if phase == "before" else [DRAWING], request_id=phase)
    write_json(directory / "chart_validation.json", {"status": "ok", "ticker": TICKER, "as_of": DAY})
    (directory / "reopened.png").write_bytes(b"synthetic screenshot attachment")
    return tmp_path / "drawings.json", manifest


def run_check(path, *, json_output=True):
    return CliRunner().invoke(app, [
        "chart-drawings-check", "--drawings", str(path), *(["--json"] if json_output else []),
    ])


@pytest.mark.parametrize(("action", "before"), [("add", []), ("reuse", [DRAWING])])
def test_complete_add_or_reuse_even_with_inconclusive_backtest(evidence, action, before):
    path, manifest = evidence
    manifest["items"][0]["action"] = action
    manifest["backtest"] = {"effective_status": "inconclusive"}
    write_read(path.parent / "artifacts/before.json", before)
    write_json(path, manifest)
    original = {file: file.read_bytes() for file in path.parent.rglob("*") if file.is_file()}

    result = run_check(path)
    assert result.exit_code == 0
    assert json.loads(result.output) == {"status": "complete", "issues": [], "items": [{
        "id": "trend", "index": 0, "status": "complete", "issues": [],
        "match_counts": {"before": len(before), "after": 1, "reopened": 1},
    }]}
    assert {file: file.read_bytes() for file in path.parent.rglob("*") if file.is_file()} == original


@pytest.mark.parametrize("case", [
    "coordinate", "duplicate", "already_exists", "not_reusable", "other_tab", "other_ticker",
    "wrong_interval", "after_missing", "lost_on_reopen", "screen_not_visible", "screen_other_tab",
    "missing_capture", "unreadable_raw", "reused_raw_path", "wrong_order", "request_too_late",
    "wrong_chart_date", "wrong_chart_ticker", "absolute_path", "unsupported_action",
])
def test_incomplete_evidence_reports_the_missing_or_conflicting_check(evidence, case):
    path, manifest = evidence
    item = manifest["items"][0]
    reads = manifest["reads"]
    artifacts = path.parent / "artifacts"
    if case == "coordinate":
        item["anchors"][1]["price"] = "100.000000000000000002"
        issue = "reads.after.expected_1_found_0"
    elif case == "duplicate":
        write_read(artifacts / "after.json", [DRAWING, DRAWING])
        issue = "reads.after.expected_1_found_2"
    elif case == "already_exists":
        write_read(artifacts / "before.json", [DRAWING])
        issue = "reads.before.expected_0_found_1"
    elif case == "not_reusable":
        item["action"] = "reuse"
        issue = "reads.before.expected_1_found_0"
    elif case == "other_tab":
        reads["reopened"]["tab_id"] = "a-second-tab-for-the-same-ticker"
        issue = "reads.reopened.target_mismatch"
    elif case == "other_ticker":
        write_read(artifacts / "reopened.json", [DRAWING], ticker="OTHER")
        issue = "reads.reopened.invalid_evidence"
    elif case == "wrong_interval":
        reads["before"]["interval"] = "week"
        issue = "reads.before.target_mismatch"
    elif case == "after_missing":
        write_read(artifacts / "after.json", [])
        issue = "reads.after.expected_1_found_0"
    elif case == "lost_on_reopen":
        write_read(artifacts / "reopened.json", [])
        issue = "reads.reopened.expected_1_found_0"
    elif case == "screen_not_visible":
        item["reopened_screen"]["visible"] = False
        issue = "reopened_screen.not_confirmed_on_target_tab"
    elif case == "screen_other_tab":
        item["reopened_screen"]["tab_id"] = "other"
        issue = "reopened_screen.not_confirmed_on_target_tab"
    elif case == "missing_capture":
        (artifacts / "reopened.png").unlink()
        issue = "reopened_screen.capture_missing"
    elif case == "unreadable_raw":
        (artifacts / "before.json").write_text("{")
        issue = "reads.before.invalid_evidence"
    elif case == "reused_raw_path":
        reads["reopened"]["path"] = reads["after"]["path"]
        issue = "reads.reopened.invalid_evidence"
    elif case == "wrong_order":
        reads["reopened"]["observed_at"] = reads["before"]["observed_at"]
        issue = "reads.out_of_order"
    elif case == "request_too_late":
        item["requested_at"] = reads["after"]["observed_at"]
        issue = "item.invalid_request"
    elif case == "wrong_chart_date":
        write_json(artifacts / "chart_validation.json", {"status": "ok", "ticker": TICKER, "as_of": "2026-11-19"})
        issue = "data_validation.target_mismatch"
    elif case == "wrong_chart_ticker":
        write_json(artifacts / "chart_validation.json", {"status": "ok", "ticker": "OTHER", "as_of": DAY})
        issue = "data_validation.target_mismatch"
    elif case == "absolute_path":
        reads["before"]["path"] = str(artifacts / "before.json")
        issue = "reads.before.invalid_evidence"
    else:
        item["action"] = "delete"
        issue = "item.invalid_request"
    write_json(path, manifest)

    result = run_check(path)
    assert result.exit_code == 1
    output = json.loads(result.output)
    assert output["items"][0]["status"] == output["status"] == "incomplete"
    assert issue in output["issues"] + output["items"][0]["issues"]


def test_missing_as_of_bar_in_tratto_csv_blocks_completion(evidence):
    path, manifest = evidence
    run_dir = path.parent / "artifacts"
    write_json(run_dir / "zones.json", {
        "ticker": TICKER, "as_of": DAY, "snapshot_sha256": "synthetic",
        "check_windows": {"recent": {"dates": ["2026-11-19", DAY], "count": 2}},
    })
    (run_dir / "snapshot.csv").write_text(
        "Date,Open,High,Low,Close,Volume\n2026-11-19,10,12,9,11,100\n2026-11-20,11,13,10,12,200\n"
    )
    csv = path.parent / "export.csv"
    csv.write_text("date,o,h,l,c,v\n2026-11-19,10,12,9,11,100\n")
    checked = CliRunner().invoke(app, [
        "chart-check", "--run-dir", str(run_dir), "--chart-csv", str(csv), "--json",
    ])
    assert checked.exit_code == 0
    assert json.loads(checked.output)["missing_dates"] == [DAY]
    write_json(path, manifest)

    result = run_check(path, json_output=False)
    assert result.exit_code == 1
    assert "data_validation.as_of_bar_missing" in result.output
    assert "trend: incomplete" in result.output


@pytest.mark.parametrize("case", [
    "complete", "style_mismatch", "duplicate_role_color", "old_remains", "label_mismatch",
    "minimum_not_met", "incorrect_visible_count", "summary_wrong_symbol",
])
def test_replace_style_roles_labels_and_view(evidence, case):
    path, manifest = evidence
    artifacts = path.parent / "artifacts"
    item = manifest["items"][0]
    old = {**DRAWING, "raw": {**DRAWING["raw"], "col": "#FFE066", "ptrn": "dashed", "lw": 3}}
    new = {**DRAWING, "raw": {**DRAWING["raw"], "col": "#F472D0", "ptrn": "solid", "lw": 3}}
    label = {"type": "callout", "raw": {
        "d0": "20261120000000000", "v0": 110.5, "col": "#FFE066", "bc": "#FFE066",
        "text": "%ED%9A%8C%EB%B3%B5%20%24110.50",
    }}
    item.update(
        action="replace", role="long_uptrend", previous={
            "anchors": item["anchors"], "style": {"color": "#FFE066", "pattern": "dashed"},
        },
        style={"color": "#f472d0", "pattern": "solid", "line_width": 3},
    )
    manifest["role_colors"] = {"long_uptrend": "#F472D0", "recovery": "#FFE066"}
    manifest["items"].append({
        **item, "id": "label", "type": "callout", "action": "add", "role": "recovery",
        "anchors": [item["anchors"][0]],
        "style": {"text": "회복 $110.50", "color": "#FFE066", "border_color": "#FFE066"},
    })
    manifest["reopened_view"] = {
        "tab_id": TAB, "chart_timezone": "Asia/Seoul", "summary_path": "artifacts/summary.json",
        "first_date": "2026-11-18", "last_date": DAY, "visible_bars": 3, "minimum_bars": 3,
    }
    summary = {
        "ok": True, "data": {"symbol": TICKER, "interval": "day", "total_bars_loaded": 100,
                             "loaded_range": {"start": "2026-11-16T15:00:00Z", "end": "2026-11-19T15:00:00Z"}},
    }
    write_read(artifacts / "before.json", [old])
    write_read(artifacts / "after.json", [new, label])
    reopened = [new, label]
    issue = None
    if case == "style_mismatch":
        reopened[0] = {**new, "raw": {**new["raw"], "ptrn": "dotted"}}
        issue = "reads.reopened.style_mismatch"
    elif case == "duplicate_role_color":
        manifest["role_colors"]["support"] = "#ffe066"
        issue = "role_colors.invalid_or_repeated"
    elif case == "old_remains":
        reopened.append(old)
        issue = "reads.reopened.replacement_expected_0_old_found_1"
    elif case == "label_mismatch":
        reopened[1] = {**label, "raw": {**label["raw"], "text": "wrong"}}
        issue = "reads.reopened.style_mismatch"
    elif case == "minimum_not_met":
        manifest["reopened_view"]["minimum_bars"] = 2500
        issue = "reopened_view.minimum_bars_not_met"
    elif case == "incorrect_visible_count":
        manifest["reopened_view"]["visible_bars"] = 100
        issue = "reopened_view.visible_count_mismatch"
    elif case == "summary_wrong_symbol":
        summary["data"]["symbol"] = "OTHER"
        issue = "reopened_view.target_mismatch"
    write_read(artifacts / "reopened.json", reopened)
    write_json(artifacts / "summary.json", summary)
    write_json(path, manifest)

    result = run_check(path)
    response = json.loads(result.output)
    if issue:
        assert result.exit_code == 1
        assert issue in response["issues"] + [v for entry in response["items"] for v in entry["issues"]]
    else:
        assert result.exit_code == 0
        assert response["items"][0]["match_counts"] == {"before": 1, "after": 1, "reopened": 1}


def test_remove_requires_absence_on_reopen(evidence):
    path, manifest = evidence
    artifacts = path.parent / "artifacts"
    item = manifest["items"][0]
    item["action"] = "remove"
    item["reopened_screen"]["visible"] = False
    write_read(artifacts / "before.json", [DRAWING])
    for stage in ("after", "reopened"):
        write_read(artifacts / f"{stage}.json", [])
    write_json(path, manifest)
    assert run_check(path).exit_code == 0

    write_read(artifacts / "reopened.json", [DRAWING])
    result = run_check(path)
    assert result.exit_code == 1
    assert "reads.reopened.expected_0_found_1" in result.output


@pytest.mark.parametrize(("kind", "length"), [("rectangle", 2), ("horizontal", 1)])
def test_price_zone_kinds_and_exact_json_decimal_anchors(evidence, kind, length):
    path, manifest = evidence
    item = manifest["items"][0]
    item["type"] = kind
    item["anchors"] = item["anchors"][::-1][:length]
    write_json(path, manifest)
    # Tratto returns prices as JSON numbers. Keep the original decimal token here.
    drawing = json.dumps({"type": kind, "raw": DRAWING["raw"]}).replace(
        '"100.000000000000000001"', "100.000000000000000001"
    )
    for phase in ("after", "reopened"):
        evidence_file = path.parent / f"artifacts/{phase}.json"
        evidence_file.write_text(
            f'{{"ok":true,"data":{{"symbol":"{TICKER}","count":1,"drawings":[{drawing}]}}}}'
        )
    assert run_check(path).exit_code == 0


@pytest.mark.parametrize(("sessions", "ohlcv", "exit_code"), [
    ("passed", "passed", 0), ("failed", "passed", 1), ("passed", "failed", 1),
])
def test_five_year_evidence_requires_both_checks(evidence, sessions, ohlcv, exit_code):
    path, manifest = evidence
    manifest["data_validation"]["source"] = "five-year-ohlcv"
    write_json(path.parent / "artifacts/chart_validation.json", {
        "ticker": TICKER, "as_of": DAY, "sessions": sessions, "ohlcv": ohlcv,
    })
    write_json(path, manifest)
    result = run_check(path)
    assert result.exit_code == exit_code
    if exit_code:
        assert json.loads(result.output)["issues"] == ["data_validation.ohlcv_not_passed"]


@pytest.mark.parametrize(("contents", "code", "issue"), [
    (None, 2, "manifest.unreadable"),
    ("{", 2, "manifest.unreadable"),
    ("[]", 2, "manifest.unreadable"),
    ('{"version": NaN}', 2, "manifest.unreadable"),
    ('{"status":"partial","symbols":{"SYNTH":{}}}', 1, "manifest.version_missing_or_unsupported"),
])
def test_unreadable_and_legacy_files(tmp_path, contents, code, issue):
    path = tmp_path / "drawings.json"
    if contents is not None:
        path.write_text(contents)
    result = run_check(path)
    assert result.exit_code == code
    assert json.loads(result.output)["issues"] == [issue]
    assert path.read_text() == contents if contents is not None else not path.exists()
