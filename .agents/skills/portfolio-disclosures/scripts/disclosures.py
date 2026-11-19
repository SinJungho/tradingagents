"""Form 13F holdings and House trade reports, side by side in a terminal.

Reads official sources: SEC EDGAR for Form 13F and the House Clerk for
Periodic Transaction Reports (PTR). Senators are out of scope; the Senate eFD
answers 403 to any client that is not a browser. 13F rows carry no ticker, so
the shown ones are mapped by CUSIP through OpenFIGI, a secondary source.

Run from the repository root with the project venv. Importing the package loads
.env, so SEC sees the SEC_EDGAR_USER_AGENT contact it asks for:

    .venv/bin/python .agents/skills/portfolio-disclosures/scripts/disclosures.py \\
        --filer 1067983 "pershing square" --house Pelosi
"""

from __future__ import annotations

import argparse
import hashlib
import io
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
import zlib
from collections import Counter
from datetime import date, datetime, timedelta
from urllib.parse import quote

import requests

from tradingagents.dataflows.net import get_with_retry
from tradingagents.dataflows.vendors import sec_edgar

WIDTH = 78  # an 80-column terminal, inside the fenced block the agent prints
SEC = "https://www.sec.gov"
HOUSE = "https://disclosures-clerk.house.gov/public_disc"
FIGI = "https://api.openfigi.com/v3/mapping"
LISTED = 5  # new and dropped 13F rows listed under the table


# --- Form 13F ---------------------------------------------------------------

def sec_text(url: str) -> str:
    sec_edgar._wait_for_request_slot()
    return get_with_retry(url, timeout=60, provider="SEC EDGAR",
                          headers={"User-Agent": sec_edgar._user_agent()}).text


def submissions(cik: int) -> dict:
    return sec_edgar._fetch_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")


def cusip_tickers(cusips: list[str]) -> dict[str, str]:
    """US tickers by CUSIP from OpenFIGI; a CUSIP with none or several gets no entry.

    Without an API key OpenFIGI takes 10 jobs a request and 25 requests a minute.
    """
    found = {}
    for start in range(0, len(cusips), 10):
        batch = cusips[start:start + 10]
        response = requests.post(FIGI, timeout=30, json=[
            {"idType": "ID_CUSIP", "idValue": cusip, "exchCode": "US"} for cusip in batch])
        response.raise_for_status()
        for cusip, result in zip(batch, response.json(), strict=True):
            tickers = {row["ticker"].replace("/", ".") for row in result.get("data", [])}
            if len(tickers) == 1:
                found[cusip] = tickers.pop()
    return found


def find_filer(query: str) -> tuple[dict | None, list[str]]:
    """The submissions of the 13F filer a CIK or name points to, else the candidates.

    A name goes through EDGAR full-text search over 13F-HR filings of the last 400
    days, so only active filers match: "Warren Buffett" files 13F-NT (Berkshire
    reports for him) and finds none, "Bridgewater" finds two firms to choose from.
    """
    if query.isdigit():
        return submissions(int(query)), []
    today = date.today()
    found = sec_edgar._fetch_json(
        "https://efts.sec.gov/LATEST/search-index?forms=13F-HR&dateRange=custom"
        f"&startdt={today - timedelta(days=400)}&enddt={today}&entityName={quote(query)}")
    if "aggregations" not in found:
        raise ValueError(found.get("message") or "EDGAR search answered in an unknown shape")
    filers: dict[int, str] = {}
    for bucket in found["aggregations"]["entity_filter"]["buckets"]:
        # "BERKSHIRE HATHAWAY INC  (BRK-A, BRK-B)  (CIK 0001067983)"; renamed filers repeat a CIK
        cik = int(re.search(r"\(CIK (\d+)\)", bucket["key"]).group(1))
        filers.setdefault(cik, re.split(r"\s{2,}\(", bucket["key"])[0])
    if len(filers) == 1:
        return submissions(next(iter(filers))), []
    return None, [f"{name} (CIK {cik})" for cik, name in filers.items()]


def periods_13f(subs: dict, want: int = 2) -> list[tuple[str, list[dict]]]:
    """13F-HR filings and their amendments by report period, newest first.

    `recent` holds a filer's last 1,000 filings, which for a bank issuing notes
    daily can miss whole quarters, so up to two older pages are read as needed.
    """
    found: dict[str, list[dict]] = {}
    pages = [subs["filings"]["recent"], *(f["name"] for f in subs["filings"].get("files", [])[:2])]
    for page in pages:
        if sum(any(f["form"] == "13F-HR" for f in fs) for fs in found.values()) >= want:
            break
        if isinstance(page, str):
            page = sec_edgar._fetch_json(f"https://data.sec.gov/submissions/{page}")
        for form, accession, filed, period in zip(page["form"], page["accessionNumber"],
                                                  page["filingDate"], page["reportDate"], strict=True):
            if form in ("13F-HR", "13F-HR/A"):
                found.setdefault(period, []).append(
                    {"form": form, "accession": accession, "filed": filed})
    return [(period, filings) for period, filings in sorted(found.items(), reverse=True)
            if any(f["form"] == "13F-HR" for f in filings)]


def _xml(text: str) -> ET.Element:
    root = ET.fromstring(text.encode())
    for element in root.iter():
        element.tag = element.tag.rpartition("}")[2]
    return root


