"""Private, prospective-only SEC 13F chart-zone sample refreshes.

CUSIPs and OpenFIGI response bodies are transient inputs. The private manifest
keeps CUSIP hashes, FIGIs, resolved Yahoo tickers, and source hashes only.
"""

from __future__ import annotations

import csv
import hashlib
import html.parser
import io
import json
import os
import re
import sqlite3
import tempfile
import time
import zipfile
from collections import defaultdict
from contextlib import suppress
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import requests

from tradingagents.dataflows.files import replace_file
from tradingagents.dataflows.vendors.sec_edgar import _user_agent

SEC_13F_INDEX_URL = "https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets"
OPENFIGI_MAPPING_URL = "https://api.openfigi.com/v3/mapping"
MAPPING_VERSION = "openfigi-cusip-us-common-stock-v1"
MAX_CUSIPS_TO_MAP = 100
MAX_SEC_TICKERS = 10
_CUSIP_RE = re.compile(r"^[A-Z0-9]{9}$")
_ZIP_LINK_RE = re.compile(
    r"(?P<start>\d{2}[a-z]{3}\d{4})-(?P<end>\d{2}[a-z]{3}\d{4})_form13f\.zip$",
    re.IGNORECASE,
)


class Sec13FSourceError(RuntimeError):
    """A SEC or mapping source could not be used safely."""


class _LinkParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href and _ZIP_LINK_RE.search(href):
            self.links.append(href)


def _latest_dataset_url(html: str) -> str:
    parser = _LinkParser()
    parser.feed(html)
    candidates = []
    for link in parser.links:
        match = _ZIP_LINK_RE.search(link)
        if not match:
            continue
        end = datetime.strptime(match.group("end").upper(), "%d%b%Y").date()
        candidates.append((end, link))
    if not candidates:
        raise Sec13FSourceError("SEC 13F dataset index contains no ZIP link.")
    url = max(candidates)[1]
    return url if url.startswith("https://") else "https://www.sec.gov" + url


def _private_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)
    return path


def _download_dataset(url: str, cache_root: Path) -> tuple[Path, str, int]:
    cache_root = _private_directory(cache_root)
    temporary: Path | None = None
    try:
        with requests.get(url, headers={"User-Agent": _user_agent()}, stream=True,
                          timeout=(15, 90)) as response:
            if response.status_code != 200:
                raise Sec13FSourceError(f"SEC 13F ZIP request failed ({response.status_code}).")
            content_type = response.headers.get("Content-Type", "").lower()
            if "application/octet-stream" not in content_type and "application/zip" not in content_type:
                raise Sec13FSourceError("SEC 13F ZIP returned an unexpected content type.")
            length = response.headers.get("Content-Length")
            if length and int(length) > 512 * 1024 * 1024:
                raise Sec13FSourceError("SEC 13F ZIP exceeded the private cache size limit.")
            fd, name = tempfile.mkstemp(prefix=".13f-", suffix=".zip.tmp", dir=cache_root)
            temporary = Path(name)
            os.fchmod(fd, 0o600)
            digest = hashlib.sha256()
            first = b""
            total = 0
            with os.fdopen(fd, "wb") as output:
                for chunk in response.iter_content(1024 * 1024):
                    if not chunk:
                        continue
                    if len(first) < 4:
                        first += chunk[:4 - len(first)]
                    total += len(chunk)
                    if total > 512 * 1024 * 1024:
                        raise Sec13FSourceError("SEC 13F ZIP exceeded the private cache size limit.")
                    digest.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            if not first.startswith(b"PK\x03\x04"):
                raise Sec13FSourceError("SEC 13F response is not a ZIP archive.")
            sha256 = digest.hexdigest()
            destination = cache_root / f"{sha256}.zip"
            if destination.exists():
                temporary.unlink(missing_ok=True)
            else:
                os.replace(temporary, destination)
                os.chmod(destination, 0o600)
            return destination, sha256, total
    except requests.RequestException as exc:
        raise Sec13FSourceError(f"SEC 13F download failed ({type(exc).__name__}).") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _table_members(archive: zipfile.ZipFile) -> dict[str, str]:
    wanted = {"submission", "coverpage", "infotable"}
    members: dict[str, str] = {}
    for name in archive.namelist():
        path = Path(name)
        if path.suffix.lower() != ".tsv":
            continue
        stem = path.stem.lower()
        if stem in wanted:
            members[stem] = name
    missing = wanted - set(members)
    if missing:
        raise Sec13FSourceError("SEC 13F ZIP is missing a required table.")
    return members


