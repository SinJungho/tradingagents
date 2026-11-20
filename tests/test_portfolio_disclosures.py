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
    asked = []
    monkeypatch.setattr(disclosures, "cusip_tickers",
                        lambda cusips: asked.append(cusips) or {AAPL: "AAPL", BAC: "BAC"})

    report = disclosures.filer_report("1", top=1)

    held = {h["label"]: h for h in report["holdings"]}
    assert (report["period"], report["prior"], report["amendments"]) == ("2026-09-30", "2026-06-30", 1)
    assert report["total"] == 10_000
    assert held["APPLE INC"]["shares"] == 80 and held["APPLE INC"]["status"] == "감소"
    assert held["APPLE INC"]["weight"] == pytest.approx(0.8)
    assert held["NVIDIA CORP"]["status"] == "유지"
    assert held["NVIDIA CORP CALL"]["status"] == "신규"  # an option side is its own position
    assert held["COCA COLA CO"]["status"] == "신규"  # added by the NEW HOLDINGS amendment
    assert report["counts"] == {"신규": 2, "증가": 0, "감소": 1, "유지": 1, "미보고": 1}
    # the restated prior, not the original
    assert [(h["label"], h["value"]) for h in report["gone"]] == [("BANK AMER CORP", 400.0)]
    assert asked == [[AAPL, NVDA, KO, BAC]]  # only rows on screen: top, new, dropped
    assert held["APPLE INC"]["ticker"] == "AAPL" and held["NVIDIA CORP CALL"]["ticker"] == ""
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


def _held(name, cusip, side="", ticker="", **extra):
    return {"name": name, "key": (cusip, side, "SH"), "suffix": side,
            "label": " ".join(filter(None, (name, side))), "ticker": ticker, "value": 2e9,
            "weight": 0.5, "status": "신규", "ratio": None, **extra}


def test_13f_rows_read_like_house_rows_once_the_cusip_has_a_ticker():
    brookfield = _held("BROOKFIELD CORP", "11271J107", ticker="BN")
    unnamed = _held("RESTAURANT BRANDS INTL INC", "76131D103", "CALL", ticker="QSR")
    unknown = _held("SYNTHETIC ISSUER INC", "000000000")
    report = {"name": "Synthetic Capital", "cik": 1, "holdings": [brookfield, unnamed, unknown],
              "counts": {"신규": 3}, "period": "2026-03-31", "filed": "2026-05-15",
              "amendments": 0, "prior": "2025-12-31", "total": 6e9, "confidential": False,
              "ticker_error": "", "url": "https://www.sec.gov/Archives/edgar/data/1/1/",
              "gone": [brookfield]}

    output = disclosures.filer_detail(report, 10)

    assert sum("브룩필드 코퍼레이션 (BN)" in line for line in output) == 3  # table, new, dropped
    assert any("RESTAURANT BRANDS INTL INC (QSR) CALL" in line for line in output)
    assert disclosures.holding_label(unnamed, 20).rstrip().endswith("(QSR) CALL")
    assert disclosures.holding_label(unknown, 36).rstrip() == "SYNTHETIC ISSUER INC"
    failed = disclosures.filer_detail({**report, "ticker_error": "HTTPError"}, 10)
    assert "티커 조회 실패(HTTPError): 원문명으로 표시" in failed


def test_cusip_tickers_batch_by_ten_and_skip_missing_or_split(monkeypatch):
    calls = []

    class Response:
        def __init__(self, jobs):
            self.jobs = jobs

        def raise_for_status(self):
            pass

        def json(self):
            return [{"data": [{"ticker": "BRK/B"}]} if job["idValue"] == "084670702"
                    else {"data": [{"ticker": "A"}, {"ticker": "B"}]} if job["idValue"] == "SPLIT"
                    else {"warning": "No identifier found."} for job in self.jobs]

    monkeypatch.setattr(disclosures.requests, "post",
                        lambda url, json, timeout: calls.append(json) or Response(json))

    found = disclosures.cusip_tickers(["084670702", "SPLIT", *[f"X{n}" for n in range(9)]])

    assert found == {"084670702": "BRK.B"}
    assert [len(jobs) for jobs in calls] == [10, 1]


def test_house_lookup_lists_members_sharing_a_name():
    index = [{"Prefix": "Hon.", "First": first, "Last": "Johnson", "StateDst": district,
              "FilingDate": "11/10/2026", "DocID": "1", "Year": "2026"}
             for first, district in (("Julie", "TX32"), ("Mike", "LA04"))]

    assert disclosures.house_report("Johnson", index, 5) == {
        "kind": "하원", "query": "Johnson", "candidates": ["Julie Johnson (TX32)", "Mike Johnson (LA04)"]}


def test_house_lookup_treats_first_name_variants_as_one_member():
    index = [{"Prefix": "", "First": first, "Last": "Greene", "StateDst": "GA14", "FilingType": "P",
              "FilingDate": date, "DocID": doc, "Year": "2026"}
             for first, date, doc in (("Marjorie Taylor", "01/02/2026", "1"),
                                      ("Marjorie Taylor Mrs", "02/02/2026", "2"))]
    report = disclosures.house_report("Marjorie Taylor Greene", index, 0)
    assert report["name"] == "Marjorie Taylor Mrs Greene" and report["filings"] == 2


