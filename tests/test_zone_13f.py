import csv
import io
import json
import zipfile

from typer.testing import CliRunner

from cli.main import app
from tradingagents.zone_13f import (
    _latest_dataset_url,
    _map_batch,
    _mapping_payload,
    _write_sample,
    load_current_sec_sample,
    map_cusips,
    parse_13f_dataset,
)
from tradingagents.zone_samples import FIXED_SAMPLE, load_backtest_sample, write_sample


def _zip_dataset(path, submissions, coverpages, infotable):
    tables = {
        "SUBMISSION.tsv": ("ACCESSION_NUMBER", "FILING_DATE", "SUBMISSIONTYPE", "CIK", "PERIODOFREPORT"),
        "COVERPAGE.tsv": ("ACCESSION_NUMBER", "ISAMENDMENT", "AMENDMENTTYPE", "REPORTTYPE"),
        "INFOTABLE.tsv": ("ACCESSION_NUMBER", "INFOTABLE_SK", "CUSIP", "VALUE", "SSHPRNAMT",
                           "SSHPRNAMTTYPE", "PUTCALL", "TITLEOFCLASS", "NAMEOFISSUER"),
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, headers in tables.items():
            rows = {"SUBMISSION.tsv": submissions, "COVERPAGE.tsv": coverpages,
                    "INFOTABLE.tsv": infotable}[name]
            text = io.StringIO(newline="")
            writer = csv.DictWriter(text, fieldnames=headers, delimiter="\t", lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            archive.writestr(name, text.getvalue())


def _filing(accession, form, filing_date, cik="0000000001", period="30-JUN-2026"):
    return {"ACCESSION_NUMBER": accession, "FILING_DATE": filing_date,
            "SUBMISSIONTYPE": form, "CIK": cik, "PERIODOFREPORT": period}


def _position(accession, cusip, value, *, share_type="SH", put_call="", seq="1"):
    return {"ACCESSION_NUMBER": accession, "INFOTABLE_SK": seq, "CUSIP": cusip,
            "VALUE": str(value), "SSHPRNAMT": "100", "SSHPRNAMTTYPE": share_type,
            "PUTCALL": put_call, "TITLEOFCLASS": "COM", "NAMEOFISSUER": "Synthetic Issuer"}


def test_sec_dataset_uses_latest_period_and_applies_restatement_and_addition(tmp_path):
    path = tmp_path / "synthetic.zip"
    submissions = [
        _filing("BASE", "13F-HR", "14-AUG-2026"),
        _filing("REST", "13F-HR/A", "16-AUG-2026"),
        _filing("ADD", "13F-HR/A", "17-AUG-2026"),
        _filing("LATE", "13F-HR", "10-SEP-2026", cik="0000000002"),
        _filing("OLD", "13F-HR", "15-MAY-2026", period="31-MAR-2026"),
        _filing("NOTICE", "13F-NT", "14-AUG-2026", cik="0000000003"),
    ]
    coverpages = [
        {"ACCESSION_NUMBER": "BASE", "AMENDMENTTYPE": ""},
        {"ACCESSION_NUMBER": "REST", "AMENDMENTTYPE": "RESTATEMENT"},
        {"ACCESSION_NUMBER": "ADD", "AMENDMENTTYPE": "NEW HOLDINGS ENTRIES"},
        {"ACCESSION_NUMBER": "LATE", "AMENDMENTTYPE": ""},
        {"ACCESSION_NUMBER": "OLD", "AMENDMENTTYPE": ""},
    ]
    infotable = [
        _position("BASE", "SYNTH0001", 900),
        _position("BASE", "SYNTH0002", 100),
        _position("REST", "SYNTH0001", 300),
        _position("REST", "SYNTH0003", 200),
        _position("ADD", "SYNTH0004", 50),
        _position("LATE", "SYNTH0003", 400),
        _position("LATE", "SYNTH0005", 10, share_type="PRN"),
        _position("LATE", "SYNTH0006", 20, put_call="PUT"),
        _position("OLD", "SYNTH0007", 999),
    ]
    _zip_dataset(path, submissions, coverpages, infotable)

    result = parse_13f_dataset(path)
    candidates = {item["cusip"]: item for item in result["candidates"]}

    assert result["report_period"] == "2026-06-30"
    assert candidates["SYNTH0001"]["value_thousands"] == 300
    assert "SYNTH0002" not in candidates
    assert candidates["SYNTH0003"]["value_thousands"] == 600
    assert candidates["SYNTH0004"]["value_thousands"] == 50
    assert "SYNTH0007" not in candidates
    assert result["excluded_rows"]["principal_amount"] == 1
    assert result["excluded_rows"]["options"] == 1


def test_unknown_amendment_type_excludes_filer_and_keeps_other_filings(tmp_path):
    path = tmp_path / "synthetic.zip"
    submissions = [_filing("BASE", "13F-HR", "14-AUG-2026"),
                   _filing("AMEND", "13F-HR/A", "16-AUG-2026"),
                   _filing("OTHER", "13F-HR", "14-AUG-2026", cik="0000000002")]
    coverpages = [{"ACCESSION_NUMBER": "BASE", "AMENDMENTTYPE": ""},
                  {"ACCESSION_NUMBER": "AMEND", "AMENDMENTTYPE": "UNKNOWN"},
                  {"ACCESSION_NUMBER": "OTHER", "AMENDMENTTYPE": ""}]
    infotable = [_position("BASE", "SYNTH0001", 900), _position("AMEND", "SYNTH0002", 200),
                 _position("OTHER", "SYNTH0003", 100)]
    _zip_dataset(path, submissions, coverpages, infotable)

    result = parse_13f_dataset(path)

    assert result["ambiguous_filer_count"] == 1
    assert [row["cusip"] for row in result["candidates"]] == ["SYNTH0003"]


def test_mapping_api_classifies_ambiguous_unmapped_and_non_common_stock(monkeypatch):
    class Response:
        status_code = 200
        headers = {"Content-Type": "application/json; charset=utf-8"}

        @staticmethod
        def json():
            return [
                {"data": [{"ticker": "SYN", "figi": "FIGI1", "marketSector": "Equity",
                           "securityType": "Common Stock"}]},
                {"data": [{"ticker": "SYN", "figi": "FIGI2"}, {"ticker": "SYN", "figi": "FIGI3"}]},
                {"error": "Not found"},
                {"data": [{"ticker": "FUND", "figi": "FIGI4", "marketSector": "Equity",
                           "securityType": "ETF"}]},
            ]

    calls = []
    monkeypatch.setattr("tradingagents.zone_13f.requests.post", lambda *args, **kwargs: calls.append((args, kwargs)) or Response())

    result = _map_batch(["SYNTH0001", "SYNTH0002", "SYNTH0003", "SYNTH0004"])

    assert [item["status"] for item in result] == ["mapped", "ambiguous", "unmapped", "ambiguous_security_type"]
    assert result[0] == {"status": "mapped", "ticker": "SYN", "figi": "FIGI1"}
    assert calls[0][1]["json"][0]["exchCode"] == "US"
    assert "X-OPENFIGI-APIKEY" not in calls[0][1]["headers"]


def test_mapping_batches_at_ten_jobs_and_respects_free_api_pacing(monkeypatch):
    batches = []
    delays = []

    def fake_batch(cusips):
        batches.append(cusips)
        return [{"status": "unmapped"} for _ in cusips]

    monkeypatch.setattr("tradingagents.zone_13f._map_batch", fake_batch)

    result = map_cusips([f"SYNTH{i:04d}" for i in range(21)], sleep=delays.append)

    assert [len(batch) for batch in batches] == [10, 10, 1]
    assert delays == [2.5, 2.5]
    assert len(result) == 21


def test_latest_dataset_url_selects_newest_quarterly_zip():
    page = """
      <a href="/files/datastandardsinnovation/data/form-13f-data-sets/01mar2026-31may2026_form13f.zip">older</a>
      <a href="/files/datastandardsinnovation/data/form-13f-data-sets/01jun2026-31aug2026_form13f.zip">latest</a>
    """

    assert _latest_dataset_url(page).endswith("01jun2026-31aug2026_form13f.zip")


def test_sample_mapping_is_stable_private_and_ties_sort_by_ticker(tmp_path):
    candidates = [{"cusip": f"SYNTH{i:04d}", "value_thousands": 100, "reporting_filers": 2}
                 for i in range(11)]
    parsed = {"candidates": candidates, "report_period": "2026-06-30", "filer_count": 3,
              "ambiguous_filer_count": 0, "total_candidate_cusips": 11,
              "excluded_rows": {"options": 0, "principal_amount": 0, "invalid_cusip": 0, "invalid_value": 0}}
    mapping = [{"status": "mapped", "ticker": f"SYN{i:02d}", "figi": f"FIGI{i:02d}"}
               for i in reversed(range(11))]
    payload = _mapping_payload(parsed, mapping, "a" * 64)

    assert payload["tickers"] == [f"SYN{i:02d}" for i in range(10)]
    assert "cusip_mapping_observed_at_not_historical" in payload["bias_flags"]
    assert payload["quality"]["candidate_truncated_count"] == 0
    assert payload["ticker_metrics"][0]["reported_value_usd"] == 100_000
    encoded = json.dumps(payload, sort_keys=True)
    assert all(item["cusip"] not in encoded for item in candidates)
    assert all(len(item["cusip_sha256"]) == 64 for item in payload["mapping_audit"])

    first = _write_sample(payload, root=tmp_path, dataset_observed_at="2026-11-18T07:00:00+00:00",
                          mapping_observed_at="2026-11-18T07:01:00+00:00",
                          retrieved_at="2026-11-18T07:02:00+00:00")
    original = (tmp_path / f"{first['sample_id']}.json").read_bytes()
    again = _write_sample(payload, root=tmp_path, dataset_observed_at="2026-12-01T07:00:00+00:00",
                          mapping_observed_at="2026-12-01T07:01:00+00:00",
                          retrieved_at="2026-12-01T07:02:00+00:00")
    pointer, manifest = load_current_sec_sample(tmp_path)

    assert again["sample_id"] == first["sample_id"]
    assert (tmp_path / f"{first['sample_id']}.json").read_bytes() == original
    assert pointer["retrieved_at"] == "2026-12-01T07:02:00+00:00"
    assert pointer["eligible_from"] == first["eligible_from"]
    assert manifest["sha256"] == first["sha256"]
    assert "SYNTH0000" not in (tmp_path / f"{first['sample_id']}.json").read_text()


def test_eligibility_uses_latest_observation_and_next_xnys_session(tmp_path):
    manifest = {"schema_version": 1, "cohort_id": "sec_13f", "dataset_sha256": "a" * 64,
                "mapping_result_sha256": "b" * 64, "report_period": "2026-06-30",
                "tickers": [], "ticker_metrics": [], "mapping_audit": [],
                "quality": {"status": "inconclusive"}}

    result = _write_sample(manifest, root=tmp_path,
                           dataset_observed_at="2026-11-20T20:00:00+00:00",
                           mapping_observed_at="2026-11-22T18:00:00+00:00",
                           retrieved_at="2026-11-22T18:01:00+00:00")

    assert result["eligible_from"] == "2026-11-23"


def test_backtest_combines_13f_as_distinct_cohort_and_keeps_eligibility(tmp_path):
    base = write_sample(holdings=["AAPL"], priority_tickers=["AAPL"],
                        retrieved_at="2026-11-18T07:00:00+00:00", root=tmp_path)
    payload = {"schema_version": 1, "cohort_id": "sec_13f", "mapping_version": "v1",
               "dataset_sha256": "a" * 64, "mapping_result_sha256": "b" * 64,
               "report_period": "2026-06-30", "selection_policy": "synthetic",
               "tickers": ["QQQ", "SYN"], "ticker_metrics": [], "mapping_audit": [],
               "bias_flags": ["cusip_mapping_observed_at_not_historical"],
               "quality": {"status": "inconclusive"}}
    sec = _write_sample(payload, root=tmp_path, dataset_observed_at="2026-11-18T07:00:00+00:00",
                        mapping_observed_at="2026-11-18T07:01:00+00:00",
                        retrieved_at="2026-11-18T07:02:00+00:00")

    combined = load_backtest_sample(tmp_path)

    assert len(FIXED_SAMPLE["m7"]) == 7
    assert "SYN" in combined["tickers"]
    assert "QQQ" in combined["tickers"]
    assert combined["cohorts"]["sec_13f"] == ["SYN"]
    assert combined["sec_13f_overlap_count"] == 1
    assert combined["sec_13f_eligible_from"] == sec["eligible_from"]
    assert combined["sec_13f_bias_flags"] == ["cusip_mapping_observed_at_not_historical"]
    assert combined["sample_id"].endswith(sec["sha256"][:12])
    assert len(base["tickers"]) == 48


def test_sec_refresh_cli_does_not_require_toss_or_call_llm(monkeypatch, tmp_path):
    calls = []
    sample = {"sample_id": "sec13f-synthetic", "report_period": "2026-06-30",
              "tickers": ["SYN"], "eligible_from": "2026-11-19",
              "quality": {"mapped_candidate_cusips": 1, "ambiguous_candidate_cusips": 0,
                          "ambiguous_security_type_count": 0, "unmapped_candidate_cusips": 0,
                          "status": "inconclusive"}}
    monkeypatch.setattr("tradingagents.zone_13f.refresh_sec_sample",
                        lambda root: calls.append(root) or sample)
    monkeypatch.setattr("cli.main.run_analysis", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("LLM called")))

    result = CliRunner().invoke(app, ["zone-sample", "refresh", "--source", "sec", "--output-dir", str(tmp_path)])

    assert result.exit_code == 0
    assert calls == [tmp_path]
    assert "inconclusive" in result.output
