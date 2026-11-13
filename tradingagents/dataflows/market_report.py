"""Free public inputs for market reports; no broker access or model calls."""
from __future__ import annotations

import re
from datetime import UTC, datetime, time, timedelta
from html.parser import HTMLParser
from urllib.parse import quote
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from tradingagents.dataflows.net import get_with_retry
from tradingagents.dataflows.vendors import fred, sec_edgar
from tradingagents.dataflows.vendors.yahoo.news import _extract_article_data
from tradingagents.stock_discovery import fetch_index_universe, fetch_spy_holdings_universe

INDICES = {'^GSPC': 'S&P 500', '^IXIC': 'Nasdaq Composite', '^DJI': 'Dow Jones', '^RUT': 'Russell 2000', '^VIX': 'VIX'}
SECTORS = dict(zip(('XLC', 'XLY', 'XLP', 'XLE', 'XLF', 'XLV', 'XLI', 'XLB', 'XLRE', 'XLK', 'XLU'),
                   ('커뮤니케이션', '경기소비재', '필수소비재', '에너지', '금융', '헬스케어', '산업재', '소재', '부동산', '정보기술', '유틸리티'), strict=True))
MARKETS = {'DX-Y.NYB': ('미 달러 지수', '지수'), 'CL=F': ('WTI 연속 선물', 'USD/배럴'), 'GC=F': ('금 연속 선물', 'USD/트로이온스')}
FUTURES = {'ES=F': 'S&P 500 선물', 'NQ=F': 'Nasdaq 100 선물', 'YM=F': 'Dow 선물', 'RTY=F': 'Russell 2000 선물'}
COMPANIES = ('AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA')
MACRO = {'FEDFUNDS': '정책금리(실효 연방기금 월평균)', 'DGS2': '2년 국채금리', 'DGS10': '10년 국채금리', 'T10Y2Y': '10년–2년 금리차', 'CPIAUCSL': '소비자물가 수준', 'PCEPILFE': '근원 PCE 물가 수준', 'UNRATE': '실업률', 'PAYEMS': '비농업 고용 수준', 'GDPC1': '실질 GDP 수준', 'DTWEXBGS': '무역가중 미 달러 지수(광의, 명목)'}
BEA_RELEASES_URL = 'https://apps.bea.gov/API/signup/release_dates.json'
BEA_SCHEDULE_URL = 'https://www.bea.gov/news/schedule/full'
CENSUS_CALENDAR_URL = 'https://www.census.gov/economic-indicators/calendar-listview-{year}.html'
BLS_CALENDAR_URL = 'https://www.bls.gov/schedule/news_release/bls.ics'
FRED_US_RELEASES = frozenset({
    'consumer price index', 'employment situation', 'employment cost index',
    'job openings and labor turnover survey', 'producer price index',
    'gross domestic product', 'personal income and outlays',
    'advance monthly sales for retail and food services',
    'industrial production and capacity utilization', 'new residential construction',
    'new home sales', 'durable goods', 'u.s. international trade in goods and services',
    'unemployment insurance weekly claims report',
    # 'FOMC Press Release' (FRED release 101) is dated every day for the daily target-range
    # series, so it is not an event; FOMC decisions come from the Fed calendar.
    'state unemployment insurance weekly claims report',
    'fomc meeting minutes', 'beige book', 'monthly treasury statement',
})
CENSUS_US_RELEASES = frozenset({
    'advance monthly retail trade', 'advance monthly sales for retail and food services',
    'new residential construction', 'new residential sales',
    'advance report on durable goods', 'u.s. international trade in goods and services',
})
CENSUS_FRED_ALIASES = {
    'advance monthly retail trade': 'advance monthly sales for retail and food services',
    'new residential sales': 'new home sales',
    'advance report on durable goods': 'durable goods',
}
BEA_US_RELEASES = frozenset({
    'gross domestic product', 'personal income and outlays',
    'u.s. international trade in goods and services', 'u.s. international transactions',
    'u.s. international investment position',
    'gross domestic product by state and personal income by state',
})
BLS_US_RELEASES = frozenset({
    'consumer price index', 'employment situation', 'producer price index',
    'job openings and labor turnover survey', 'employment cost index', 'real earnings',
    'u.s. import and export price indexes', 'productivity and costs',
})
ET = ZoneInfo('America/New_York')


