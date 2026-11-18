"""Form 13F holdings and House trade reports, side by side in a terminal.

Reads official sources only: SEC EDGAR for Form 13F and the House Clerk for
Periodic Transaction Reports (PTR). Senators are out of scope; the Senate eFD
answers 403 to any client that is not a browser.

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

from tradingagents.dataflows.net import get_with_retry
from tradingagents.dataflows.vendors import sec_edgar

WIDTH = 78  # an 80-column terminal, inside the fenced block the agent prints
SEC = "https://www.sec.gov"
HOUSE = "https://disclosures-clerk.house.gov/public_disc"


# --- Form 13F ---------------------------------------------------------------

def sec_text(url: str) -> str:
    sec_edgar._wait_for_request_slot()
    return get_with_retry(url, timeout=60, provider="SEC EDGAR",
                          headers={"User-Agent": sec_edgar._user_agent()}).text


def submissions(cik: int) -> dict:
    return sec_edgar._fetch_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")


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
        held["label"] = " ".join(filter(None, (
            held["name"], held["title"] if names[held["name"], key[1]] > 1 else "", key[1])))
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


def filer_report(query: str) -> dict:
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
    gone = sorted(((h["name"] + (f" {k[1]}" if k[1] else ""), h["value"])
                   for k, h in (before or {}).items() if k not in now), key=lambda g: -g[1])
    total = sum(h["value"] for h in now.values())
    for held in now.values():
        held["weight"] = held["value"] / total if total else 0.0
    return {"kind": "13F", "name": subs["name"], "cik": cik, "period": periods[0][0],
            "prior": periods[1][0] if len(periods) > 1 else None, "total": total,
            "holdings": sorted(now.values(), key=lambda h: -h["value"]),
            "counts": counts, "gone": gone, **info}


# --- House PTR ----------------------------------------------------------------

TRADES = {"P": "매수", "S": "매도", "S (partial)": "일부매도", "E": "교환"}
OWNERS = {"SP": "배우자", "JT": "공동", "DC": "자녀"}
DATE = re.compile(r"\d{2}/\d{2}/\d{4}")
AMOUNT = re.compile(r"\$[\d,]+ - \$[\d,]+|(?:Spouse/DC )?Over \$[\d,]+")


def house_filings(year: int) -> list[dict]:
    """The year's PTR filings from the Clerk's yearly index."""
    raw = get_with_retry(f"{HOUSE}/financial-pdfs/{year}FD.zip", timeout=60,
                         provider="House Clerk").content
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        root = ET.fromstring(archive.read(f"{year}FD.xml"))
    fields = ("Prefix", "First", "Last", "StateDst", "FilingDate", "DocID", "Year")
    return [{f: (member.findtext(f) or "").strip() for f in fields}
            for member in root.iter("Member") if member.findtext("FilingType") == "P"]


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

    pages = []
    for number, body in objects.items():
        content = stream(number)
        if "BT" not in content:
            continue
        fonts = {}
        for table in re.findall(rb"/Font\s*<<(.*?)>>", body, re.S):
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


def ptr_rows(pages: list[list[tuple[float, str]]]) -> list[dict]:
    """Transactions from PTR text lines.

    A row starts where a transaction type is followed by two dates. Its owner and
    asset cells start on that line and wrap below it, so they are the lines drawn
    just before the type at or below its height.
    """
    rows = []
    for lines in pages:
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
                "amount": after[2] if AMOUNT.fullmatch(after[2]) else " ".join(after[2:4]),
            })
    return rows


def house_report(query: str, index: list[dict], ptrs: int) -> dict:
    words = set(query.casefold().split())
    hits = [f for f in index
            if words <= set(f"{f['First']} {f['Last']}".casefold().replace(",", " ").split())]
    members = {(f["First"], f["Last"]) for f in hits}
    if len(members) != 1:
        return {"kind": "하원", "query": query,
                "candidates": sorted(f"{first} {last}" for first, last in members)}
    hits.sort(key=lambda f: datetime.strptime(f["FilingDate"], "%m/%d/%Y"), reverse=True)
    latest, years = hits[0], sorted({f["Year"] for f in index})
    report = {"kind": "하원", "name": f"{latest['First']} {latest['Last']}",
              "district": latest["StateDst"], "latest": _iso(latest["FilingDate"]),
              "filings": len(hits), "span": f"{years[0]}~{years[-1]}",
              "trades": [], "read": [], "unreadable": [], "failed": []}
    for filing in hits[:ptrs]:
        url = f"{HOUSE}/ptr-pdfs/{filing['Year']}/{filing['DocID']}.pdf"
        try:
            rows = ptr_rows(pdf_lines(get_with_retry(url, timeout=60, provider="House Clerk").content))
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


def bar(share: float, cells: int = 12) -> str:
    eighths = round(share * cells * 8)
    return "█" * (eighths // 8) + ("", "▏", "▎", "▍", "▌", "▋", "▊", "▉")[eighths % 8]


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


def overview(report: dict) -> str:
    head = fit(report["kind"], 4) + " "
    if "holdings" in report:
        counts = report["counts"]
        line = (f"{head}{fit(report['name'], 24)} {report['period']} "
                f"{fit(usd(report['total']), 7, True)} ")
        tail = ("비교 불가" if counts is None else
                " ".join(f"{k}{v}" for k, v in counts.items() if v and k != "유지") or "변화 없음")
    elif "trades" in report:
        tally = Counter(t["type"] for t in report["trades"])
        line = (f"{head}{fit(report['name'] + ' ' + report['district'], 24)} {report['latest']} "
                f"{fit(str(len(report['trades'])) + '건', 7, True)} ")
        tail = " ".join([*(f"{k}{tally[k]}" for k in TRADES.values() if tally[k]),
                         *(f"판독불가{n}" for n in [len(report["unreadable"])] if n),
                         *(f"실패{n}" for n in [len(report["failed"])] if n)])
    else:
        line, tail = f"{head}{fit(report['query'], 24)} ", status(report)
    return line + fit(tail, WIDTH - cols(line))


def listing(label: str, items: list[str], limit: int = 5) -> list[str]:
    if len(items) > limit:
        items = [*items[:limit], f"외 {len(items) - limit}개"]
    return [fit(label if n == 0 else "", 8) + fit(item, WIDTH - 8) for n, item in enumerate(items)]


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
    lines.append(f"{fit('#', 3, True)}  {fit('종목', 26)} {fit('가치', 7, True)} "
                 f"{fit('비중', 6, True)} {fit('주식 수', 7, True)}")
    biggest = shown[0]["weight"] if shown and shown[0]["weight"] else 1.0
    for n, held in enumerate(shown, 1):
        lines.append(f"{n:>3}  {fit(held['label'], 26)} {fit(usd(held['value']), 7, True)} "
                     f"{held['weight']:>6.1%} {fit(share_change(held), 7, True)}  "
                     f"{bar(held['weight'] / biggest)}")
    lines += listing("신규", [f"{h['label']} {usd(h['value'])}" for h in holdings
                              if h["status"] == "신규"])
    lines += listing("미보고", [f"{label} (직전 {usd(value)})" for label, value in report["gone"]])
    return [*lines, f"원문 {report['url']}"]


def asset_label(trade: dict) -> str:
    label = trade["ticker"] or trade["asset"]
    if trade["kind"] == "OP":
        return f"{label} 옵션"
    return f"{label} [{trade['kind']}]" if trade["kind"] not in ("ST", "") else label


def house_detail(report: dict, top: int) -> list[str]:
    trades = sorted(report["trades"], key=lambda t: t["date"], reverse=True)
    lines = [
        f"[하원] {report['name']} · {report['district']}",
        f"PTR {report['filings']}건({report['span']}) · 최근 제출 {report['latest']} · "
        f"최근 {len(report['read']) + len(report['unreadable']) + len(report['failed'])}건 읽음",
    ]
    if trades:
        lines.append(f"{fit('거래일', 10)}  {fit('구분', 8)}  {fit('종목·자산', 22)}  "
                     f"{fit('금액 구간', 12)}  소유")
    lines += [f"{t['date']}  {fit(t['type'], 8)}  {fit(asset_label(t), 22)}  "
              f"{fit(bracket(t['amount']), 12)}  {t['owner']}" for t in trades[:top]]
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
            "     주식 수 변화는 분할 미보정이며 실제 매매를 뜻하지 않는다."],
    "하원": ["PTR: 거래 신고(거래 후 45일 안)일 뿐 보유 전체가 아니다. 금액은 신고 구간",
            "     ($1K~$15K = $1,001~$15,000). 옵션 행사가·만기는 원문 설명에 있다."],
}


def render(reports: list[dict], now: datetime, top: int) -> str:
    lines = [f"공시 스냅샷 · 조회 {now:%Y-%m-%d %H:%M %Z}", "",
             f"{fit('구분', 4)} {fit('대상', 24)} {fit('기준일', 10)} {fit('규모', 7, True)} 변화·거래",
             *map(overview, reports)]
    for report in reports:
        if "holdings" in report:
            lines += ["", *filer_detail(report, top)]
        elif "trades" in report:
            lines += ["", *house_detail(report, top)]
        elif report.get("candidates") and len(report["candidates"]) > 1:
            lines += ["", f"[{report['kind']}] '{report['query']}' 식별 모호, 하나를 골라 다시 실행",
                      *(f"  {c}" for c in report["candidates"])]
    lines += ["", "기준일: 13F는 보고기간 말, 하원은 최근 PTR 제출일."]
    for kind in dict.fromkeys(r["kind"] for r in reports):
        lines += NOTES[kind]
    return "\n".join(line.rstrip() for line in lines)


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
    args = parser.parse_args(argv)
    if not (args.filer or args.house):
        parser.error("--filer, --house 중 하나 이상을 지정하세요")
    now = datetime.now().astimezone()
    reports = [_safely("13F", q, lambda q=q: filer_report(q)) for q in args.filer]
    if args.house:
        index, missing = [], []
        for year in (now.year - 1, now.year):  # last year too, so January still has history
            try:
                index += house_filings(year)
            except Exception as exc:
                missing.append(f"{year} {type(exc).__name__}")
        if len(missing) == 2:
            reports += [{"kind": "하원", "query": q, "error": "PTR 색인 조회 실패 (" + ", ".join(missing) + ")"}
                        for q in args.house]
        else:
            reports += [_safely("하원", q, lambda q=q: house_report(q, index, args.ptrs))
                        for q in args.house]
    print(render(reports, now, args.top))


if __name__ == "__main__":
    main()