def test_list_numbers_filers_then_house_members_by_ptr_count():
    index = [{"First": first, "Last": last, "StateDst": dst, "FilingType": kind, "Year": "2026"}
             for first, last, dst, kind in (("Ann", "Lee", "CA01", "P"), ("Ann", "Lee", "CA01", "P"),
                                            ("Bo", "Kim", "NY02", "P"), ("Bo", "Kim", "NY02", "O"))]
    text = disclosures.catalog(index, "", 2)
    n = len(disclosures.FAMOUS)
    assert "| 1067983 |" in text and f"| {n + 1:>4} | Ann Lee" in text and f"| {n + 2:>4} | Bo Kim" in text
    assert max(disclosures.cols(line) for line in text.splitlines()) <= disclosures.WIDTH
    investors, institutions = text.split("13F 기관")
    assert "| 1067983 |" in investors and "BlackRock" not in investors
    assert "| BlackRock" in institutions.split("하원")[0]
    failed = disclosures.catalog(None, "하원 색인 조회 실패 (Timeout: x)", 2)
    assert "| 1067983 |" in failed and failed.endswith("하원 색인 조회 실패 (Timeout: x)")


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


def test_holdings_keep_only_schedule_a_stock_rows_and_ranges_across_pages():
    page1 = [(403.0, "Value of Asset"), (418.0, "$1,000?"),
             (447.0, "11 Zinfandel Lane - Home & Vineyard"), (447.0, "[RP]"), (447.0, "JT"),
             (447.0, "$5,000,001 -"), (461.0, "$25,000,000"), (447.0, "Grape Sales"),
             (484.0, "L       :"), (484.0, "St. Helena, CA"),
             (519.0, "Apple Inc. (AAPL)"), (519.0, "[ST]"), (519.0, "Over $50,000,000"),
             (560.0, "Microsoft Corporation (MSFT)"), (560.0, "[ST]"), (560.0, "SP"),
             (560.0, "03/02/2025"), (560.0, "S"),  # Schedule B: a sale, not a holding
             (600.0, "Financial Leasing Services"), (600.0, "[OL]"), (600.0, "SP"),
             (600.0, "$100,001 -"), (600.0, "None")]
    page2 = [(403.0, "Asset"), (418.0, "$1,000?"), (430.0, "$250,000")]

    rows = disclosures.holding_rows([page1, page2])

    assert [(r["asset"], r["ticker"], r["kind"], r["owner"], r["value"]) for r in rows] == [
        ("Apple Inc. (AAPL)", "AAPL", "ST", "본인", "Over $50,000,000")]


def test_annual_output_distinguishes_no_stock_from_unreadable():
    annual = {"year": "2025", "filed": "2026-05-15", "amended": 0,
              "url": "https://example.test/annual.pdf", "holdings": [], "error": "", "readable": True}

    assert "표시할 주식 없음" in disclosures.annual_lines(annual, 10)
    annual["readable"] = False
    assert any("판독 불가" in line for line in disclosures.annual_lines(annual, 10))


def _pdf(objects, trailer=b""):
    body = b"".join(b"%d 0 obj\r\n%s\r\nendobj\r\n" % (n, o) for n, o in objects.items())
    return b"%PDF-1.4\r\n" + body + b"trailer\r\n<< " + trailer + b" >>\r\n%%EOF"


def _with_stream(head, data):
    return b"<< %s /Filter /FlateDecode /Length %d >>\r\nstream\r\n%s\r\nendstream" % (
        head, len(data), data)


