from tradingagents.zone_validation import append_evaluation, load_evaluations, validation_state


def _record(status, evaluated_at, sample="sample-a", quarter_index=2026 * 4 + 2):
    return {
        "sample": sample,
        "params_version": "v1",
        "baseline_version": "matched-v1",
        "evaluated_at": evaluated_at,
        "quarter_index": quarter_index,
        "results": {
            "support_resistance": {"status": status, "lift": 0.02, "ci95": [0.01, 0.03]},
            "inside": {"status": status, "lift": 0.01, "ci95": [-0.01, 0.03]},
        },
    }


def test_latest_failed_evaluation_is_effective_and_retains_previous_pass(tmp_path):
    append_evaluation(_record("passed", "2026-08-01T00:00:00Z"), tmp_path)
    append_evaluation(_record("failed", "2026-11-01T00:00:00Z"), tmp_path)
    records = load_evaluations(tmp_path, "support_resistance")

    state = validation_state(records, latest_sample="sample-a", latest_quarter_index=2026 * 4 + 2)

    assert state["status"] == "failed"
    assert state["effective_status"] == "failed"
    assert state["last_passed_evaluation"]["sample"] == "sample-a"
    assert state["latest_evaluation"]["status"] == "failed"
    assert state["pending"] is False


def test_latest_nonpassing_statuses_never_inherit_older_pass(tmp_path):
    append_evaluation(_record("passed", "2026-08-01T00:00:00Z"), tmp_path)
    for status in ("failed", "inconclusive", "not_evaluated"):
        append_evaluation(_record(status, f"2026-11-{len(status):02d}T00:00:00Z"), tmp_path)
        state = validation_state(load_evaluations(tmp_path, "inside"), latest_sample="sample-a",
                                 latest_quarter_index=2026 * 4 + 2)
        assert state["status"] == status
        assert state["effective_status"] == status
        assert state["last_passed_evaluation"]["sample"] == "sample-a"


def test_new_sample_is_pending_without_replacing_latest_status(tmp_path):
    append_evaluation(_record("passed", "2026-08-01T00:00:00Z"), tmp_path)
    record = append_evaluation(_record("inconclusive", "2026-11-01T00:00:00Z"), tmp_path)
    records = load_evaluations(tmp_path, "inside")

    state = validation_state(records, latest_sample="sample-b", latest_quarter_index=2026 * 4 + 2)

    assert state["latest_evaluation"]["record_id"] == record["record_id"]
    assert state["status"] == "inconclusive"
    assert state["effective_status"] == "inconclusive"
    assert state["pending"] is True
    assert state["last_passed_evaluation"]["sample"] == "sample-a"


def test_two_quarter_old_pass_is_stale_and_not_effective(tmp_path):
    append_evaluation(_record("passed", "2026-01-01T00:00:00Z", quarter_index=2026 * 4), tmp_path)
    records = load_evaluations(tmp_path, "support_resistance")

    state = validation_state(records, latest_sample="sample-a", latest_quarter_index=2026 * 4 + 2)

    assert state["status"] == "passed"
    assert state["stale"] is True
    assert state["effective_status"] == "unverified"


def test_no_evaluation_with_latest_sample_is_not_evaluated_and_pending():
    state = validation_state([], latest_sample="sample-a", latest_quarter_index=2026 * 4 + 2)

    assert state["status"] == "not_evaluated"
    assert state["effective_status"] == "not_evaluated"
    assert state["pending"] is True
