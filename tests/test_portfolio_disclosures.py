"""The portfolio-disclosures skill script, on synthetic filings only."""

import importlib.util
import zlib
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

import pytest

SCRIPT = (Path(__file__).resolve().parents[1]
          / ".agents/skills/portfolio-disclosures/scripts/disclosures.py")
_spec = importlib.util.spec_from_file_location("portfolio_disclosures", SCRIPT)
disclosures = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(disclosures)


def _filing(form, rows, amendment=""):
    table = "".join(
        f"<infoTable><nameOfIssuer>{name}</nameOfIssuer><titleOfClass>COM</titleOfClass>"
        f"<cusip>{cusip}</cusip>{f'<putCall>{side}</putCall>' if side else ''}<value>{value}</value>"
        f"<shrsOrPrnAmt><sshPrnamt>{shares}</sshPrnamt><sshPrnamtType>SH</sshPrnamtType>"
        "</shrsOrPrnAmt></infoTable>"
        for name, cusip, side, value, shares in rows)
    cover = ('<edgarSubmission xmlns="http://www.sec.gov/edgar/thirteenffiler"><formData><coverPage>'
             f"<amendmentInfo><amendmentType>{amendment}</amendmentType></amendmentInfo>"
             "</coverPage></formData></edgarSubmission>")
    return (f'<DOCUMENT>\n<TYPE>{form}\n<TEXT>\n<XML>\n<?xml version="1.0" encoding="UTF-8"?>\n'
            f"{cover}\n</XML>\n</TEXT>\n</DOCUMENT>\n<DOCUMENT>\n<TYPE>INFORMATION TABLE\n<TEXT>\n<XML>\n"
            '<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">'
            f"{table}</informationTable>\n</XML>\n</TEXT>\n</DOCUMENT>")


AAPL, BAC, NVDA, KO = "037833100", "060505104", "67066G104", "191216100"
FILINGS = {  # accession: (form, filed, period, text)
    "0000000001-26-000001": ("13F-HR", "2026-08-14", "2026-06-30", _filing("13F-HR", [
        ("APPLE INC", AAPL, "", 10_000, 100), ("BANK AMER CORP", BAC, "", 500, 50),
        ("NVIDIA CORP", NVDA, "", 1_000, 10)])),
    "0000000001-26-000002": ("13F-HR/A", "2026-08-20", "2026-06-30", _filing("13F-HR/A", [
        ("APPLE INC", AAPL, "", 10_000, 100), ("BANK AMER CORP", BAC, "", 400, 40),
        ("NVIDIA CORP", NVDA, "", 1_000, 10)], "RESTATEMENT")),
    "0000000001-26-000004": ("13F-HR", "2026-11-14", "2026-09-30", _filing("13F-HR", [
        ("APPLE INC", AAPL, "", 5_000, 50), ("APPLE INC", AAPL, "", 3_000, 30),
        ("NVIDIA CORP", NVDA, "", 1_000, 10), ("NVIDIA CORP", NVDA, "Call", 500, 5)])),
    "0000000001-26-000005": ("13F-HR/A", "2026-11-20", "2026-09-30", _filing("13F-HR/A", [
        ("COCA COLA CO", KO, "", 500, 20)], "NEW HOLDINGS")),
}


def test_13f_applies_amendments_and_compares_reported_shares(monkeypatch):
    recent = {"form": [f[0] for f in FILINGS.values()] + ["4"],
              "accessionNumber": [*FILINGS, "0000000001-26-000003"],
              "filingDate": [f[1] for f in FILINGS.values()] + ["2026-10-01"],
              "reportDate": [f[2] for f in FILINGS.values()] + [""]}
    subs = {"cik": "0000000001", "name": "SYNTHETIC CAPITAL LLC", "filings": {"recent": recent}}
    monkeypatch.setattr(disclosures, "submissions", lambda cik: subs)
    monkeypatch.setattr(disclosures, "sec_text",
                        lambda url: FILINGS[url.rsplit("/", 1)[1].removesuffix(".txt")][3])

    report = disclosures.filer_report("1")

    held = {h["label"]: h for h in report["holdings"]}
    assert (report["period"], report["prior"], report["amendments"]) == ("2026-09-30", "2026-06-30", 1)
    assert report["total"] == 10_000
    assert held["APPLE INC"]["shares"] == 80 and held["APPLE INC"]["status"] == "감소"
    assert held["APPLE INC"]["weight"] == pytest.approx(0.8)
    assert held["NVIDIA CORP"]["status"] == "유지"
    assert held["NVIDIA CORP CALL"]["status"] == "신규"  # an option side is its own position
    assert held["COCA COLA CO"]["status"] == "신규"  # added by the NEW HOLDINGS amendment
    assert report["counts"] == {"신규": 2, "증가": 0, "감소": 1, "유지": 1, "미보고": 1}
    assert report["gone"] == [("BANK AMER CORP", 400.0)]  # the restated prior, not the original
    old = disclosures.parse_filing(_filing("13F-HR", [("APPLE INC", AAPL, "", 7, 1)]), "2022-11-14")
    assert old["rows"][0]["value"] == 7_000  # reported in thousands before 2023-01-03