@pytest.mark.parametrize("encrypted, page_fonts", [(False, False), (True, False), (False, True)])
def test_pdf_lines_read_type0_text_plain_encrypted_or_page_fonts(encrypted, page_fonts):
    assert disclosures._rc4(b"Key", b"Plaintext").hex() == "bbf316e8d940af0ad3"  # RC4 test vector
    streams = {
        2: (b"", b"1 beginbfchar\n<0001> <004A>\n<0002> <0054>\nendbfchar\n"
                 b"1 beginbfrange\n<0010> <0019> <0030>\nendbfrange"),
        3: (b"" if page_fonts else b"/Subtype /Form /Resources << /Font << /F1 1 0 R >> >>",
            b"BT /F1 12 Tf 1 0 0 -1 57 348 Tm <00010002> Tj ET\n"
            b"BT /F1 12 Tf 1 0 0 -1 407 348 Tm <0011> Tj 3 0 Td <00120010> Tj ET"),
    }
    objects = {1: b"<< /Type /Font /Subtype /Type0 /ToUnicode 2 0 R >>"}
    if page_fonts:  # later pages of a filing: the page, not the stream, names the fonts
        objects[5] = b"<< /Type /Page /Resources << /Font << /F1 1 0 R >> >> /Contents 3 0 R >>"
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
    holding = {"name": "ALPHABET INC LONG HOLDINGS", "suffix": "CAP STK CL A", "key": ("1", "", "SH"),
               "label": "ALPHABET INC LONG HOLDINGS CAP STK CL A", "value": 2.5e10, "weight": 0.25,
               "status": "감소", "ratio": -0.153}
    filer = {"kind": "13F", "name": "SYNTHETIC CAPITAL MANAGEMENT HOLDINGS LLC", "cik": 1,
             "period": "2026-09-30", "prior": "2026-06-30", "filed": "2026-11-14",
             "amendments": 1, "confidential": True, "total": 1e11,
             "url": "https://www.sec.gov/Archives/edgar/data/1/000000000126000004/",
             "holdings": [holding, {**holding, "name": "NEW CO", "suffix": "", "label": "NEW CO",
                                   "status": "신규", "ratio": None}],
             "counts": {"신규": 123, "증가": 4567, "감소": 890, "유지": 12, "미보고": 345},
             "gone": [_held("BANK AMER CORP", "060505104")]}
    trade = {"date": "2026-10-07", "type": "일부매도", "owner": "배우자", "ticker": "",
             "asset": "Very Long Private Fund Interest Name, LLC", "kind": "OT",
             "amount": "$1,000,001 - $5,000,000"}
    asset = {"asset": "Very Long Publicly Traded Company Holdings Inc.", "ticker": "",
             "kind": "ST", "owner": "배우자", "value": "Spouse/DC Over $1,000,000"}
    member = {"kind": "하원", "name": "Marjorie Taylor Greene-Example", "district": "GA14",
              "latest": "2026-11-06", "filings": 25, "span": "2024~2026", "trades": [trade] * 12,
              "read": ["https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/2026/20035780.pdf"],
              "unreadable": [], "failed": [],
              "annual": {"year": "2025", "filed": "2026-05-15", "amended": 1, "error": "",
                         "url": "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/2025/1.pdf",
                         "holdings": [asset, {**asset, "value": "None"}]}}
    reports = [filer, member,
               {"kind": "13F", "query": "bridgewater", "candidates": ["A (CIK 1)", "B (CIK 2)"]},
               {"kind": "하원", "query": "Example", "error": "PTR 색인 조회 실패 (2025 HTTPError, 2026 HTTPError)"}]

    text = disclosures.render(reports, datetime(2026, 11, 18, 23, 0).astimezone(), top=10)

    assert max(map(disclosures.cols, text.splitlines())) <= disclosures.WIDTH
    assert "$1M~$5M" in text and "... 외 2건" in text and "식별 모호" in text
    assert "CAP STK CL A |" in text  # a cut name keeps the share class
    assert ">$1M" in text and "| 없음" in text and "수정 신고 1건 미반영" in text
    house_output = "\n".join(disclosures.house_detail(member, 10))
    assert "Very Long Publicly Traded" in house_output
    assert "Private Real Estate Partnership" not in house_output
    assert "주식 2건" in house_output

    def edges(line):  # terminal columns of the table's border characters
        spots, col = [], 0
        for char in line:
            if char in "+|":
                spots.append(col)
            col += disclosures.cols(char)
        return spots

    tables, current = [], []
    for line in text.splitlines():
        if line[:1] in "+|" and line:
            current.append(line)
        elif current:
            tables, current = [*tables, current], []
    assert len(tables) == 5  # overview, 13F holdings and changes, House assets, House trades
    for rows in tables:
        assert rows[0].startswith("+-") and rows[-1] == rows[0]
        assert {tuple(edges(row)) for row in rows} == {tuple(edges(rows[0]))}


def test_house_assets_read_korean_name_and_keep_the_ticker():
    known = {"ticker": "GOOGL", "asset": "Alphabet Inc. - Class A (GOOGL)", "kind": "ST"}
    unknown = {"ticker": "CLNE", "asset": "Clean Energy Fuels Corp. - Common Stock (CLNE)", "kind": "OP"}
    plain = {"ticker": "", "asset": "US Treasury Bill", "kind": "GS"}

    assert disclosures.asset_label(known, 26).rstrip() == "구글 (GOOGL)"
    assert disclosures.asset_label(unknown, 40).rstrip() == "Clean Energy Fuels Corp. (CLNE) 옵션"
    assert disclosures.asset_label(unknown, 20).rstrip().endswith("(CLNE) 옵션")
    assert disclosures.asset_label(plain, 26).rstrip() == "US Treasury Bill [GS]"


def test_new_and_dropped_rows_share_one_table_with_their_quarter():
    new = [_held(f"NEW {n}", f"N{n}") for n in range(7)]
    gone = [_held("OLD ONE", "O1", ticker="BN")]
    lines = disclosures.changes(new, gone)
    text = "\n".join(lines)
    lines = lines[1:]  # a blank line parts it from the holdings table
    assert "| 신규   | NEW 0" in text and "| 외 2개" in text and "NEW 5" not in text
    assert any("브룩필드 코퍼레이션 (BN)" in line and "직전 분기" in line for line in lines)
    assert {disclosures.cols(line) for line in lines} == {disclosures.cols(lines[0])} and \
        disclosures.cols(lines[0]) <= disclosures.WIDTH
    assert disclosures.changes([], []) == []
