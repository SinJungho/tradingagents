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
from tradingagents.dataflows.vendors import fred
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
FRED_US_RELEASES = frozenset({
    'consumer price index', 'employment situation', 'employment cost index',
    'job openings and labor turnover survey', 'producer price index',
    'gross domestic product', 'personal income and outlays',
    'advance monthly sales for retail and food services',
    'industrial production and capacity utilization', 'new residential construction',
    'new home sales', 'durable goods', 'unemployment insurance weekly claims report',
    'state unemployment insurance weekly claims report', 'fomc press release',
    'fomc meeting minutes', 'beige book', 'monthly treasury statement',
})
BEA_US_RELEASES = frozenset({
    'gross domestic product', 'personal income and outlays',
    'u.s. international trade in goods and services', 'u.s. international transactions',
    'u.s. international investment position',
    'gross domestic product by state and personal income by state',
})


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
            self._tickers[symbol] = yf.Ticker(symbol.replace('.', '-'))
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