def parse_filing(text: str, filed: str) -> dict:
    """Cover facts and holding rows from a 13F's complete submission text."""
    docs = {}
    for doc in re.findall(r"<DOCUMENT>(.*?)</DOCUMENT>", text, re.S):
        kind = re.search(r"<TYPE>([^\n<]+)", doc)
        xml = re.search(r"<XML>\s*(.*?)\s*</XML>", doc, re.S)
        if kind and xml:
            docs[kind.group(1).strip()] = _xml(xml.group(1))
    cover = docs.get("13F-HR", docs.get("13F-HR/A"))
    if cover is None:
        raise ValueError("13F XML cover page not found")
    table = docs.get("INFORMATION TABLE")
    # Filed before 2023-01-03, value is in thousands of dollars; since then, in dollars.
    scale = 1000 if filed < "2023-01-03" else 1
    rows = [{
        "name": row.findtext("nameOfIssuer", "").strip(),
        "title": row.findtext("titleOfClass", "").strip(),
        "key": (row.findtext("cusip", "").strip().upper(),
                row.findtext("putCall", "").strip().upper(),
                row.findtext("shrsOrPrnAmt/sshPrnamtType", "").strip()),
        "value": float(row.findtext("value") or 0) * scale,
        "shares": float(row.findtext("shrsOrPrnAmt/sshPrnamt") or 0),
    } for row in ([] if table is None else table.iter("infoTable"))]
    return {"amendment": cover.findtext(".//amendmentType", "").strip().upper(),
            "confidential": cover.findtext(".//isConfidentialOmitted", "").strip() == "true",
            "rows": rows}


def period_holdings(cik: int, filings: list[dict]) -> tuple[dict, dict]:
    """Holdings at one report period: the latest original report, then its amendments.

    A RESTATEMENT replaces the table so far and NEW HOLDINGS adds to it, in filing
    order. Rows for one security, option side and unit are summed: filers list a
    row per sub-manager and voting split.
    """
    filings = sorted(filings, key=lambda f: (f["filed"], f["accession"]))
    start = max(i for i, f in enumerate(filings) if f["form"] == "13F-HR")
    original = filings[start]["accession"]
    info = {"filed": filings[start]["filed"], "amendments": 0, "confidential": False,
            "url": f"{SEC}/Archives/edgar/data/{cik}/{original.replace('-', '')}/"}
    rows = []
    for filing in filings[start:]:
        folder = f"{SEC}/Archives/edgar/data/{cik}/{filing['accession'].replace('-', '')}"
        doc = parse_filing(sec_text(f"{folder}/{filing['accession']}.txt"), filing["filed"])
        if filing["form"] == "13F-HR/A":
            info["amendments"] += 1
            if doc["amendment"] == "RESTATEMENT":
                rows = []
        rows += doc["rows"]
        info["confidential"] |= doc["confidential"]
    holdings: dict[tuple, dict] = {}
    for row in rows:
        held = holdings.setdefault(row["key"], {**row, "value": 0.0, "shares": 0.0})
        held["value"] += row["value"]
        held["shares"] += row["shares"]
    return holdings, info


def compare(now: dict, before: dict | None) -> dict | None:
    """Label each holding and set its reported share change against the prior period.

    Share counts are compared as filed: a split reads as an increase, and a
    change is not evidence of a trade.
    """
    names = Counter((h["name"], key[1]) for key, h in now.items())
    for key, held in now.items():
        # The class and option side tell rows of one issuer apart, so a cut keeps them.
        held["suffix"] = " ".join(filter(None, (
            held["title"] if names[held["name"], key[1]] > 1 else "", key[1])))
        held["label"] = " ".join(filter(None, (held["name"], held["suffix"])))
        prior = before.get(key) if before is not None else None
        held["ratio"] = None
        if before is None:
            held["status"] = None
        elif prior is None:
            held["status"] = "신규"
        else:
            held["ratio"] = held["shares"] / prior["shares"] - 1 if prior["shares"] else 0.0
            held["status"] = "증가" if held["ratio"] > 0 else "감소" if held["ratio"] < 0 else "유지"
    if before is None:
        return None
    counts = Counter(h["status"] for h in now.values())
    gone = sum(key not in now for key in before)
    return {"신규": counts["신규"], "증가": counts["증가"], "감소": counts["감소"],
            "유지": counts["유지"], "미보고": gone}


def filer_report(query: str, top: int = 10) -> dict:
    subs, candidates = find_filer(query)
    if subs is None:
        return {"kind": "13F", "query": query, "candidates": candidates}
    cik = int(subs["cik"])
    periods = periods_13f(subs)
    if not periods:
        return {"kind": "13F", "query": query, "error": f"{subs['name']}: 13F-HR 제출 없음"}
    now, info = period_holdings(cik, periods[0][1])
    before = period_holdings(cik, periods[1][1])[0] if len(periods) > 1 else None
    counts = compare(now, before)
    gone = sorted(({**h, "suffix": k[1], "label": " ".join(filter(None, (h["name"], k[1])))}
                   for k, h in (before or {}).items() if k not in now), key=lambda h: -h["value"])
    total = sum(h["value"] for h in now.values())
    for held in now.values():
        held["weight"] = held["value"] / total if total else 0.0
    holdings = sorted(now.values(), key=lambda h: -h["value"])
    shown = [*holdings[:top], *[h for h in holdings if h["status"] == "신규"][:LISTED], *gone[:LISTED]]
    try:
        tickers, ticker_error = cusip_tickers(list(dict.fromkeys(h["key"][0] for h in shown))), ""
    except Exception as exc:  # the filed names still read without tickers
        tickers, ticker_error = {}, type(exc).__name__
    for held in shown:
        held["ticker"] = tickers.get(held["key"][0], "")
    return {"kind": "13F", "name": subs["name"], "cik": cik, "period": periods[0][0],
            "prior": periods[1][0] if len(periods) > 1 else None, "total": total,
            "holdings": holdings, "counts": counts, "gone": gone,
            "ticker_error": ticker_error, **info}