def quote_url(symbol):
    return f'https://finance.yahoo.com/quote/{quote(symbol, safe="")}/'


class PublicDataError(ValueError):
    def __init__(self, category):
        self.category = category
        super().__init__(category)


def error_reason(exc):
    category = exc.category if isinstance(exc, PublicDataError) else type(exc).__name__
    if category == 'FredNotConfiguredError':
        return 'FRED_API_KEY 미설정 (무료 키 필요)'
    return category


def release_key(name):
    """Normalize official calendar titles to the matching FRED release name."""
    normalized = ' '.join(str(name).split()).casefold()
    if normalized.startswith('advance report on durable goods'):
        return 'durable goods'
    return CENSUS_FRED_ALIASES.get(normalized, normalized)


class PublicMarketData:
    """One instance per report: each endpoint/key, including failures, is fetched once."""

    def __init__(self):
        self._results = {}
        self.retrieved = {}
        self._tickers = {}

    def _once(self, key, fetch):
        if key not in self._results:
            try:
                self._results[key] = (fetch(), None)
            except Exception as exc:
                # Never retain exception text, request URLs with keys, or raw responses.
                self._results[key] = (None, type(exc).__name__)
            self.retrieved[key] = datetime.now(UTC).isoformat()
        value, error = self._results[key]
        if error:
            raise PublicDataError(error)
        return value

    def ticker(self, symbol):
        if symbol not in self._tickers:
            yahoo_symbol = symbol.replace('.', '-') if re.fullmatch(r'[A-Z]+\.[A-Z]', symbol) else symbol
            self._tickers[symbol] = yf.Ticker(yahoo_symbol)
        return self._tickers[symbol]

    def daily(self, symbol, day):
        return self._once(('daily', symbol, day), lambda: self.ticker(symbol).history(
            start=day - timedelta(days=430), end=day + timedelta(days=1),
            auto_adjust=False, actions=True, raise_errors=True, timeout=15))

    def intraday(self, symbol, day):
        return self._once(('intraday', symbol, day), lambda: self.ticker(symbol).history(
            start=day, end=day + timedelta(days=1), interval='5m', prepost=True,
            auto_adjust=False, actions=False, raise_errors=True, timeout=15))

    def universe(self):
        def fetch():
            try:
                return fetch_spy_holdings_universe()
            except Exception:
                return fetch_index_universe('sp500')
        return self._once(('universe',), fetch)

    def news(self, symbol):
        return self._once(('news', symbol), lambda: [
            _extract_article_data(a) for a in self.ticker(symbol).get_news(count=12) or []])

    def macro(self, series, day):
        # FRED vintages have date precision, not intraday publication times.
        vintage = min((day - timedelta(days=1)).isoformat(), fred._fred_today())
        params = {'series_id': series, 'realtime_start': vintage, 'realtime_end': vintage}
        def fetch():
            meta = fred._request('series', params).get('seriess') or []
            rows = fred._request('series/observations', {
                **params, 'observation_end': vintage, 'sort_order': 'desc', 'limit': 100,
            }).get('observations') or []
            points = [r for r in rows if r.get('value') not in ('.', '', None)]
            if not meta or not points:
                raise ValueError('No observations')
            return {'value': float(points[0]['value']), 'period': points[0]['date'],
                    'unit': meta[0].get('units', '미확인'),
                    'frequency': meta[0].get('frequency', '미확인'), 'vintage': vintage}
        return self._once(('macro', series, day), fetch)

    def calendar(self, day):
        def fetch():
            rows = []
            offset = 0
            while True:
                payload = fred._request('releases/dates', {
                    'realtime_start': day.isoformat(), 'realtime_end': day.isoformat(),
                    'include_release_dates_with_no_data': 'true', 'sort_order': 'asc',
                    'limit': 1000, 'offset': offset,
                })
                page = payload.get('release_dates') or []
                rows.extend(r for r in page if r.get('date') == day.isoformat()
                            and str(r.get('release_name', '')).strip().casefold() in FRED_US_RELEASES)
                offset += len(page)
                if not page or offset >= int(payload.get('count', offset)):
                    return rows
        return self._once(('calendar', day), fetch)

    def bea_calendar(self, day):
        def fetch():
            response = get_with_retry(BEA_RELEASES_URL, timeout=15, provider='BEA')
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError('BEA release calendar format unavailable')
            result = []
            seen = set()
            for title, info in payload.items():
                if str(title).strip().casefold() not in BEA_US_RELEASES or not isinstance(info, dict):
                    continue
                for value in info.get('release_dates', []):
                    try:
                        scheduled = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
                    except ValueError:
                        continue
                    if scheduled.tzinfo is None or scheduled.astimezone(ZoneInfo('America/New_York')).date() != day:
                        continue
                    local_time = scheduled.astimezone(ZoneInfo('America/New_York'))
                    key = (title, local_time.isoformat())
                    if key in seen:
                        continue
                    seen.add(key)
                    result.append({'title': title, 'scheduled_at': local_time.isoformat(),
                                   'source': BEA_SCHEDULE_URL, 'source_api': BEA_RELEASES_URL,
                                   'related_assets': ['미국 주가지수', '미 국채', '달러']})
            return sorted(result, key=lambda item: (item['scheduled_at'], item['title']))
        return self._once(('bea_calendar', day), fetch)

    def census_calendar(self, day):
        source = CENSUS_CALENDAR_URL.format(year=day.year)
        def fetch():
            response = get_with_retry(source, timeout=15, provider='Census')
            return census_events(response.content.decode('utf-8'), day, source)
        return self._once(('census_calendar', day), fetch)

    def bls_calendar(self, day):
        def fetch():
            # BLS, like SEC, answers 403 unless the User-Agent carries a contact address.
            response = get_with_retry(BLS_CALENDAR_URL, timeout=15, provider='BLS',
                                      headers={'User-Agent': sec_edgar._user_agent()})
            return bls_events(response.content.decode('utf-8'), day)
        return self._once(('bls_calendar', day), fetch)

    def policy_calendar(self, day):
        def fetch():
            root = 'https://www.federalreserve.gov'
            index = get_with_retry(root + '/newsevents/calendar.htm', timeout=15, provider='Federal Reserve')
            parser = FedCalendarParser()
            parser.feed(index.content.decode('utf-8'))
            label = day.strftime('%B %Y')
            paths = [url for url, title in parser.links if title.strip() == label
                     and re.fullmatch(r'/newsevents/[0-9a-z-]+\.htm', url)]
            if not paths:
                raise ValueError('Fed month unavailable')
            source = root + paths[0]
            response = get_with_retry(source, timeout=15, provider='Federal Reserve')
            return fed_events(response.content.decode('utf-8'), day, source)
        return self._once(('policy_calendar', day), fetch)

    def earnings(self, symbol):
        return self._once(('earnings', symbol), lambda: self.ticker(symbol).get_earnings_dates(limit=12))

    def earnings_release(self, symbol, day):
        def fetch():
            cik = sec_edgar.cik_for(symbol)
            if cik is None:
                raise ValueError('SEC CIK not found')
            source_api = f'https://data.sec.gov/submissions/CIK{cik}.json'
            payload = sec_edgar._fetch_json(source_api)
            recent = ((payload.get('filings') or {}).get('recent'))
            fields = ('form', 'items', 'filingDate', 'acceptanceDateTime',
                      'accessionNumber', 'primaryDocument')
            if not isinstance(recent, dict) or any(not isinstance(recent.get(field), list) for field in fields):
                raise ValueError('SEC submissions format unavailable')
            arrays = [recent[field] for field in fields]
            if len({len(values) for values in arrays}) != 1:
                raise ValueError('SEC submissions arrays have different lengths')

            matches = []
            for form, items, filing_date, accepted_raw, accession, document in zip(*arrays, strict=True):
                if form != '8-K' or '2.02' not in {item.strip() for item in str(items or '').split(',')}:
                    continue
                try:
                    accepted = datetime.fromisoformat(str(accepted_raw).replace('Z', '+00:00'))
                except ValueError as exc:
                    raise ValueError('SEC acceptance timestamp unavailable') from exc
                if accepted.tzinfo is None:
                    raise ValueError('SEC acceptance timestamp has no timezone')
                accepted_et = accepted.astimezone(ET)
                if accepted_et.date() != day:
                    continue
                accession = str(accession or '')
                if not re.fullmatch(r'\d{10}-\d{2}-\d{6}', accession):
                    raise ValueError('SEC accession number unavailable')
                directory = (f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/'
                             f'{accession.replace("-", "")}')
                document = str(document or '').strip()
                url = f'{directory}/{quote(document, safe="._-")}' if document else f'{directory}/'
                matches.append({
                    'filing_date': filing_date,
                    'accepted_at': accepted_et.isoformat(),
                    'accession_number': accession,
                    'primary_document': document or None,
                    'url': url,
                })
            return {'source_api': source_api, 'filings': matches}

        return self._once(('earnings_release', symbol, day), fetch)