def test_name_lookup_merges_renamed_filers_and_lists_rivals(monkeypatch):
    buckets = {
        "pershing square": ["PERSHING SQUARE INC.  (PS)  (CIK 0002026053)",
                            "PERSHING SQUARE HOLDCO, L.P.  (CIK 0002026053)"],
        "bridgewater": ["Bridgewater Advisors Inc.  (CIK 0001600319)",
                        "Bridgewater Associates, LP  (CIK 0001350694)"],
        "warren buffett": [],
    }
    monkeypatch.setattr(disclosures.sec_edgar, "_fetch_json", lambda url: {"aggregations": {
        "entity_filter": {"buckets": [{"key": k} for k in buckets[unquote(url.split("entityName=")[1])]]}}})
    monkeypatch.setattr(disclosures, "submissions", lambda cik: {"cik": cik})

    assert disclosures.find_filer("pershing square") == ({"cik": 2026053}, [])
    assert disclosures.find_filer("bridgewater") == (None, [
        "Bridgewater Advisors Inc. (CIK 1600319)", "Bridgewater Associates, LP (CIK 1350694)"])
    assert disclosures.find_filer("warren buffett") == (None, [])


def test_house_lookup_lists_members_sharing_a_name():
    index = [{"Prefix": "Hon.", "First": first, "Last": "Johnson", "StateDst": district,
              "FilingDate": "11/10/2026", "DocID": "1", "Year": "2026"}
             for first, district in (("Julie", "TX32"), ("Mike", "LA04"))]

    assert disclosures.house_report("Johnson", index, 5) == {
        "kind": "하원", "query": "Johnson", "candidates": ["Julie Johnson", "Mike Johnson"]}


def test_ptr_rows_keep_owner_wrapped_cells_and_reported_range():
    lines = [(319.0, "$200?"),
             (348.0, "SP"), (348.0, "Warner Bros. Discovery, Inc. - Series"),
             (362.0, "A Common Stock (WBD)"), (362.0, "[ST]"), (348.0, "S"),
             (348.0, "10/07/2026"), (348.0, "10/07/2026"), (348.0, "$50,001 -"), (362.0, "$100,000"),
             (385.0, "F      S     :"), (385.0, "New"), (402.0, "D          :"), (402.0, "Sold calls."),
             (437.0, "US Treasury Bill"), (437.0, "[GS]"), (437.0, "P"), (437.0, "01/02/2026"),
             (437.0, "01/05/2026"), (437.0, "$1,000,001 - $5,000,000")]

    rows = disclosures.ptr_rows([lines])

    assert [(r["owner"], r["ticker"], r["type"], r["date"], r["kind"], r["amount"]) for r in rows] == [
        ("배우자", "WBD", "매도", "2026-10-07", "ST", "$50,001 - $100,000"),
        ("본인", "", "매수", "2026-01-02", "GS", "$1,000,001 - $5,000,000")]
    assert rows[1]["asset"] == "US Treasury Bill"  # the description above is not part of it
    assert [disclosures.bracket(r["amount"]) for r in rows] == ["$50K~$100K", "$1M~$5M"]