# --- House PTR ----------------------------------------------------------------

TRADES = {"P": "매수", "S": "매도", "S (partial)": "일부매도", "E": "교환"}
OWNERS = {"SP": "배우자", "JT": "공동", "DC": "자녀"}
DATE = re.compile(r"\d{2}/\d{2}/\d{4}")
AMOUNT = re.compile(r"\$[\d,]+ - \$[\d,]+|(?:Spouse/DC )?Over \$[\d,]+")


def house_filings(year: int) -> list[dict]:
    """The year's PTRs (P), annual reports (O) and amendments (A) from the Clerk's index."""
    raw = get_with_retry(f"{HOUSE}/financial-pdfs/{year}FD.zip", timeout=60,
                         provider="House Clerk").content
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        root = ET.fromstring(archive.read(f"{year}FD.xml"))
    fields = ("Prefix", "First", "Last", "StateDst", "FilingType", "FilingDate", "DocID", "Year")
    return [{f: (member.findtext(f) or "").strip() for f in fields}
            for member in root.iter("Member") if member.findtext("FilingType") in ("P", "O", "A")]


# Padding the PDF Standard security handler appends to a password (ISO 32000-1, 7.6.3.3).
PDF_PAD = bytes.fromhex("28BF4E5E4E758A4164004E56FFFA01082E2E00B6D0683E802F0CA9FE6453697A")


def _rc4(key: bytes, data: bytes) -> bytes:
    box, j = list(range(256)), 0
    for i in range(256):
        j = (j + box[i] + key[i % len(key)]) % 256
        box[i], box[j] = box[j], box[i]
    out, i, j = bytearray(), 0, 0
    for byte in data:
        i = (i + 1) % 256
        j = (j + box[i]) % 256
        box[i], box[j] = box[j], box[i]
        out.append(byte ^ box[(box[i] + box[j]) % 256])
    return bytes(out)


def _object_keys(data: bytes, objects: dict[bytes, bytes]):
    """Per-object RC4 keys when the PDF is encrypted, else None.

    About half the House PTRs carry an owner password that only restricts editing:
    the user password is empty, so any viewer opens them, and so can this. Only
    the RC4 revisions (R2, R3) are read; an AES file raises and reads as unreadable.
    """
    ref = re.search(rb"/Encrypt (\d+) 0 R", data)
    if not ref:
        return None
    spec = objects.get(ref.group(1), b"")
    revision = re.search(rb"/R (\d+)", spec)
    if b"/Standard" not in spec or not revision or revision.group(1) not in (b"2", b"3"):
        raise ValueError("unsupported PDF encryption")
    bits = re.search(rb"/Length (\d+)", spec)
    size = int(bits.group(1)) // 8 if bits and revision.group(1) == b"3" else 5
    owner = bytes.fromhex(re.search(rb"/O\s*<(\w+)>", spec).group(1).decode())
    perms = (int(re.search(rb"/P (-?\d+)", spec).group(1)) & 0xFFFFFFFF).to_bytes(4, "little")
    file_id = bytes.fromhex(re.search(rb"/ID\s*\[\s*<(\w+)>", data).group(1).decode())
    key = hashlib.md5(PDF_PAD + owner + perms + file_id).digest()
    if revision.group(1) == b"3":
        for _ in range(50):
            key = hashlib.md5(key[:size]).digest()
    key = key[:size]
    return lambda number: hashlib.md5(
        key + int(number).to_bytes(3, "little") + b"\0\0").digest()[:min(size + 5, 16)]


def _stream(body: bytes, key: bytes | None) -> bytes:
    head, _, rest = body.partition(b"stream")
    if not rest or b"/Image" in head or b"/Length1" in head:  # images, embedded fonts
        return b""
    raw = rest.lstrip(b"\r\n").rpartition(b"endstream")[0]
    raw = _rc4(key, raw) if key else raw
    try:
        return zlib.decompressobj().decompress(raw) if b"FlateDecode" in head else raw
    except zlib.error:
        return b""


def _unicode_map(cmap: str) -> dict[int, str]:
    codes = {}
    for block in re.findall(r"beginbfchar(.*?)endbfchar", cmap, re.S):
        for src, dst in re.findall(r"<(\w+)>\s*<(\w+)>", block):
            codes[int(src, 16)] = bytes.fromhex(dst).decode("utf-16-be")
    for block in re.findall(r"beginbfrange(.*?)endbfrange", cmap, re.S):
        for low, high, dst in re.findall(r"<(\w+)>\s*<(\w+)>\s*<(\w+)>", block):
            for code in range(int(low, 16), int(high, 16) + 1):
                codes[code] = chr(int(dst, 16) + code - int(low, 16))
    return codes