def finite(value):
    try:
        number = float(value)
        return number if pd.notna(number) and abs(number) != float('inf') else None
    except (TypeError, ValueError):
        return None


class FedCalendarParser(HTMLParser):
    """Read the Fed's time / event / day columns; reject layout drift."""

    def __init__(self):
        super().__init__()
        self.depth = 0
        self.capture = None
        self.row = {}
        self.rows = []
        self.links = []
        self.link = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a':
            self.link = [attrs.get('href', ''), '']
        if tag != 'div':
            return
        self.depth += 1
        classes = attrs.get('class', '').split()
        for css, key in [('col-xs-2', 'time'), ('col-xs-7', 'title'), ('col-xs-3', 'days')]:
            if css in classes:
                if key == 'time':
                    self.row = {}
                self.capture = (key, self.depth)
                self.row[key] = ''
                break

    def handle_data(self, data):
        if self.link is not None:
            self.link[1] += data
        if self.capture:
            self.row[self.capture[0]] += ' ' + data.strip()

    def handle_endtag(self, tag):
        if tag == 'a' and self.link is not None:
            self.links.append(tuple(self.link))
            self.link = None
        if tag != 'div':
            return
        if self.capture and self.capture[1] == self.depth:
            key = self.capture[0]
            self.row[key] = ' '.join(self.row[key].split())
            self.capture = None
            if key == 'days' and self.row.get('title') and re.fullmatch(r'\d{1,2}(?:\s*[-–]\s*\d{1,2})?', self.row[key]):
                self.rows.append(dict(self.row))
        self.depth -= 1