def _pdf(objects, trailer=b""):
    body = b"".join(b"%d 0 obj\r\n%s\r\nendobj\r\n" % (n, o) for n, o in objects.items())
    return b"%PDF-1.4\r\n" + body + b"trailer\r\n<< " + trailer + b" >>\r\n%%EOF"


def _with_stream(head, data):
    return b"<< %s /Filter /FlateDecode /Length %d >>\r\nstream\r\n%s\r\nendstream" % (
        head, len(data), data)


@pytest.mark.parametrize("encrypted", [False, True])
def test_pdf_lines_read_type0_text_plain_or_rc4_encrypted(encrypted):
    assert disclosures._rc4(b"Key", b"Plaintext").hex() == "bbf316e8d940af0ad3"  # RC4 test vector
    streams = {
        2: (b"", b"1 beginbfchar\n<0001> <004A>\n<0002> <0054>\nendbfchar\n"
                 b"1 beginbfrange\n<0010> <0019> <0030>\nendbfrange"),
        3: (b"/Subtype /Form /Resources << /Font << /F1 1 0 R >> >>",
            b"BT /F1 12 Tf 1 0 0 -1 57 348 Tm <00010002> Tj ET\n"
            b"BT /F1 12 Tf 1 0 0 -1 407 348 Tm <0011> Tj 3 0 Td <00120010> Tj ET"),
    }
    objects = {1: b"<< /Type /Font /Subtype /Type0 /ToUnicode 2 0 R >>"}
    trailer = b""
    if encrypted:
        objects[4] = (b"<< /Filter /Standard /V 2 /R 3 /Length 128 /P -1852 /O <"
                      + b"AB" * 32 + b"> /U <" + b"CD" * 32 + b"> >>")
        trailer = b"/Encrypt 4 0 R /ID [<" + b"12" * 16 + b"> <" + b"34" * 16 + b">]"
    keys = disclosures._object_keys(_pdf(objects, trailer), {b"4": objects.get(4, b"")})
    for number, (head, text) in streams.items():
        packed = zlib.compress(text)
        objects[number] = _with_stream(head, disclosures._rc4(keys(b"%d" % number), packed)
                                       if keys else packed)

    assert disclosures.pdf_lines(_pdf(objects, trailer)) == [[(348.0, "JT"), (348.0, "120")]]


def test_snapshot_fits_an_80_column_terminal():
    holding = {"label": "INTERCONTINENTAL EXCHANGE INC NEW", "value": 2.5e10, "weight": 0.25,
               "status": "감소", "ratio": -0.153}
    filer = {"kind": "13F", "name": "SYNTHETIC CAPITAL MANAGEMENT HOLDINGS LLC", "cik": 1,
             "period": "2026-09-30", "prior": "2026-06-30", "filed": "2026-11-14",
             "amendments": 1, "confidential": True, "total": 1e11,
             "url": "https://www.sec.gov/Archives/edgar/data/1/000000000126000004/",
             "holdings": [holding, {**holding, "label": "NEW CO", "status": "신규", "ratio": None}],
             "counts": {"신규": 123, "증가": 4567, "감소": 890, "유지": 12, "미보고": 345},
             "gone": [("BANK AMER CORP", 4e8)]}
    trade = {"date": "2026-10-07", "type": "일부매도", "owner": "배우자", "ticker": "",
             "asset": "Very Long Private Fund Interest Name, LLC", "kind": "OT",
             "amount": "$1,000,001 - $5,000,000"}
    member = {"kind": "하원", "name": "Marjorie Taylor Greene-Example", "district": "GA14",
              "latest": "2026-11-06", "filings": 25, "span": "2025~2026", "trades": [trade] * 12,
              "read": ["https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/2026/20035780.pdf"],
              "unreadable": [], "failed": []}
    reports = [filer, member,
               {"kind": "13F", "query": "bridgewater", "candidates": ["A (CIK 1)", "B (CIK 2)"]},
               {"kind": "하원", "query": "Example", "error": "PTR 색인 조회 실패 (2025 HTTPError, 2026 HTTPError)"}]

    text = disclosures.render(reports, datetime(2026, 11, 18, 23, 0).astimezone(), top=10)

    assert max(map(disclosures.cols, text.splitlines())) <= disclosures.WIDTH
    assert "$1M~$5M" in text and "... 외 2건" in text and "식별 모호" in text