# ponytail: reads only what the House e-filing PDFs use (Type0 fonts with ToUnicode
# maps, one BT block per table cell line at an absolute Tm); switch to pypdf if the
# Clerk changes generator. Scanned paper filings carry no text and come back empty.
def pdf_lines(data: bytes) -> list[list[tuple[float, str]]]:
    """Text lines as (y, text) per content stream, in drawing order."""
    objects = dict(re.findall(rb"(\d+) 0 obj(.*?)endobj", data, re.S))
    keys = _object_keys(data, objects)

    def stream(number: bytes) -> str:
        key = keys(number) if keys else None
        return _stream(objects.get(number, b""), key).decode("latin-1")

    # A form XObject carries its fonts itself; a page's content stream gets them from the page.
    page_of = {ref: body for body in objects.values()
               for ref in re.findall(rb"/Contents (\d+) 0 R", body)}
    pages = []
    for number, body in objects.items():
        content = stream(number)
        if "BT" not in content:
            continue
        fonts = {}
        for table in re.findall(rb"/Font\s*<<(.*?)>>", body + page_of.get(number, b""), re.S):
            for name, ref in re.findall(rb"/(\w+)\s+(\d+) 0 R", table):
                found = re.search(rb"/ToUnicode (\d+) 0 R", objects.get(ref, b""))
                if found:
                    fonts[name.decode()] = _unicode_map(stream(found.group(1)))
        lines = []
        for block in re.findall(r"\bBT\b(.*?)\bET\b", content, re.S):
            at = re.search(r"([-\d.]+) ([-\d.]+) Tm", block)
            font, text = {}, ""
            for name, hexes in re.findall(r"/(\w+) [-\d.]+ Tf|<([0-9A-Fa-f]*)>", block):
                if name:
                    font = fonts.get(name, {})
                else:
                    text += "".join(font.get(int(hexes[i:i + 4], 16), "")
                                    for i in range(0, len(hexes), 4))
            if at and text.strip():
                lines.append((float(at.group(2)), text.strip()))
        pages.append(lines)
    return pages


def _iso(day: str) -> str:
    return datetime.strptime(day, "%m/%d/%Y").date().isoformat()


def _range(pages: list[list[tuple[float, str]]], page: int, j: int) -> str:
    """A reported range, joined when it wraps: '$50,001 -' then '$100,000'.

    At a page end the second half comes after the next page's repeated header.
    """
    text = pages[page][j][1]
    if not text.endswith("-"):
        return text
    rest = pages[page][j + 1:j + 3] + (pages[page + 1][:15] if page + 1 < len(pages) else [])
    return " ".join([text, *[t for _, t in rest if re.fullmatch(r"\$[\d,]+", t)][:1]])


def ptr_rows(pages: list[list[tuple[float, str]]]) -> list[dict]:
    """Transactions from PTR text lines.

    A row starts where a transaction type is followed by two dates. Its owner and
    asset cells start on that line and wrap below it, so they are the lines drawn
    just before the type at or below its height.
    """
    rows = []
    for page, lines in enumerate(pages):
        for i, (y, text) in enumerate(lines):
            after = [t for _, t in lines[i + 1:i + 5]]
            if text not in TRADES or len(after) < 3 or not all(map(DATE.fullmatch, after[:2])):
                continue
            start = i
            while start and lines[start - 1][0] >= y:
                start -= 1
            cells = [t for _, t in lines[start:i]]
            owner = OWNERS.get(cells[0], "") if cells else ""
            asset = " ".join(cells[1:] if owner else cells)
            kind = re.search(r"\[(\w{2})\]", asset)
            tickers = re.findall(r"\(([A-Z][A-Z0-9./-]{0,9})\)", asset)
            rows.append({
                "date": _iso(after[0]), "notified": _iso(after[1]), "type": TRADES[text],
                "owner": owner or "본인", "ticker": tickers[-1] if tickers else "",
                "asset": re.sub(r"\s*\[\w{2}\]", "", asset), "kind": kind.group(1) if kind else "",
                "amount": _range(pages, page, i + 3),
            })
    return rows


VALUE = re.compile(r"\$[\d,]+ - \$[\d,]+|(?:Spouse/DC )?Over \$[\d,]+|None|Undetermined")
TAG = re.compile(r"\[(\w{2})\]$")


def holding_rows(pages: list[list[tuple[float, str]]]) -> list[dict]:
    """Assets from an annual report's Schedule A, largest reported range first.

    A holding is an asset whose type tag is followed by its owner and a value
    range. Schedule B transactions put a date there instead, so they drop out.
    """
    rows = []
    for page, lines in enumerate(pages):
        for i, (_, text) in enumerate(lines):
            tag = TAG.search(text)
            j = i + 1 + (i + 1 < len(lines) and lines[i + 1][1] in OWNERS)
            if not tag or tag.group(1) != "ST" or j >= len(lines):
                continue
            y, value = lines[j][0], _range(pages, page, j)
            if not VALUE.fullmatch(value):
                continue
            start = i
            while start and lines[start - 1][0] >= y:
                start -= 1
            asset = TAG.sub("", " ".join(t for _, t in lines[start:i + 1])).strip()
            tickers = re.findall(r"\(([A-Z][A-Z0-9./-]{0,9})\)", asset)
            rows.append({"asset": asset, "ticker": tickers[-1] if tickers else "",
                         "kind": tag.group(1), "owner": OWNERS.get(lines[i + 1][1], "본인"),
                         "value": value})

    def floor(row: dict) -> int:
        found = re.search(r"\$([\d,]+)", row["value"])
        return int(found.group(1).replace(",", "")) + ("Over" in row["value"]) if found else -1

    return sorted(rows, key=floor, reverse=True)


def _house_pdf(url: str) -> list[list[tuple[float, str]]]:
    return pdf_lines(get_with_retry(url, timeout=60, provider="House Clerk").content)