class CensusCalendarParser(HTMLParser):
    """Read the Census annual calendar table and its local-time sort key."""

    def __init__(self):
        super().__init__()
        self.in_calendar = False
        self.calendar_found = False
        self.in_row = False
        self.cells = []
        self.cell = None
        self.rows = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'table' and attrs.get('id') == 'calendar':
            self.in_calendar = True
            self.calendar_found = True
        if not self.in_calendar:
            return
        if tag == 'tr':
            self.in_row = True
            self.cells = []
        elif tag == 'td' and self.in_row:
            self.cell = {'parts': [], 'sort_key': attrs.get('sorttable_customkey', '')}

    def handle_data(self, data):
        if self.cell is not None:
            self.cell['parts'].append(data)

    def handle_endtag(self, tag):
        if tag == 'td' and self.cell is not None:
            self.cell['text'] = ' '.join(' '.join(self.cell.pop('parts')).split())
            self.cells.append(self.cell)
            self.cell = None
        elif tag == 'tr' and self.in_row:
            if self.cells:
                self.rows.append(self.cells)
            self.in_row = False
        elif tag == 'table' and self.in_calendar:
            self.in_calendar = False


def census_events(html, day, source):
    parser = CensusCalendarParser()
    parser.feed(html)
    if not parser.calendar_found:
        raise ValueError('Census calendar table unavailable')
    eastern = ZoneInfo('America/New_York')
    events = []
    seen = set()
    for cells in parser.rows:
        if len(cells) < 3:
            continue
        title = ' '.join(cells[0]['text'].split())
        normalized = ' '.join(title.split()).casefold()
        if normalized not in CENSUS_US_RELEASES and not normalized.startswith('advance report on durable goods'):
            continue
        sort_key = cells[1]['sort_key']
        scheduled_at = None
        try:
            if re.fullmatch(r'\d{12}', sort_key):
                local = datetime.strptime(sort_key, '%Y%m%d%H%M').replace(tzinfo=eastern)
                event_day = local.date()
                scheduled_at = local.isoformat()
            else:
                event_day = datetime.strptime(cells[1]['text'], '%B %d, %Y').date()
        except ValueError:
            continue
        if event_day != day:
            continue
        key = (release_key(title), scheduled_at)
        if key in seen:
            continue
        seen.add(key)
        events.append({'title': title, 'scheduled_at': scheduled_at, 'source': source,
                       'time_label': cells[2]['text'],
                       'related_assets': ['미국 주가지수', '미 국채', '달러']})
    return sorted(events, key=lambda item: (item['scheduled_at'] or '', item['title']))