def _rows(archive: zipfile.ZipFile, member: str):
    with archive.open(member) as binary:
        text = io.TextIOWrapper(binary, encoding="utf-8-sig", newline="")
        reader = csv.DictReader(text, delimiter="\t")
        for row in reader:
            yield {str(key).strip().upper(): (value or "").strip()
                   for key, value in row.items() if key is not None}


def _sec_date(value: str) -> date:
    for fmt in ("%d-%b-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip().upper(), fmt).date()
        except ValueError:
            pass
    raise ValueError("invalid SEC filing date")


def _accepted_order(row: dict) -> tuple[date, str]:
    try:
        filed = _sec_date(row.get("FILING_DATE", ""))
    except ValueError:
        filed = date.min
    return filed, row.get("ACCESSION_NUMBER", "")


def _parse_value_thousands(value: str) -> int | None:
    try:
        parsed = int(value.strip())
    except (ValueError, AttributeError):
        return None
    return parsed if parsed > 0 else None


def parse_13f_dataset(path: Path) -> dict:
    """Aggregate the latest 13F report period, applying amendments conservatively."""
    with zipfile.ZipFile(path) as archive:
        members = _table_members(archive)
        submissions = [row for row in _rows(archive, members["submission"])
                       if row.get("SUBMISSIONTYPE", "").upper() in {"13F-HR", "13F-HR/A"}]
        if not submissions:
            raise Sec13FSourceError("SEC 13F ZIP has no holdings reports.")
        period_by_accession = {}
        for row in submissions:
            try:
                period_by_accession[row["ACCESSION_NUMBER"]] = _sec_date(row["PERIODOFREPORT"])
            except (KeyError, ValueError):
                continue
        if not period_by_accession:
            raise Sec13FSourceError("SEC 13F ZIP has no usable report periods.")
        latest_period = max(period_by_accession.values())
        submissions = [row for row in submissions
                       if period_by_accession.get(row.get("ACCESSION_NUMBER")) == latest_period]
        covers = {row.get("ACCESSION_NUMBER", ""): row for row in _rows(archive, members["coverpage"])}
        by_filer: dict[str, list[dict]] = defaultdict(list)
        actions: dict[str, str] = {}
        ambiguous_ciks: set[str] = set()
        for row in submissions:
            accession = row.get("ACCESSION_NUMBER", "")
            cik = row.get("CIK", "").strip().zfill(10)
            if not accession or not cik.isdigit():
                continue
            cover = covers.get(accession, {})
            form = row.get("SUBMISSIONTYPE", "").upper()
            if form == "13F-HR":
                action = "replace"
            else:
                amendment_type = re.sub(r"\s+", " ", cover.get("AMENDMENTTYPE", "").upper()).strip()
                if amendment_type == "RESTATEMENT":
                    action = "replace"
                elif amendment_type in {"NEW HOLDINGS ENTRIES", "NEW HOLDING ENTRIES"}:
                    action = "add"
                else:
                    ambiguous_ciks.add(cik)
                    continue
            actions[accession] = action
            by_filer[cik].append(row)

        active_accessions = set(actions)
        db_path: Path | None = None
        connection: sqlite3.Connection | None = None
        try:
            fd, name = tempfile.mkstemp(prefix=".13f-positions-", suffix=".sqlite", dir=path.parent)
            os.fchmod(fd, 0o600)
            os.close(fd)
            db_path = Path(name)
            connection = sqlite3.connect(db_path)
            connection.execute("CREATE TABLE positions(accession TEXT, cusip TEXT, value_k INTEGER)")
            connection.execute("CREATE INDEX positions_accession ON positions(accession, cusip)")
            excluded = {"options": 0, "principal_amount": 0, "invalid_cusip": 0, "invalid_value": 0}
            pending = []
            for row in _rows(archive, members["infotable"]):
                accession = row.get("ACCESSION_NUMBER", "")
                if accession not in active_accessions:
                    continue
                if row.get("PUTCALL", "").strip():
                    excluded["options"] += 1
                    continue
                if row.get("SSHPRNAMTTYPE", "").upper() != "SH":
                    excluded["principal_amount"] += 1
                    continue
                cusip = row.get("CUSIP", "").upper()
                if not _CUSIP_RE.fullmatch(cusip):
                    excluded["invalid_cusip"] += 1
                    continue
                value = _parse_value_thousands(row.get("VALUE", ""))
                if value is None:
                    excluded["invalid_value"] += 1
                    continue
                pending.append((accession, cusip, value))
                if len(pending) >= 10_000:
                    connection.executemany("INSERT INTO positions VALUES (?, ?, ?)", pending)
                    pending.clear()
            if pending:
                connection.executemany("INSERT INTO positions VALUES (?, ?, ?)", pending)
            connection.commit()

            aggregate: dict[str, dict] = {}
            ambiguous_ciks.update(cik for cik, filings in by_filer.items()
                                  if not any(row.get("SUBMISSIONTYPE", "").upper() == "13F-HR" for row in filings))
            for cik, filings in by_filer.items():
                if cik in ambiguous_ciks:
                    continue
                current: dict[str, int] = {}
                for filing in sorted(filings, key=_accepted_order):
                    accession = filing["ACCESSION_NUMBER"]
                    rows = connection.execute(
                        "SELECT cusip, SUM(value_k) FROM positions WHERE accession=? GROUP BY cusip",
                        (accession,),
                    )
                    accession_values = {cusip: int(value) for cusip, value in rows}
                    if actions[accession] == "replace":
                        current = accession_values
                    else:
                        for cusip, value in accession_values.items():
                            current[cusip] = current.get(cusip, 0) + value
                for cusip, value in current.items():
                    target = aggregate.setdefault(cusip, {"value_thousands": 0, "filers": set()})
                    target["value_thousands"] += value
                    target["filers"].add(cik)
        finally:
            if connection is not None:
                connection.close()
            if db_path is not None:
                db_path.unlink(missing_ok=True)

    candidates = []
    for cusip, item in aggregate.items():
        candidates.append({"cusip": cusip,
                           "value_thousands": item["value_thousands"],
                           "reporting_filers": len(item["filers"])})
    candidates.sort(key=lambda item: (-item["value_thousands"],
                                      hashlib.sha256(item["cusip"].encode()).hexdigest()))
    return {
        "report_period": latest_period.isoformat(),
        "filer_count": len(by_filer),
        "ambiguous_filer_count": len(ambiguous_ciks),
        "excluded_rows": excluded,
        "total_candidate_cusips": len(candidates),
        "candidates": candidates[:MAX_CUSIPS_TO_MAP],
    }


def _map_batch(cusips: list[str]) -> list[dict]:
    response = requests.post(
        OPENFIGI_MAPPING_URL,
        json=[{"idType": "ID_CUSIP", "idValue": cusip, "exchCode": "US"} for cusip in cusips],
        headers={"Content-Type": "application/json"},
        timeout=(15, 45),
    )
    if response.status_code != 200:
        raise Sec13FSourceError(f"OpenFIGI mapping failed ({response.status_code}).")
    if "json" not in response.headers.get("Content-Type", "").lower():
        raise Sec13FSourceError("OpenFIGI mapping returned a non-JSON response.")
    try:
        results = response.json()
    except ValueError:
        raise Sec13FSourceError("OpenFIGI mapping returned unreadable JSON.") from None
    if not isinstance(results, list) or len(results) != len(cusips):
        raise Sec13FSourceError("OpenFIGI mapping result count did not match the request.")
    output = []
    for item in results:
        if not isinstance(item, dict):
            output.append({"status": "unmapped"})
            continue
        rows = item.get("data")
        if not isinstance(rows, list) or not rows:
            output.append({"status": "unmapped"})
            continue
        if len(rows) != 1 or not isinstance(rows[0], dict):
            output.append({"status": "ambiguous"})
            continue
        row = rows[0]
        if row.get("marketSector") != "Equity" or row.get("securityType") != "Common Stock":
            output.append({"status": "ambiguous_security_type"})
            continue
        ticker, figi = row.get("ticker"), row.get("figi")
        if not isinstance(ticker, str) or not ticker or not isinstance(figi, str) or not figi:
            output.append({"status": "unmapped"})
            continue
        output.append({"status": "mapped", "ticker": ticker.strip().upper(), "figi": figi})
    return output


def map_cusips(cusips: list[str], *, sleep=time.sleep) -> list[dict]:
    """Map at most 100 CUSIPs, respecting the unauthenticated OpenFIGI quota."""
    result = []
    for offset in range(0, len(cusips), 10):
        if offset:
            sleep(2.5)
        result.extend(_map_batch(cusips[offset:offset + 10]))
    return result


def _mapping_payload(parsed: dict, mapping: list[dict], dataset_sha256: str) -> dict:
    candidates = parsed["candidates"]
    ticker_totals: dict[str, dict] = {}
    audit = []
    canonical_mapping = []
    for candidate, item in zip(candidates, mapping, strict=True):
        cusip_hash = hashlib.sha256(candidate["cusip"].encode()).hexdigest()
        status = item.get("status", "unmapped")
        entry = {"cusip_sha256": cusip_hash, "status": status}
        canonical_mapping.append(entry | {k: item[k] for k in ("ticker", "figi") if k in item})
        if status == "mapped":
            ticker = item["ticker"]
            target = ticker_totals.setdefault(ticker, {
                "ticker": ticker, "reported_value_usd": 0, "reporting_filers": set(),
                "cusip_sha256": [], "figis": [],
            })
            target["reported_value_usd"] += int(candidate["value_thousands"]) * 1000
            target["reporting_filers"].add((cusip_hash, int(candidate["reporting_filers"])))
            target["cusip_sha256"].append(cusip_hash)
            target["figis"].append(item["figi"])
            entry.update({"ticker": ticker, "figi": item["figi"]})
        audit.append(entry)
    ranked = []
    for ticker, item in ticker_totals.items():
        ranked.append({"ticker": ticker, "reported_value_usd": item["reported_value_usd"],
                       "cusip_sha256": sorted(item["cusip_sha256"]),
                       "figis": sorted(set(item["figis"])),
                       "source_cusip_count": len(item["cusip_sha256"]),
                       "reporting_filer_cusip_observations": sum(
                           value for _, value in item["reporting_filers"]
                       )})
    ranked.sort(key=lambda item: (-item["reported_value_usd"], item["ticker"]))
    selected = ranked[:MAX_SEC_TICKERS]
    mapping_canonical = json.dumps(canonical_mapping, sort_keys=True, separators=(",", ":"))
    return {
        "schema_version": 1,
        "cohort_id": "sec_13f",
        "mapping_version": MAPPING_VERSION,
        "dataset_sha256": dataset_sha256,
        "mapping_result_sha256": hashlib.sha256(mapping_canonical.encode()).hexdigest(),
        "report_period": parsed["report_period"],
        "selection_policy": "latest-report-period/top-100-cusip-value/top-10-common-stock-ticker-v1",
        "bias_flags": [
            "13f_reporting_population_only",
            "shared_discretion_may_double_count_reported_value",
            "quarterly_report_delay",
            "cusip_mapping_observed_at_not_historical",
        ],
        "tickers": [item["ticker"] for item in selected],
        "ticker_metrics": selected,
        "mapping_audit": audit,
        "quality": {
            "filer_count": parsed["filer_count"],
            "ambiguous_filer_count": parsed["ambiguous_filer_count"],
            "source_candidate_cusips": parsed["total_candidate_cusips"],
            "mapped_candidate_cusips": sum(item.get("status") == "mapped" for item in audit),
            "ambiguous_candidate_cusips": sum(item.get("status") == "ambiguous" for item in audit),
            "unmapped_candidate_cusips": sum(item.get("status") == "unmapped" for item in audit),
            "ambiguous_security_type_count": sum(item.get("status") == "ambiguous_security_type" for item in audit),
            "candidate_cap": MAX_CUSIPS_TO_MAP,
            "candidate_truncated_count": max(0, parsed["total_candidate_cusips"] - len(candidates)),
            "excluded_rows": parsed["excluded_rows"],
            "status": "ready" if len(selected) >= MAX_SEC_TICKERS else "inconclusive",
        },
    }


def _write_sample(manifest: dict, *, root: Path, dataset_observed_at: str,
                  mapping_observed_at: str, retrieved_at: str) -> dict:
    payload = dict(manifest)
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    sample_id = f"sec13f-{digest[:12]}"
    root = _private_directory(root)
    path = root / f"{sample_id}.json"
    encoded = json.dumps({**payload, "sample_id": sample_id, "sha256": digest},
                         ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != encoded:
            raise ValueError("SEC 13F sample hash collision.")
    else:
        replace_file(path, lambda temporary: Path(temporary).write_text(encoded, encoding="utf-8"))
    os.chmod(path, 0o600)
    pointer_path = root / "sec_latest.json"
    previous = None
    with suppress(OSError, json.JSONDecodeError):
        previous = json.loads(pointer_path.read_text(encoding="utf-8"))
    if previous and previous.get("sample_id") == sample_id:
        dataset_observed_at = previous["dataset_observed_at"]
        mapping_observed_at = previous["mapping_observed_at"]
        eligible_from = previous["eligible_from"]
    else:
        source_times = [datetime.fromisoformat(value.replace("Z", "+00:00"))
                        for value in (dataset_observed_at, mapping_observed_at)]
        eligible_from = next_xnys_session(max(source_times)).isoformat()
    pointer = {
        "sample_id": sample_id,
        "sha256": digest,
        "dataset_sha256": payload["dataset_sha256"],
        "dataset_observed_at": dataset_observed_at,
        "mapping_observed_at": mapping_observed_at,
        "eligible_from": eligible_from,
        "retrieved_at": retrieved_at,
    }
    pointer_encoded = json.dumps(pointer, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    replace_file(pointer_path, lambda temporary: Path(temporary).write_text(pointer_encoded, encoding="utf-8"))
    os.chmod(pointer_path, 0o600)
    return {**payload, "sample_id": sample_id, "sha256": digest,
            "path": str(path), "eligible_from": eligible_from}


def next_xnys_session(timestamp: datetime) -> date:
    """Return the first XNYS session strictly after a known observation date."""
    if timestamp.tzinfo is None:
        raise ValueError("observation timestamp must be timezone-aware")
    local_day = timestamp.astimezone(ZoneInfo("America/New_York")).date()
    sessions = xcals.get_calendar("XNYS").sessions_in_range(
        local_day + timedelta(days=1), local_day + timedelta(days=31)
    )
    if sessions.empty:
        raise ValueError("No XNYS session found after SEC observation.")
    return sessions[0].date()


def load_current_sec_sample(root: Path) -> tuple[dict, dict] | None:
    pointer_path = root / "sec_latest.json"
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        path = root / f"{pointer['sample_id']}.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, KeyError, json.JSONDecodeError):
        return None
    if manifest.get("sha256") != pointer.get("sha256") or manifest.get("sample_id") != pointer.get("sample_id"):
        raise ValueError("SEC 13F sample pointer does not match its immutable manifest.")
    return pointer, manifest


def refresh_sec_sample(root: Path) -> dict:
    """Download and map the current SEC 13F dataset; never calls Yahoo or Toss."""
    with requests.get(SEC_13F_INDEX_URL, headers={"User-Agent": _user_agent()}, timeout=(15, 60)) as response:
        if response.status_code != 200:
            raise Sec13FSourceError(f"SEC 13F index request failed ({response.status_code}).")
        if "text/html" not in response.headers.get("Content-Type", "").lower():
            raise Sec13FSourceError("SEC 13F index returned an unexpected content type.")
        dataset_url = _latest_dataset_url(response.text)
    cache_root = root / "sec_inputs"
    dataset_path, dataset_sha256, _size = _download_dataset(dataset_url, cache_root)
    dataset_observed_at = datetime.now(UTC).isoformat()
    parsed = parse_13f_dataset(dataset_path)
    candidates = parsed["candidates"]
    mappings = map_cusips([item["cusip"] for item in candidates])
    mapping_observed_at = datetime.now(UTC).isoformat()
    payload = _mapping_payload(parsed, mappings, dataset_sha256)
    retrieved_at = datetime.now(UTC).isoformat()
    return _write_sample(payload, root=root, dataset_observed_at=dataset_observed_at,
                         mapping_observed_at=mapping_observed_at, retrieved_at=retrieved_at)