def house_report(query: str, index: list[dict], ptrs: int) -> dict:
    words = set(query.casefold().split())
    hits = [f for f in index
            if words <= set(f"{f['First']} {f['Last']}".casefold().replace(",", " ").split())]
    # A member is a last name and district; First varies between filings ("Mrs").
    members = {(f["Last"], f["StateDst"]): f"{f['First']} {f['Last']} ({f['StateDst']})" for f in hits}
    if len(members) != 1:
        return {"kind": "하원", "query": query, "candidates": sorted(members.values())}
    hits.sort(key=lambda f: datetime.strptime(f["FilingDate"], "%m/%d/%Y"), reverse=True)
    trades = [f for f in hits if f["FilingType"] == "P"]
    years = sorted({f["Year"] for f in index})
    report = {"kind": "하원", "name": f"{hits[0]['First']} {hits[0]['Last']}",
              "district": hits[0]["StateDst"],
              "latest": _iso(trades[0]["FilingDate"]) if trades else "",
              "filings": len(trades), "span": f"{years[0]}~{years[-1]}",
              "trades": [], "read": [], "unreadable": [], "failed": [], "annual": None}
    annual = max((f for f in hits if f["FilingType"] == "O"), default=None,
                 key=lambda f: (f["Year"], datetime.strptime(f["FilingDate"], "%m/%d/%Y")))
    if annual:
        url = f"{HOUSE}/financial-pdfs/{annual['Year']}/{annual['DocID']}.pdf"
        report["annual"] = {"year": annual["Year"], "filed": _iso(annual["FilingDate"]), "url": url,
                            "amended": sum(f["FilingType"] == "A" and f["Year"] == annual["Year"]
                                           for f in hits),
                            "holdings": [], "readable": False, "error": ""}
        try:
            pages = _house_pdf(url)
            report["annual"]["readable"] = any(pages)
            report["annual"]["holdings"] = holding_rows(pages)
        except Exception as exc:  # the trades below are still worth showing
            report["annual"]["error"] = f"조회 실패 ({type(exc).__name__})"
    for filing in trades[:ptrs]:
        url = f"{HOUSE}/ptr-pdfs/{filing['Year']}/{filing['DocID']}.pdf"
        try:
            rows = ptr_rows(_house_pdf(url))
        except Exception as exc:  # one report's failure leaves the others readable
            report["failed"].append(f"{url} ({type(exc).__name__})")
            continue
        report["read" if rows else "unreadable"].append(url)
        report["trades"] += rows
    return report


# --- Terminal rendering ---------------------------------------------------------