def bls_events(ics, day):
    text = re.sub(r'\n[ \t]', '', ics.replace('\r\n', '\n'))
    if 'BEGIN:VCALENDAR' not in text:
        raise ValueError('BLS calendar format unavailable')
    events = []
    seen = set()
    for block in text.split('BEGIN:VEVENT')[1:]:
        props = {}
        for line in block.split('END:VEVENT')[0].split('\n'):
            name, _, value = line.partition(':')
            props.setdefault(name.split(';')[0].upper(), (name.upper(), value.strip()))
        title = re.sub(r'\\([,;\\])', r'\1', props.get('SUMMARY', ('', ''))[1])
        start_name, start = props.get('DTSTART', ('', ''))
        if ' '.join(title.split()).casefold() not in BLS_US_RELEASES:
            continue
        try:
            local = datetime.strptime(start.rstrip('Z'), '%Y%m%dT%H%M%S')
        except ValueError:
            continue
        if start.endswith('Z'):
            local = local.replace(tzinfo=UTC).astimezone(ET)
        elif 'TZID=US-EASTERN' in start_name or 'TZID=AMERICA/NEW_YORK' in start_name:
            local = local.replace(tzinfo=ET)
        else:
            continue
        if local.date() != day:
            continue
        key = (release_key(title), local.isoformat())
        if key in seen:
            continue
        seen.add(key)
        events.append({'title': title, 'scheduled_at': local.isoformat(), 'source': BLS_CALENDAR_URL,
                       'related_assets': ['미국 주가지수', '미 국채', '달러']})
    return sorted(events, key=lambda item: (item['scheduled_at'], item['title']))


def fed_events(html, day, source):
    parser = FedCalendarParser()
    parser.feed(html)
    if not parser.rows:
        raise ValueError('Fed calendar layout unavailable')
    result = []
    for row in parser.rows:
        days = [int(d) for d in re.split(r'\s*[-–]\s*', row['days'])]
        if not days[0] <= day.day <= days[-1]:
            continue
        stamp = None
        # A range does not establish which day's clock time applies.
        match = re.fullmatch(r'(\d{1,2}):(\d{2})\s*([ap])\.m\.', row['time'], re.I)
        if match and len(days) == 1:
            hour, minute = int(match[1]), int(match[2])
            if 1 <= hour <= 12 and 0 <= minute <= 59:
                stamp = datetime.combine(day, time(hour % 12 + (12 if match[3].lower() == 'p' else 0), minute), ZoneInfo('America/New_York')).isoformat()
        result.append({'title': row['title'], 'scheduled_at': stamp, 'source': source, 'time_label': row['time']})
    return result