def cols(text: str) -> int:
    """Terminal columns `text` takes: Hangul and other wide characters take two."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def fit(text: str, width: int, right: bool = False) -> str:
    if cols(text) > width:
        while cols(text) > width - 2:
            text = text[:-1]
        text += ".."
    gap = " " * (width - cols(text))
    return gap + text if right else text + gap


def usd(value: float, spec: str = ".1f") -> str:
    for unit, size in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(value) >= size:
            return f"${value / size:{spec}}{unit}"
    return f"${value:,.0f}"


def bracket(amount: str) -> str:
    """A reported range, shorter: '$1,001 - $15,000' reads '$1K~$15K'."""
    values = [int(n.replace(",", "")) for n in re.findall(r"\$([\d,]+)", amount)]
    if len(values) == 2:
        return f"{usd(values[0] - 1, 'g')}~{usd(values[1], 'g')}"
    if len(values) == 1 and "Over" in amount:
        return f">{usd(values[0], 'g')}"
    return amount


def share_change(held: dict) -> str:
    if held["ratio"] is None or held["status"] == "유지":
        return held["status"] or "-"
    return f"{held['ratio']:+.0%}" if abs(held["ratio"]) >= 10 else f"{held['ratio']:+.1%}"


def status(report: dict) -> str:
    if "error" in report:
        return report["error"]
    if report["candidates"]:
        return "식별 모호: " + ", ".join(report["candidates"])
    return "13F 제출자 없음" if report["kind"] == "13F" else "PTR 색인에 없음"


def table(columns: list[tuple[str, int, bool]], rows: list[list[str]]) -> list[str]:
    """An ASCII-bordered table; each column is (title, width, right-aligned).

    Plain ASCII borders, since box-drawing characters are two columns wide in
    some East Asian terminal settings and would push the right edge out.
    """
    rule = "+" + "+".join("-" * (width + 2) for _, width, _ in columns) + "+"

    def line(cells: list[str]) -> str:
        return "|" + "|".join(f" {fit(cell, width, right)} "
                              for cell, (_, width, right) in zip(cells, columns, strict=True)) + "|"

    return [rule, line([title for title, _, _ in columns]), rule, *map(line, rows), rule]


OVERVIEW = [("구분", 4, False), ("대상", 19, False), ("기준일", 10, False), ("규모", 7, True),
            ("변화·거래", 22, False)]


def overview(report: dict) -> list[str]:
    if "holdings" in report:
        counts = report["counts"]
        tail = ("비교 불가" if counts is None else
                " ".join(f"{k}{v}" for k, v in counts.items() if v and k != "유지") or "변화 없음")
        return ["13F", report["name"], report["period"], usd(report["total"]), tail]
    if "trades" in report:
        tally = Counter(t["type"] for t in report["trades"])
        tail = " ".join([*(f"{k}{tally[k]}" for k in TRADES.values() if tally[k]),
                         *(f"판독불가{n}" for n in [len(report["unreadable"])] if n),
                         *(f"실패{n}" for n in [len(report["failed"])] if n)])
        return [report["kind"], f"{report['name']} {report['district']}", report["latest"],
                f"{len(report['trades'])}건", tail]
    return [report["kind"], report["query"], "", "", status(report)]


def changes(new: list[dict], gone: list[dict], limit: int = LISTED) -> list[str]:
    """New and dropped 13F rows in one table; a dropped row's value is last quarter's."""
    rows = []
    for label, items, basis in (("신규", new, "이번 분기"), ("미보고", gone, "직전 분기")):
        rows += [[label if n == 0 else "", holding_label(h, 41), usd(h["value"]), basis]
                 for n, h in enumerate(items[:limit])]
        if len(items) > limit:
            rows.append(["", f"외 {len(items) - limit}개", "", ""])
    if not rows:
        return []
    return ["", *table([("구분", 6, False), ("종목", 41, False), ("가치", 7, True), ("기준", 9, False)], rows)]


def filer_detail(report: dict, top: int) -> list[str]:
    holdings, counts = report["holdings"], report["counts"]
    shown = holdings[:top]
    lines = [
        f"[13F] {report['name']} · CIK {report['cik']}",
        f"보고기간 {report['period']} · 제출 {report['filed']}"
        + (f" · 수정 {report['amendments']}건 반영" if report["amendments"] else "")
        + (f" · 비교 {report['prior']}" if report["prior"] else " · 직전 분기 없음(비교 불가)"),
        f"신고가치 {usd(report['total'])} · {len(holdings)}종목 · "
        f"상위 {len(shown)} 비중 {sum(h['weight'] for h in shown):.1%}",
    ]
    if counts:
        lines.append("변화(주식 수) " + " · ".join(f"{k} {v}" for k, v in counts.items()))
    if report["confidential"]:
        lines.append("일부 보유는 기밀 처리로 이 신고에서 빠짐")
    if report.get("ticker_error"):
        lines.append(f"티커 조회 실패({report['ticker_error']}): 원문명으로 표시")
    lines += table([("#", 3, True), ("종목", 36, False), ("가치", 7, True), ("비중", 6, True),
                    ("주식 수", 7, True)],
                   [[str(n), holding_label(held, 36), usd(held["value"]), f"{held['weight']:.1%}",
                     share_change(held)]
                    for n, held in enumerate(shown, 1)])
    lines += changes([h for h in holdings if h["status"] == "신규"], report["gone"])
    return [*lines, f"원문 {report['url']}"]


def holding_label(held: dict, width: int) -> str:
    """A 13F row as '구글 (GOOGL)' once its CUSIP has a ticker, else the filed name."""
    side = held["key"][1]
    if held.get("ticker"):
        return ticker_label(held["name"], held["ticker"], f" {side}" if side else "", width)
    if cols(held["label"]) <= width or not held["suffix"]:
        return fit(held["label"], width)
    # A cut name keeps the class and option side that tell the issuer's rows apart.
    return fit(held["name"], width - cols(held["suffix"]) - 1).rstrip() + " " + held["suffix"]


# Korean names for tickers in House filings and 13F rows. A ticker missing here
# keeps its filed English name: a guessed Korean name would read as fact.
TICKER_NAMES = {
    "AAPL": "애플", "AB": "얼라이언스번스타인", "AMAT": "어플라이드 머티어리얼즈", "AMD": "AMD",
    "AMZN": "아마존", "AVGO": "브로드컴", "AXP": "아메리칸 익스프레스", "BAC": "뱅크오브아메리카",
    "BE": "블룸에너지", "BN": "브룩필드 코퍼레이션", "BRK.B": "버크셔 해서웨이", "CB": "처브",
    "CMCSA": "컴캐스트", "COST": "코스트코", "CRM": "세일즈포스", "CRWD": "크라우드스트라이크",
    "CVX": "셰브론", "DBX": "드롭박스", "DIS": "디즈니", "GOOG": "구글", "GOOGL": "구글",
    "IBKR": "인터랙티브 브로커스", "INTC": "인텔", "JPM": "JP모건체이스", "KO": "코카콜라",
    "LRCX": "램리서치", "MA": "마스터카드", "MCO": "무디스", "META": "메타", "MORN": "모닝스타",
    "MSFT": "마이크로소프트", "MU": "마이크론", "NFLX": "넷플릭스", "NVDA": "엔비디아",
    "ORCL": "오라클", "OXY": "옥시덴탈 페트롤리엄", "PANW": "팔로알토 네트웍스", "PYPL": "페이팔",
    "QCOM": "퀄컴", "RBLX": "로블록스", "SQ": "블록", "T": "AT&T", "TSLA": "테슬라", "UBER": "우버",
    "V": "비자", "VST": "비스트라", "WBD": "워너브라더스 디스커버리", "WMT": "월마트",
}


def ticker_label(name: str, ticker: str, tail: str, width: int) -> str:
    """'구글 (GOOGL)': the Korean name if registered, else the filed one; a cut spares the ticker."""
    tail = f" ({ticker}){tail}"
    return fit(fit(TICKER_NAMES.get(ticker) or name, width - cols(tail)).rstrip() + tail, width)


def asset_label(trade: dict, width: int) -> str:
    ticker, kind = trade["ticker"], trade["kind"]
    tail = " 옵션" if kind == "OP" else f" [{kind}]" if kind not in ("ST", "") else ""
    if not ticker:
        return fit(trade["asset"] + tail, width)
    return ticker_label(trade["asset"].split(f"({ticker})")[0].split(" - ")[0].strip(" ,"),
                        ticker, tail, width)


VALUE_WORDS = {"None": "없음", "Undetermined": "미확정"}


def annual_lines(annual: dict | None, top: int) -> list[str]:
    if annual is None:
        return ["연간 재무공시: 색인에서 찾지 못함"]
    holdings = annual["holdings"]
    lines = [f"연간 재무공시 {annual['year']}년분 · 제출 {annual['filed']} · 주식 {len(holdings)}건"
             + (f" · 수정 신고 {annual['amended']}건 미반영" if annual["amended"] else "")]
    if holdings:
        lines += table([("종목", 40, False), ("평가액 구간", 14, False), ("소유", 6, False)],
                       [[asset_label(h, 40), VALUE_WORDS.get(h["value"], bracket(h["value"])), h["owner"]]
                        for h in holdings[:top]])
        if len(holdings) > top:
            lines.append(f"... 외 {len(holdings) - top}건")
    else:
        lines.append(annual["error"] or
                     ("표시할 주식 없음" if annual.get("readable", True)
                      else "판독 불가(스캔 원문 등, 직접 확인)"))
    return [*lines, f"원문 {annual['url']}"]


def house_detail(report: dict, top: int) -> list[str]:
    trades = sorted(report["trades"], key=lambda t: t["date"], reverse=True)
    lines = [
        f"[하원] {report['name']} · {report['district']}",
        *annual_lines(report["annual"], top),
        f"PTR {report['filings']}건({report['span']}) · 최근 제출 {report['latest'] or '-'} · "
        f"최근 {len(report['read']) + len(report['unreadable']) + len(report['failed'])}건 읽음",
    ]
    if trades:
        lines += table([("거래일", 10, False), ("구분", 8, False), ("종목·자산", 26, False),
                        ("금액 구간", 12, False), ("소유", 6, False)],
                       [[t["date"], t["type"], asset_label(t, 26), bracket(t["amount"]), t["owner"]]
                        for t in trades[:top]])
    if len(trades) > top:
        lines.append(f"... 외 {len(trades) - top}건")
    for title, urls in (("원문", report["read"]), ("판독 불가(스캔 원문 등, 직접 확인)", report["unreadable"]),
                        ("조회 실패", report["failed"])):
        if urls:
            lines += [title, *(f"  {url}" for url in urls)]
    return lines


NOTES = {
    "13F": ["13F: 분기말 기준 신고(분기 후 45일 안). 13(f) 증권(미국 상장 주식·ETF·",
            "     옵션 등)만 담고 공매도·현금·비상장은 없다. 비중은 신고가치 합계 대비,",
            "     주식 수 변화는 분할 미보정이며 실제 매매를 뜻하지 않는다. 티커는",
            "     CUSIP을 OpenFIGI(2차 출처)로 맞춘 것이며 미확인 종목은 원문명이다."],
    "하원": ["PTR: 거래 신고(거래 후 45일 안)일 뿐 보유 전체가 아니다. 금액은 신고 구간",
            "     ($1K~$15K = $1,001~$15,000). 옵션 행사가·만기는 원문 설명에 있다.",
            "연간: 신고연도 말 자산과 평가액 구간(다음 해 5월 제출). 구간이라 비중은",
            "     계산하지 않으며, 수정 신고는 반영하지 않는다."],
}


def render(reports: list[dict], now: datetime, top: int) -> str:
    lines = [f"공시 스냅샷 · 조회 {now:%Y-%m-%d %H:%M %Z}", "",
             *table(OVERVIEW, [overview(r) for r in reports])]
    for report in reports:
        if "holdings" in report:
            lines += ["", *filer_detail(report, top)]
        elif "trades" in report:
            lines += ["", *house_detail(report, top)]
        elif report.get("candidates") and len(report["candidates"]) > 1:
            lines += ["", f"[{report['kind']}] '{report['query']}' 식별 모호, 하나를 골라 다시 실행",
                      *(f"  {c}" for c in report["candidates"])]
        elif "error" in report:
            lines += ["", f"[{report['kind']}] '{report['query']}'", fit("  " + report["error"], WIDTH)]
    lines += ["", "기준일: 13F는 보고기간 말, 하원은 최근 PTR 제출일."]
    for kind in dict.fromkeys(r["kind"] for r in reports):
        lines += NOTES[kind]
    return "\n".join(line.rstrip() for line in lines)


# Well-known 13F filers for --list. Each CIK was checked against EDGAR on
# 2026-11-19 for its name and a 13F-HR filed within the past year.
# ponytail: hand-kept list, re-check CIKs when a filer stops filing or renames.
FAMOUS = [
    ("워런 버핏", "Berkshire Hathaway", 1067983), ("빌 애크먼", "Pershing Square", 1336528),
    ("레이 달리오", "Bridgewater Associates", 1350694),
    ("스탠리 드러켄밀러", "Duquesne Family Office", 1536411),
    ("데이비드 테퍼", "Appaloosa", 1656456), ("세스 클라만", "Baupost Group", 1061768),
    ("대니얼 롭", "Third Point", 1040273), ("칼 아이칸", "Icahn (Carl C. Icahn)", 921669),
    ("조지 소로스", "Soros Fund Management", 1029160),
    ("짐 사이먼스", "Renaissance Technologies", 1037389),
    ("체이스 콜먼", "Tiger Global Management", 1167483),
    ("필리프 라퐁", "Coatue Management", 1135730), ("캐시 우드", "ARK Investment Mgmt", 1697748),
    ("리루", "Himalaya Capital", 1709323), ("모니시 파브라이", "Dalal Street", 1549575),
    ("빌 게이츠", "Gates Foundation Trust", 1166559), ("토머스 게이너", "Markel Group", 1096343),
    ("테리 스미스", "Fundsmith", 1569205), ("스티븐 맨델", "Lone Pine Capital", 1061165),
    ("안드레아스 할보르센", "Viking Global Investors", 1103804),
    ("폴 싱어", "Elliott Investment Mgmt", 1791786), ("켄 그리핀", "Citadel Advisors", 1423053),
    ("스티브 코언", "Point72 Asset Management", 1603466),
    ("척 에이크리", "Akre Capital Management", 1112520),
    ("하워드 막스", "Oaktree Capital Management", 949509),
    ("넬슨 펠츠", "Trian Fund Management", 1345471), ("메이슨 모핏", "ValueAct Holdings", 1418814),
    ("제프 스미스", "Starboard Value", 1517137), ("조엘 그린블랫", "Gotham Asset Management", 1510387),
    ("브루스 버코위츠", "Fairholme Capital", 1056831),
    ("돤융핑", "H&H International Investment", 1759760),
    ("크리스 혼", "TCI Fund Management", 1647251),
    ("기관", "BlackRock", 2012383), ("기관", "State Street", 93751), ("기관", "JPMorgan Chase", 19617),
    ("기관", "스위스 중앙은행", 1582202),
]


def catalog(index: list[dict] | None, error: str, top: int) -> str:
    numbered = list(enumerate(FAMOUS, 1))  # institutions keep their numbers after investors
    lines = ["13F 투자자 · 번호를 고르면 CIK로 조회", "",
             *table([("번호", 4, True), ("인물", 20, False), ("운용사", 30, False), ("CIK", 7, True)],
                    [[str(n), who, firm, str(cik)] for n, (who, firm, cik) in numbered if who != "기관"]),
             "", "13F 기관", "",
             *table([("번호", 4, True), ("기관", 53, False), ("CIK", 7, True)],
                    [[str(n), firm, str(cik)] for n, (who, firm, cik) in numbered if who == "기관"]),
             "", f"하원 PTR 신고 건수 상위 {top}명 · 유명도가 아니라 신고 활동 기준"]
    if index is None:
        return "\n".join([*lines, fit("  " + error, WIDTH).rstrip()])
    tally = Counter((f["Last"], f["StateDst"]) for f in index if f["FilingType"] == "P")
    names = {}  # one display name per member, though First varies between filings
    for f in index:
        names.setdefault((f["Last"], f["StateDst"]), f"{f['First']} {f['Last']}")
    start = len(FAMOUS)
    rows = [[str(start + n), names[key], key[1], str(count)]
            for n, (key, count) in enumerate(tally.most_common(top), 1)]
    years = sorted({f["Year"] for f in index})
    return "\n".join([*lines, f"(색인 {years[0]}~{years[-1]})",
                      *table([("번호", 4, True), ("의원", 41, False), ("지역구", 8, False),
                              ("PTR", 4, True)], rows)])


def _safely(kind: str, query: str, build) -> dict:
    try:
        return build()
    except Exception as exc:  # one target's failure must not hide the others
        return {"kind": kind, "query": query, "error": f"조회 실패 ({type(exc).__name__}: {exc})"}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="13F·하원 PTR 공시를 터미널 한 화면으로 요약한다.")
    parser.add_argument("--filer", nargs="+", default=[], metavar="CIK|이름",
                        help="13F 제출자 CIK 또는 운용사 이름")
    parser.add_argument("--house", nargs="+", default=[], metavar="이름",
                        help="하원의원 성 또는 '이름 성'")
    parser.add_argument("--top", type=int, default=10, help="대상별 표시 행 수(기본 10)")
    parser.add_argument("--ptrs", type=int, default=5, help="의원별로 읽을 최근 PTR 수(기본 5)")
    parser.add_argument("--list", action="store_true",
                        help="고를 수 있는 13F 제출자와 하원 PTR 상위 의원 목록")
    args = parser.parse_args(argv)
    if not (args.filer or args.house or args.list):
        parser.error("--filer, --house, --list 중 하나 이상을 지정하세요")
    now = datetime.now().astimezone()
    if args.list:
        try:
            index, error = [f for y in range(now.year - 2, now.year + 1) for f in house_filings(y)], ""
        except Exception as exc:
            index, error = None, f"하원 색인 조회 실패 ({type(exc).__name__}: {exc})"
        print(catalog(index, error, 15))
        return
    reports = [_safely("13F", q, lambda q=q: filer_report(q, args.top)) for q in args.filer]
    if args.house:
        index, missing = [], []
        # Annual reports for a year are filed the next May, so read three years of index.
        for year in range(now.year - 2, now.year + 1):
            try:
                index += house_filings(year)
            except Exception as exc:
                missing.append(f"{year} {type(exc).__name__}")
        if not index:
            reports += [{"kind": "하원", "query": q, "error": "하원 색인 조회 실패 (" + ", ".join(missing) + ")"}
                        for q in args.house]
        else:
            reports += [_safely("하원", q, lambda q=q: house_report(q, index, args.ptrs))
                        for q in args.house]
    print(render(reports, now, args.top))


if __name__ == "__main__":
    main()
