"""Conditional US market research, with bounded public observations and explicit gaps."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin

import pandas as pd

from tradingagents.dataflows.market_report import (
    BEA_SCHEDULE_URL,
    BLS_CALENDAR_URL,
    CBOE_VIX3M_HISTORY_URL,
    CBOE_VIX_HISTORY_URL,
    COMPANIES,
    CREDIT_SPREADS,
    ET,
    PublicMarketData,
    error_reason,
    finite,
    quote_url,
    release_key,
)
from tradingagents.dataflows.net import get_with_retry
from tradingagents.dataflows.vendors import sec_edgar

CBOE = 'https://www.cboe.com/data/mktstat.aspx'
CME_VOI = 'https://www.cmegroup.com/market-data/volume-open-interest.html'
FEDWATCH = 'https://www.cmegroup.com/articles/2023/understanding-the-cme-group-fedwatch-tool-methodology.html'
CFTC = 'https://publicreporting.cftc.gov/Commitments-of-Traders/TFF-Futures-Only/gpe5-46if'
CFTC_API = 'https://publicreporting.cftc.gov/resource/gpe5-46if.json'
CFTC_SCHEDULE = 'https://www.cftc.gov/MarketReports/CommitmentsofTraders/ReleaseSchedule/index.htm'
ICI = 'https://www.ici.org/research/statistics/etfs/weekly-estimated-etf-net-issuance'
FED = 'https://www.federalreserve.gov'
BLS = 'https://www.bls.gov'
SLOOS = FED + '/data/sloos.htm'
TERM_PREMIA = FED + '/data/three-factor-nominal-term-structure-model.htm'
BEA_ARCHIVE = 'https://www.bea.gov/news/archive'
AUCTIONS = 'https://fiscaldata.treasury.gov/datasets/treasury-securities-auctions-data/treasury-securities-auctions-data-updated/'
SEC = 'https://www.sec.gov/edgar/search/'
ALFRED = 'https://alfred.stlouisfed.org/'
FRED = 'https://fred.stlouisfed.org/series/'
EVENT_LABELS = {'cpi': '미국 CPI', 'pce': '미국 PCE 물가', 'employment': '미국 고용', 'fomc': 'FOMC 결정'}
BLS_EVENTS = {'consumer price index': 'cpi', 'employment situation': 'employment'}
NUMBER = r'([+-]?\d+(?:\.\d+)?)'


class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def _text(page):
    parser = PageText()
    parser.feed(page)
    return ' '.join(' '.join(parser.parts).split()).replace('−', '-').replace('‑', '-')


def _fetch(url, provider, **kwargs):
    return get_with_retry(url, timeout=8, provider=provider, **kwargs)


def _release_stamp(text, day):
    # The original embargo/release header supplies the clock, independent of the current calendar.
    match = re.search(r'(?:embargoed until(?: release at)?|for release at).{0,34}?'
                      r'(\d{1,2}):(\d\d)\s*([ap])\.m\.\s*\(?E[DS]?T\b', text[:15000], re.I)
    if match:
        hour, minute, half = match.groups()
        if 1 <= int(hour) <= 12 and 0 <= int(minute) < 60:
            return datetime.combine(day, time(int(hour) % 12 + 12 * (half.lower() == 'p'), int(minute)), ET)
    return None


def _dated_release_text(page, day):
    text = _text(page)
    date_text = f'{day:%B} {day.day}, {day.year}'
    if date_text not in text[:15000]:
        raise ValueError('release date mismatch')
    stamp = _release_stamp(text, day)
    if stamp is None:
        raise ValueError('unverified release time')
    return text, stamp


def _bea_release_url(day):
    params = {'field_related_product_target_id': 476, 'title': ''}
    page = _fetch(BEA_ARCHIVE, 'BEA', params={**params, 'created_1': 'All'}).text
    year = re.search(r'<option\s+value="(\d+)"[^>]*>\s*' + str(day.year) + r'\s*</option>', page)
    if not year:
        raise ValueError('BEA archive year not covered')
    if day.year != datetime.now(ET).year:
        page = _fetch(BEA_ARCHIVE, 'BEA', params={**params, 'created_1': year[1]}).text
    day_pattern = rf'\b{day:%B}\s+0?{day.day},\s+{day.year}\b'
    for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', page, re.I | re.S):
        path = re.search(r'href="(/news/\d{4}/personal-income-and-outlays-[a-z0-9-]+)"', row)
        if path and re.search(day_pattern, _text(row)):
            return urljoin(BEA_ARCHIVE, path[1])
    if day.year == datetime.now(ET).year:
        # The calendar can precede the archival publication and identifies newly released pages.
        page = _fetch(BEA_SCHEDULE_URL, 'BEA').text
        day_pattern = rf'\b{day:%B}\s+0?{day.day}\s+\d{{1,2}}:\d\d'
        for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', page, re.I | re.S):
            path = re.search(r'href="(/news/\d{4}/personal-income-and-outlays-[a-z0-9-]+)"', row)
            if path and f'/news/{day.year}/' in path[1] and re.search(day_pattern, _text(row)):
                return urljoin(BEA_SCHEDULE_URL, path[1])
    return None


def _signed(value, direction):
    return float(value) * (-1 if direction in ('declined', 'decreased', 'fell', 'down') else 1)


def _movement(text, prefix):
    match = re.search(prefix + r'.{0,100}?\b(increased|rose|decreased|declined|fell)\s+' + NUMBER + r'\s+percent', text, re.I)
    return _signed(match[2], match[1].lower()) if match else None


def _release_values(kind, text):
    if kind == 'cpi':
        return {
            'headline_mom_pct': _movement(text, r'Consumer Price Index for All Urban Consumers \(CPI-U\)'),
            'core_mom_pct': _movement(text, r'index for all items less food and energy'),
        }
    if kind == 'pce':
        return {
            'headline_mom_pct': _movement(text, r'From the preceding month, the PCE price index'),
            'core_mom_pct': _movement(text, r'Excluding food and energy, the PCE price index'),
        }
    if kind == 'employment':
        payroll = re.search(r'(?:total )?nonfarm payroll employment\s+(?:changed little|was little changed)'
                            r'(?:\s+in [A-Za-z]+)?\s+\(([+-]?[\d,]+)\)', text, re.I)
        payroll_change = int(payroll[1].replace(',', '')) if payroll else None
        if not payroll:
            payroll = re.search(r'(?:total )?nonfarm payroll employment\s+(increased|rose|declined|fell|'
                                r'edged up|edged down)\s+(?:by\s+)?([\d,]+)', text, re.I)
            if payroll:
                direction = payroll[1].lower().split()[-1]
                payroll_change = int(_signed(payroll[2].replace(',', ''), direction))
        unemployment = re.search(r'unemployment rate(?:, at|\s+(?:was unchanged at|was little changed at|'
                                 r'changed little at|was|edged up to|edged down to|rose to|increased to|'
                                 r'declined to|fell to|decreased to))\s+' + NUMBER + r'\s+percent', text, re.I)
        revisions = {}
        for month, old, new in re.findall(
            r'for ([A-Z][a-z]+) was revised (?:up|down) by [\d,]+, from ([+-]?[\d,]+) to ([+-]?[\d,]+)',
            text,
        )[:2]:
            revisions[month] = {'previously_published': int(old.replace(',', '')), 'revised': int(new.replace(',', ''))}
        return {'payroll_change': payroll_change,
                'unemployment_pct': float(unemployment[1]) if unemployment else None,
                'payroll_revisions': revisions or None}
    number = r'(\d+(?:-\d/\d|\.\d+)?)'
    match = re.search(r'(?:target range for the federal funds rate at|target range for the federal funds rate by [^.]{1,50}? to)\s+'
                      + number + ' to ' + number + r' percent', text, re.I)

    def rate(value):
        base, hyphen, fraction = value.partition('-')
        if not hyphen:
            return float(base)
        numerator, denominator = fraction.split('/')
        return float(base) + int(numerator) / int(denominator)

    return {'target_range_pct': [rate(match[1]), rate(match[2])] if match else None}


def _official_release_sources(day):
    """Published BLS/FOMC archives also cover dates missing from current calendars."""
    jobs = {
        'cpi': (BLS + f'/news.release/archives/cpi_{day:%m%d%Y}.htm', 'BLS'),
        'employment': (BLS + f'/news.release/archives/empsit_{day:%m%d%Y}.htm', 'BLS'),
        'fomc': (FED + f'/newsevents/pressreleases/monetary{day:%Y%m%d}a.htm', 'Federal Reserve'),
        'pce': (BEA_ARCHIVE, 'BEA'),
    }

    def locate(job):
        kind, (url, agency) = job
        try:
            if kind == 'pce':
                url = _bea_release_url(day)
                if not url:
                    return kind, None, None
            response = _fetch(url, agency, passthrough=(404,), **(
                {'headers': {'User-Agent': sec_edgar._user_agent()}} if agency == 'BLS' else {}))
            if response.status_code == 404:
                return kind, None, None
            page = response.content.decode('utf-8-sig', errors='replace')
            if kind in BLS_EVENTS.values():
                # The first BLS preformatted block holds the original release and revisions.
                pre = re.search(r'<pre\b[^>]*>(.*?)</pre>', page, re.I | re.S)
                if pre is None:
                    raise ValueError('BLS release block missing')
                text, stamp = _dated_release_text(pre[1], day)
                correction = re.search(
                    r'(?:this (?:news )?release (?:was|has been) (?:reissued|corrected)|'
                    r'correction notice|errata to this release)', text[:1800], re.I,
                )
                if correction:
                    return kind, (url, stamp, None), '정정본의 최초 공개 값·시각 미확인'
                return kind, (url, stamp, _release_values(kind, text)), None
            if kind == 'fomc' and 'Federal Reserve issues FOMC statement' not in page:
                return kind, None, None
            text, stamp = _dated_release_text(page, day)
            return kind, (url, stamp, _release_values(kind, text)), None
        except Exception as exc:
            return kind, None, error_reason(exc)

    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        results = list(pool.map(locate, jobs.items()))
    return {kind: release for kind, release, _ in results if release}, {
        kind: failure for kind, _, failure in results if failure
    }


def _thresholds(rows, day, previous_day):
    equity, rates, unavailable = [], [], []
    for symbol in ('^GSPC', '^IXIC', '^VIX'):
        row = next((row for row in rows if row.get('symbol') == symbol), {})
        values = row.get('value') or {}
        change = finite(values.get('return_1d') if symbol != '^VIX' else row.get('change_points'))
        # Legacy providers may expose VIX's two actual daily closes without the derived field.
        if symbol == '^VIX' and 'change_points' not in row and row.get('close_source') in (None, 'daily_close'):
            calculations = row.get('calculations') or {}
            closes = calculations.get('price_closes', [])[-2:]
            if calculations.get('dates', [])[-2:] == [previous_day, day] and len(closes) == 2:
                before, after = map(finite, closes)
                if before is not None and after is not None:
                    change = after - before
        if change is None:
            unavailable.append(symbol)
        elif (change >= 5 if symbol == '^VIX' else abs(change) >= 2):
            unit = '포인트 상승' if symbol == '^VIX' else '% 등락'
            scope = (' (정규장 5분 봉과 전일 종가 비교)'
                     if symbol != '^VIX' and row.get('close_source') == 'same_day_5m_regular_close_proxy' else '')
            equity.append((row['id'], f"{row['label']} {change:+.2f}{unit}{scope}"))
    candidates = [row for row in rows if row.get('series') in ('DGS10', 'TNX')
                  and row.get('observation_period') == day and finite(row.get('change_bp')) is not None]
    if candidates:
        row = min(candidates, key=lambda item: item['series'] != 'DGS10')
        change = finite(row['change_bp'])
        if abs(change) >= 10:
            rates.append((row['id'], f"{row['label']} {change:+.1f}bp 변동"))
    else:
        unavailable.append('동일 기준 10년물')
    return equity, rates, unavailable


def _complete_bars(frame, start, end):
    if not isinstance(frame, pd.DataFrame) or not isinstance(frame.index, pd.DatetimeIndex):
        return pd.DataFrame()
    if frame.empty or frame.index.tz is None or 'Close' not in frame or frame.index.has_duplicates:
        return pd.DataFrame()
    completed = frame.index + pd.Timedelta(minutes=5)
    return frame[(frame.index >= start) & (completed <= end)].sort_index()


def _aligned_prices(provider, symbol, before, after):
    day = after.tz_convert(ET).date()
    before_day = before.tz_convert(ET).date()
    start = before - pd.Timedelta(minutes=5)
    end = after - pd.Timedelta(minutes=5)
    first_frame = provider.intraday(symbol, before_day)
    last_frame = first_frame if before_day == day else provider.intraday(symbol, day)
    prices = []
    for frame, target in ((first_frame, start), (last_frame, end)):
        bars = _complete_bars(frame, target, target + pd.Timedelta(minutes=5))
        prices.append(finite(bars['Close'].iloc[0]) if not bars.empty else None)
    return tuple(prices)


def _reaction_rows(provider, add, stamp, cutoff, event_id, **metadata):
    after = stamp + pd.Timedelta(minutes=15)
    for symbol, label in (('^TNX', '10년 금리 지수 대용치'), ('DX-Y.NYB', 'ICE 달러지수'),
                          ('ES=F', 'ES 연속 선물'), ('NQ=F', 'NQ 연속 선물')):
        unit, change, reason = ('bp' if symbol == '^TNX' else '%'), None, None
        if after > cutoff:
            reason = '반응 창 미완료'
        else:
            try:
                before_price, after_price = _aligned_prices(provider, symbol, stamp, after)
                if before_price in (None, 0) or after_price is None:
                    reason = '동일 시간 창의 5분 봉 미확인'
                else:
                    change = ((after_price - before_price) * 100 if unit == 'bp'
                              else (after_price / before_price - 1) * 100)
            except Exception as exc:
                reason = error_reason(exc)
        add('추가 조사', f'발표 직후 {label} 반응', finite(change), quote_url(symbol), unit=unit,
            period=stamp.tz_convert(ET).date().isoformat(), observed_at=after.isoformat() if change is not None else None,
            status='available' if change is not None else 'unavailable', reason=reason, symbol=symbol,
            note='발표 시각 직전 완료 봉에서 발표 후 15분 완료 봉까지의 관측 변화. 인과관계 미확정.',
            window_start=stamp.isoformat(), window_end=after.isoformat(), inputs=[event_id], **metadata)


def _derivative_rows(provider, day, cutoff, add, *, include_as_of=True, expected_period=None):
    add('매크로', 'Cboe SPX·SPXW 풋/콜 거래량 비율', None, CBOE,
        status='not_run', reason='Cboe 공개 시각·자동 저장 조건을 확인한 수집 경로가 없음',
        period=day.isoformat(), source_kind='official', data_scope='Cboe의 SPX+SPXW 거래량')
    term_structure = getattr(provider, 'volatility_term_structure', None)
    if callable(term_structure):
        try:
            values = term_structure(day, include_as_of=include_as_of)
            ratio = finite(values['ratio'])
            previous_ratio = finite(values['previous_ratio'])
            transition = values['transition']
            state = {
                'inverted_today': '오늘 1개월 변동성 역전',
                'back_below_one': '오늘 1.0 아래로 역전 해소',
                'inverted': '역전 지속',
                'below_one': '1.0 이하, 역전 아님',
            }.get(transition, '상태 미확인')
            note = (f"{state}. VIX/VIX3M={ratio:.4f}; "
                    f"VIX {values['vix']:.4f}, VIX3M {values['vix3m']:.4f}; "
                    f"전 공통 거래일 {values['previous_period']} 비율 {previous_ratio:.4f}. "
                    '두 Cboe 일별 종가의 공통 날짜를 사용. CSV에는 분 단위 게시 시각이 없음.')
            if not include_as_of:
                note += ' 종목 분석 기준이 정규장 종가보다 이르므로 대상 거래일 종가는 제외.'
            timely = values['period'] == (expected_period or day).isoformat()
            status = 'available' if timely else 'partial'
            add('매크로', 'Cboe 1개월/3개월 변동성 비율 (VIX/VIX3M)', ratio,
                CBOE_VIX_HISTORY_URL, unit='비율', period=values['period'],
                sources=[CBOE_VIX_HISTORY_URL, CBOE_VIX3M_HISTORY_URL],
                source_kind='official', status=status,
                reason=None if timely else '최신 공통 Cboe 관측일이 기준 시점의 예상 직전 종가와 다름', note=note,
                data_scope='Cboe 일별 VIX 30일 및 VIX3M 약 3개월 종가',
                calculations={'vix_close': values['vix'], 'vix3m_close': values['vix3m'],
                              'ratio': ratio, 'previous_period': values['previous_period'],
                              'previous_ratio': previous_ratio, 'transition': transition})
        except Exception as exc:
            add('매크로', 'Cboe 1개월/3개월 변동성 비율 (VIX/VIX3M)', None,
                CBOE_VIX_HISTORY_URL, sources=[CBOE_VIX_HISTORY_URL, CBOE_VIX3M_HISTORY_URL],
                period=day.isoformat(), source_kind='official', status='unavailable',
                reason='동일 관측일의 VIX·VIX3M 종가를 검증하지 못함 (' + error_reason(exc) + ')',
                note='Cboe 일별 이력의 게시 시각은 확인되지 않음.')
    for symbol in ('ES=F', 'NQ=F', 'ZQ=F'):
        values = {'price': None, 'volume_observed': None, 'open_interest': None, 'contract_month': None,
                  'rollover': None, 'preliminary': None}
        observed = None
        reason = None
        try:
            # Same New York date through the customary 17 ET halt. The segment excludes
            # the previous evening and any next-session bars; volume is explicitly partial.
            halt = pd.Timestamp(datetime.combine(day, time(17), ET))
            bars = _complete_bars(provider.intraday(symbol, day), cutoff.normalize(), min(cutoff, halt))
            if bars.empty:
                raise ValueError('No completed bars')
            values['price'] = finite(bars['Close'].iloc[-1])
            observed = (bars.index[-1] + pd.Timedelta(minutes=5)).isoformat()
            if 'Volume' in bars:
                volume = pd.to_numeric(bars['Volume'], errors='coerce')
                if volume.notna().all() and volume.ge(0).all():
                    values['volume_observed'] = finite(volume.sum())
            reason = '연속 선물 데이터의 계약월·롤오버·미결제약정·잠정 여부 미확인'
        except Exception as exc:
            reason = '공급자 관측 미확인 (' + error_reason(exc) + ')'
        if symbol == 'ZQ=F':
            price = values['price']
            values['implied_avg_effr_pct'] = 100 - price if price is not None and 0 < price < 110 else None
        add('매크로', '연방기금 선물 내재 월평균 금리 대용치' if symbol == 'ZQ=F' else f'{symbol} 가격·거래량·미결제약정',
            values, quote_url(symbol), period=day.isoformat(), observed_at=observed, symbol=symbol,
            status='partial' if values['price'] is not None else 'unavailable', reason=reason, source_kind='secondary',
            note=('100 − ZQ 연속 선물 가격. 해당 계약의 인도월 및 회의별 확률 미확인.' if symbol == 'ZQ=F' else
                  '거래량은 뉴욕 자정부터 기준 이내 5분 봉 합계이며 상품 당일 전체 거래량·결제가격 미확인.'),
            methodology_source=FEDWATCH if symbol == 'ZQ=F' else CME_VOI)

TREASURY_API = 'https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/'
CFTC_MARKETS = {'13874A': 'ES', '209742': 'NQ', '043602': '미 국채 10년물'}


def _cftc_release_days(page, year):
    heading = next((match for match in re.finditer(r'<h[1-6]\b[^>]*>(.*?)</h[1-6]>', page, re.I | re.S)
                    if _text(match[1]) == f'{year} Release Schedule'), None)
    table = re.search(r'^(?:(?!<h[1-6]).)*?(<table\b.*?</table>)', page[heading.end():], re.I | re.S) if heading else None
    if not table:
        raise ValueError('해당 연도 공개 일정 미확인')
    release_days = []
    for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', table[1], re.I | re.S):
        cells = [_text(cell) for cell in re.findall(r'<td\b[^>]*>(.*?)</td>', row, re.I | re.S)]
        if not cells or cells[0] == 'Month':
            continue
        month = datetime.strptime(cells[0].strip('.'), '%B').month
        for value in cells[1:]:
            item = re.fullmatch(r'(\d\d?)(\*?)', value)
            if item:
                release_days.append((date(year, month, int(item[1])), bool(item[2])))
    if not release_days:
        raise ValueError('공개 일정 표 미확인')
    return sorted(release_days)


def _cftc_rows(day, cutoff, add):
    try:
        schedule = _fetch(CFTC_SCHEDULE, 'CFTC').text
        days = _cftc_release_days(schedule, day.year)
        start = day - timedelta(days=28)
        response = _fetch(CFTC_API, 'CFTC', params={
            '$where': f"report_date_as_yyyy_mm_dd between '{start}T00:00:00.000' and '{day}T00:00:00.000' "
                      "AND cftc_contract_market_code in ('13874A','209742','043602')",
            '$order': 'report_date_as_yyyy_mm_dd DESC,cftc_contract_market_code ASC',
            '$select': 'report_date_as_yyyy_mm_dd,cftc_contract_market_code,lev_money_positions_long,'
                       'lev_money_positions_short,lev_money_positions_spread,open_interest_all',
            '$limit': 50,
        }).json()
        if not isinstance(response, list):
            raise ValueError('CFTC 표본 형식 미확인')
        eligible = {}
        for row in response:
            observation = date.fromisoformat(row['report_date_as_yyyy_mm_dd'][:10])
            code = row['cftc_contract_market_code']
            if code not in CFTC_MARKETS or observation > day or observation.weekday() != 1:
                continue
            # Use the official year's calendar and only ordinary Tuesday-to-Friday releases.
            # Extraordinary publications lack a verified observation-to-release mapping.
            published = observation + timedelta(days=3)
            if (published, False) not in days:
                continue
            listed_time = datetime.combine(published, time(15, 30), ET)
            if listed_time > cutoff:
                continue
            eligible.setdefault(observation, []).append((code, row, listed_time))
        if not eligible:
            raise ValueError('기준 이내 통상 공개 일정과 연결된 CFTC 주간 관측 미확인')
        observation = max(eligible)
        values = {}
        release_at = eligible[observation][0][2]
        for code, row, _ in eligible[observation]:
            long = int(row['lev_money_positions_long'])
            short = int(row['lev_money_positions_short'])
            values[CFTC_MARKETS[code]] = {
                'long': long, 'short': short, 'net': long - short,
                'spreading': int(row['lev_money_positions_spread']),
                'all_trader_open_interest': int(row['open_interest_all']),
            }
        add('추가 조사', 'CFTC TFF 레버리지 펀드 포지션', values, CFTC, unit='계약 수',
            period=observation.isoformat(), scheduled_at=release_at.isoformat(),
            status='available' if len(values) == len(CFTC_MARKETS) else 'partial',
            reason=None if len(values) == len(CFTC_MARKETS) else '일부 계약시장 집계 미확인',
            source_kind='official', sources=[CFTC_API, CFTC_SCHEDULE],
            note='선물 전용 TFF의 레버리지 펀드 분류 및 계약시장 표본. 관측은 화요일 종가 기준. '
                 '공개 시각은 공식 통상 일정이며 보정 이력은 미확인. 당일 매도 주체 식별 불가.')
    except Exception as exc:
        add('추가 조사', 'CFTC TFF 레버리지 펀드 포지션', None, CFTC, status='unavailable',
            reason='공개 일정·포지션 표본 확인 실패 (' + error_reason(exc) + ')', source_kind='official')


def _macro_read(provider, series, day):
    row = provider.macro(series, day)
    period = date.fromisoformat(row['period'])
    vintage = date.fromisoformat(row['vintage'])
    value = finite(row['value'])
    if not period <= vintage < day or value is None:
        raise ValueError('unverified vintage')
    return value, period, vintage, row


def _macro_row(provider, series, label, day, add, *, scope=None, max_age=10):
    value = period = vintage = previous = change = None
    try:
        value, period, vintage, raw = _macro_read(provider, series, day)
        previous = finite(raw.get('previous'))
        previous_period = raw.get('previous_period')
        if previous is not None and previous_period and date.fromisoformat(previous_period) < period:
            change = round(100 * (value - previous), 8)
        stamp = period.isoformat()
        stale = (day - period).days > max_age
        note = '기준 전일까지의 FRED 빈티지. 분 단위 공개 시각 미확인.'
        if scope:
            note += ' ' + scope
        return add('추가 조사', label, value, FRED + series, unit=raw['unit'], period=stamp,
                   vintage=vintage.isoformat(), source_kind='official_vintage', note=note,
                   series=series, previous_value=previous, previous_period=previous_period,
                   change_bp=change, status='stale' if stale else 'available',
                   reason='마지막 관측이 비교 범위보다 오래됨' if stale else None)
    except Exception as exc:
        return add('추가 조사', label, None, FRED + series, status='unavailable',
                   reason='기준 이내 빈티지 미확인 (' + error_reason(exc) + ')',
                   series=series, source_kind='official_vintage', note=scope)


def _credit_rows(provider, day, calendar, add):
    quotes, failures = {}, {}
    for series in CREDIT_SPREADS:
        try:
            quotes[series] = _macro_read(provider, series, day)
        except Exception as exc:
            failures[series] = error_reason(exc)

    horizons = (1, 5)
    paired_dates, gaps = {}, {}
    periods = {quote[1] for quote in quotes.values()}
    for horizon in horizons:
        if failures or len(periods) != 1:
            gaps[horizon] = f'{horizon}거래일 비교에 필요한 HY·IG 최신 공통 관측일 미확인'
            continue
        period = next(iter(periods))
        sessions = calendar.sessions
        if pd.Timestamp(period) not in sessions or (position := sessions.get_loc(str(period))) < horizon:
            gaps[horizon] = f'{horizon}거래일 비교 기준일 미확인'
            continue
        prior = sessions[position - horizon].date().isoformat()
        if any(finite(raw.get('observations', {}).get(prior)) is None for _, _, _, raw in quotes.values()):
            gaps[horizon] = f'{horizon}거래일 전 {prior} HY·IG 공통 관측 미확인'
            continue
        paired_dates[horizon] = prior

    note = ('ICE Data Indices, LLC의 ICE BofA OAS를 FRED에서 인용. 수치는 로컬 검토용. '
            '기준 전일까지의 빈티지를 사용하며 분 단위 공개 시각은 미확인.')
    for series, label in CREDIT_SPREADS.items():
        if series in failures:
            add('추가 조사', label, None, FRED + series, status='unavailable',
                reason=f'기준 이내 빈티지 미확인 ({failures[series]})', series=series,
                source_kind='official_vintage', note=note)
            continue
        value, period, vintage, raw = quotes[series]
        comparisons = {}
        for horizon, prior in paired_dates.items():
            previous = finite(raw['observations'][prior])
            comparisons[horizon] = {'observation_period': prior, 'value': previous,
                                    'change_bp': round(100 * (value - previous), 8)}
        one_day = comparisons.get(1, {})
        stale = (day - period).days > 10
        reasons = ['마지막 관측이 비교 범위보다 오래됨'] if stale else []
        add('추가 조사', label, value, FRED + series, unit=raw['unit'], period=period.isoformat(),
            vintage=vintage.isoformat(), source_kind='official_vintage', series=series, note=note,
            local_use_only=True, previous_value=one_day.get('value'),
            previous_period=one_day.get('observation_period'), change_bp=one_day.get('change_bp'),
            change_bp_5d=comparisons.get(5, {}).get('change_bp'),
            comparison_observations=comparisons, comparison_gaps=gaps,
            status='stale' if stale else 'partial' if gaps else 'available',
            reason=' · '.join([*reasons, *gaps.values()]) or None)


def _credit_confirmation(rows):
    if not all(row['status'] in ('available', 'partial') for row in rows):
        return []
    first, second = rows
    if (first['observation_period'] != second['observation_period']
            or not first.get('previous_period') or first['previous_period'] != second.get('previous_period')):
        return []
    if all((row.get('change_bp') or 0) > 0 for row in rows):
        return [(row['id'], f"{row['label']} 확대 ({row['observation_period']})") for row in rows]
    return []


def _auction_rows(day, add):
    try:
        # This feed supplies date precision for results. Restrict numerical results
        # to completed prior dates because announcement/auction time isn't release time.
        start = day - timedelta(days=7)
        end = day - timedelta(days=1)
        for endpoint, date_field in (('treasury_securities_auctions_v2', 'comp_auction_close_date'),
                                     ('auctions_query', 'auction_date')):
            api = TREASURY_API + endpoint
            response = _fetch(api, 'Treasury', params={
                'filter': f'{date_field}:gte:{start},{date_field}:lte:{end}',
                'fields': f'{date_field},security_type,security_term,high_yield,bid_to_cover_ratio',
                'page[size]': '100',
                'sort': '-' + date_field,
            }).json()
            raw = response['data']
            if not isinstance(raw, list) or int(response['meta']['total-count']) > len(raw):
                raise ValueError('입찰 결과 행 형식 또는 완전성 미확인')
            if raw:
                break
        rows = [
            {'date': item[date_field], 'type': item['security_type'], 'term': item['security_term'],
             'high_yield_pct': finite(item['high_yield']), 'bid_to_cover': finite(item['bid_to_cover_ratio'])}
            for item in raw if item['security_type'] in ('Note', 'Bond')
            and start <= date.fromisoformat(item[date_field]) <= end
            and finite(item['high_yield']) is not None
        ]
        add('추가 조사', '최근 미 재무부 중장기 국채 입찰 결과', rows or None, AUCTIONS, source_kind='official',
            source_api=api, status='partial' if rows else 'none_found',
            reason='동일일 결과 공개 시각 미확인' if rows else '직전 7일의 확인된 중장기 입찰 없음',
            note='발표 시각이 없는 API 값은 전일 이전 입찰 결과만 사용.')
    except Exception as exc:
        add('추가 조사', '최근 미 재무부 중장기 국채 입찰 결과', None, AUCTIONS, source_kind='official',
            status='unavailable', reason='입찰 API 확인 실패 (' + error_reason(exc) + ')')


def _sofr_row(provider, day, add):
    source = FRED + 'SOFR'
    try:
        sofr, period, vintage, _ = _macro_read(provider, 'SOFR', day)
        iorb, reference, _, _ = _macro_read(provider, 'IORB', period + timedelta(days=1))
        if reference != period:
            raise ValueError('unaligned IORB observation')
        add('추가 조사', 'SOFR−IORB', round((sofr - iorb) * 100, 8), source, unit='bp',
            period=period.isoformat(), vintage=vintage.isoformat(), sources=[source, FRED + 'IORB'],
            source_kind='official_vintage', note='동일 관측일의 FRED 빈티지. 담보부 익일물 조달 지표.')
    except Exception as exc:
        add('추가 조사', 'SOFR−IORB', None, source, status='unavailable',
            reason='동일 관측일 기준 자료 미확인 (' + error_reason(exc) + ')', source_kind='official_vintage')


def _filing_rows(provider, day, cutoff, add):
    confirmed, failed = [], []
    for symbol in COMPANIES:
        try:
            for filing in provider.earnings_release(symbol, day)['filings']:
                accepted = pd.Timestamp(filing['accepted_at'])
                url = str(filing['url'])
                if (accepted.tzinfo is None or not cutoff.normalize() <= accepted <= cutoff
                        or not url.startswith('https://www.sec.gov/Archives/edgar/')):
                    continue
                confirmed.append((symbol, accepted, url))
        except Exception:
            failed.append(symbol)
    for symbol, accepted, url in confirmed:
        add('추가 조사', f'{symbol} SEC 실적 8-K 공시', symbol, url,
            published=accepted.isoformat(), period=day.isoformat(), source_kind='official',
            data_scope='대표 대형주 표본의 8-K Item 2.02 접수 시각')
    if failed:
        add('추가 조사', '대표 대형주 SEC 공시 조회', None, SEC, status='unavailable',
            reason='표본 조회 실패: ' + ', '.join(failed), source_kind='official')
    elif not confirmed:
        add('추가 조사', '대표 대형주 SEC 공시 조회', None, SEC, status='none_found',
            reason='기준 이내 실적 8-K 표본 없음', source_kind='official')


def _currency_row(provider, calendar, session, cutoff, add):
    previous = calendar.previous_session(session)
    start, end = calendar.session_close(previous), calendar.session_close(session)
    source = quote_url('KRW=X')
    try:
        if end > cutoff:
            raise ValueError('미완료 정규장')
        asset_base, asset_close = _aligned_prices(provider, 'SPY', start, end)
        fx_base, fx_close = _aligned_prices(provider, 'KRW=X', start, end)
        if any(x is None or x <= 0 for x in (asset_base, asset_close, fx_base, fx_close)):
            raise ValueError('시간 미정렬')
        add('추가 조사', 'SPY 원화 환산 정규장 1거래일 성과 대용치',
            (asset_close * fx_close / (asset_base * fx_base) - 1) * 100, source, unit='%',
            period=session.date().isoformat(), observed_at=end.isoformat(), source_kind='proxy',
            sources=[quote_url('SPY'), source], note='양 거래일 정규장 마감과 동시에 끝난 SPY·USD/KRW 5분 봉. 배당·비용 제외.')
    except Exception:
        add('추가 조사', 'SPY 원화 환산 정규장 1거래일 성과 대용치', None, source, status='unavailable',
            reason='같은 시각에 끝난 USD/KRW와 SPY의 완료 5분 봉을 모두 확인하지 못함', source_kind='proxy')


def _calendar_releases(provider, day):
    sources = {
        'bls_calendar': (BLS_CALENDAR_URL, BLS_EVENTS),
        'bea_calendar': (BEA_SCHEDULE_URL, {'personal income and outlays': 'pce'}),
        'policy_calendar': (FED + '/newsevents/calendar.htm', {
            'fomc meeting': 'fomc', 'fomc statement': 'fomc', 'fomc announcement': 'fomc',
        }),
    }
    events, failures = {}, []
    for name, (source, kinds) in sources.items():
        try:
            for item in getattr(provider, name)(day):
                kind = kinds.get(release_key(item['title']))
                if not kind:
                    continue
                at = pd.Timestamp(item['scheduled_at']) if item.get('scheduled_at') else None
                if at is not None and (at.tzinfo is None or at.tz_convert(ET).date() != day):
                    continue
                # An untimed FOMC meeting row can refer to the first of two days.
                if kind == 'fomc' and at is None:
                    continue
                events.setdefault(kind, (item.get('source') or source, at))
        except Exception as exc:
            failures.append((source, error_reason(exc)))
    return events, failures


def _previous_release(provider, kind, day):
    if kind == 'fomc':
        lo, lo_day, vintage, _ = _macro_read(provider, 'DFEDTARL', day)
        hi, hi_day, _, _ = _macro_read(provider, 'DFEDTARU', day)
        if lo_day == hi_day:
            return {'target_range_pct': [lo, hi], 'period': lo_day.isoformat(), 'vintage': vintage.isoformat()}
        return None

    series = {
        'cpi': ('CPIAUCSL', 'CPILFESL'), 'pce': ('PCEPI', 'PCEPILFE'), 'employment': ('PAYEMS', 'UNRATE'),
    }[kind]
    first, first_day, vintage, left = _macro_read(provider, series[0], day)
    second, second_day, _, right = _macro_read(provider, series[1], day)
    if first_day != second_day:
        return None
    base, core = finite(left.get('previous')), finite(right.get('previous'))
    result = {'period': first_day.isoformat(), 'vintage': vintage.isoformat()}
    if kind == 'employment':
        result.update(payroll_change=round((first - base) * 1000) if base is not None else None,
                      unemployment_pct=second)
    else:
        result.update(headline_mom_pct=round((first / base - 1) * 100, 3) if base else None,
                      core_mom_pct=round((second / core - 1) * 100, 3) if core else None)
    return result


def collect_investigations(provider, window, calendar, evidence, add):
    """Collect the daily derivatives and trigger only the relevant further investigations."""
    day = date.fromisoformat(window['day'])
    cutoff = pd.Timestamp(window['cutoff']).tz_convert(ET)
    session = calendar.date_to_session(day)
    previous = calendar.previous_session(session).date()
    equity, rates, unknown = _thresholds(evidence, day.isoformat(), previous.isoformat())
    last_session = calendar.next_session(session).date().isocalendar()[:2] != day.isocalendar()[:2]
    public = isinstance(provider, PublicMarketData)
    investigations = []

    def run(key, label, reasons, checks, trigger_ids=()):
        reason = ' · '.join(reasons) if reasons else '조사 조건 미충족'
        first = len(evidence)
        if reasons:
            checks()
        items = evidence[first:]
        for row in items:
            row['investigation'] = key
            row['research_reason'] = reason
        status = 'not_run'
        if reasons:
            statuses = {row['status'] for row in items}
            status = ('unavailable' if not statuses or statuses == {'unavailable'}
                      else 'partial' if statuses - {'available', 'none_found'} else 'available')
        investigations.append({'key': key, 'label': label, 'status': status, 'reason': reason,
                               'required': bool(reasons),
                               'evidence_ids': [row['id'] for row in items], 'trigger_evidence_ids': list(trigger_ids)})
        return items

    def missing(label, source, reason, *, status='unavailable', **kwargs):
        return add('추가 조사', label, None, source, status=status, reason=reason, **kwargs)

    run('derivatives', '일간 파생상품', ['매 거래일'],
        lambda: _derivative_rows(provider, day, cutoff, add,
                                 include_as_of=not window.get('analysis_mode', False),
                                 expected_period=(previous if window.get('analysis_mode', False) else day)))

    candidates, calendar_errors = _calendar_releases(provider, day)
    official, original_errors = _official_release_sources(day) if public else ({}, {})
    due = {}
    for kind, (source, stamp) in candidates.items():
        if stamp is None or stamp <= cutoff:
            due[kind] = (source, stamp, None)
    for kind, (source, stamp, values) in official.items():
        if stamp <= cutoff:
            due[kind] = (source, pd.Timestamp(stamp), values)
        else:
            due.pop(kind, None)

    def event_rows():
        for kind, (source, stamp, values) in sorted(due.items(), key=lambda item: (
                item[1][1] is None, item[1][1] or cutoff)):
            try:
                prior = _previous_release(provider, kind, day)
            except Exception:
                prior = None
            has_values = values and any(value is not None for value in values.values())
            row = add('추가 조사', EVENT_LABELS[kind] + ' 발표', {
                'actual_at_release': values if has_values else None,
                'prior_known_release': prior,
                'pre_release_consensus': None,
            }, source, period=day.isoformat(), scheduled_at=stamp.isoformat() if stamp is not None else None,
                published=stamp.isoformat() if has_values and stamp is not None else None,
                status='partial', source_kind='official', sources=[source, ALFRED],
                reason='발표 전 시각이 기록된 공개 컨센서스 미확인'
                       + ('' if has_values else f'; 발표 당시 실제치 미확인 ({original_errors.get(kind, "원문 검증 필요")})')
                       + ('' if prior else '; 이전 빈티지 미확인'),
                note='원 발표문 값과 발표 전 전일 빈티지. 보도자료 수정치가 있으면 발표 당시 제공한 수정분만 기록.')
            if stamp is not None:
                _reaction_rows(provider, add, stamp, cutoff, row['id'])

    event_results = run('release_reaction', 'CPI·PCE·고용·FOMC 발표와 반응',
                        [EVENT_LABELS[kind] + ' 발표 확인' if kind in official
                         else EVENT_LABELS[kind] + ' 공식 일정 도래' for kind in due], event_rows)

    if calendar_errors or original_errors:
        # A failed schedule check does not assert that there were no releases.
        def failed_sources():
            for source, reason in calendar_errors:
                missing('대상일 공식 일정', source, reason, source_kind='official')
            for kind, reason in original_errors.items():
                if kind in due:
                    continue
                source = {'cpi': BLS_CALENDAR_URL, 'employment': BLS_CALENDAR_URL, 'pce': BEA_SCHEDULE_URL,
                          'fomc': FED + '/newsevents/calendar.htm'}[kind]
                missing(EVENT_LABELS[kind] + ' 원문 조회', source, reason, source_kind='official')

        run('release_coverage', '대상일 발표 자료 누락', ['공식 일정·원문 조회 일부 실패'], failed_sources)

    weekly_reason = ['주의 마지막 거래일'] if last_session else []
    event_reason = [EVENT_LABELS[kind] + ' 발표' for kind in due]
    market_reason = [why for _, why in (*equity, *rates)]
    trigger_ids = [key for key, _ in (*equity, *rates)] + [
        row['id'] for row in event_results if row['label'].endswith(' 발표')]
    credit_reasons = ['매 거래일']
    credit = run('credit', '하이일드·투자등급 신용 스프레드',
                 credit_reasons + weekly_reason + market_reason + event_reason,
                 lambda: _credit_rows(provider, day, calendar, add), trigger_ids)
    credit_stress = _credit_confirmation(credit) if len(credit) == 2 else []

    def weekly_rows():
        if public:
            _cftc_rows(day, cutoff, add)
        else:
            missing('CFTC TFF 레버리지 펀드 포지션', CFTC, '공개 파생 자료 공급 경로 미제공',
                    source_kind='official')
        missing('ICI ETF 순발행 추정', ICI, '당시 발표본의 공개 시각·개정 이력을 확인한 수집 경로가 없음',
                status='not_run', source_kind='industry_estimate',
                data_scope='ICI 주간 업계 전체 순발행 추정, 월간 실제 집계와 구분')
        missing('업종 이익 전망 수정·가이던스', SEC,
                '과거 시점의 공개 컨센서스와 가이던스 집계를 대조하는 수집 경로가 없음',
                status='not_run', source_kind='official_filings')
        _filing_rows(provider, day, cutoff, add)

    run('weekly_flows', '주간 수급·이익 전망', weekly_reason, weekly_rows)

    def rate_rows():
        _macro_row(provider, 'THREEFYTP10', '연준 Kim–Wright 10년 기간 프리미엄 추정', day, add, max_age=15,
                   scope='모형 추정치. 의사결정 당시 빈티지 사용. 뉴욕 연은 ACM과 추정 방식이 다름.')
        if public:
            _auction_rows(day, add)
        else:
            missing('최근 미 재무부 중장기 국채 입찰 결과', AUCTIONS, '공개 입찰 공급 경로 미제공',
                    source_kind='official')
        missing('금리 급변 시 회의별 선물 내재 기대', FEDWATCH,
                '공개 FedWatch 자료의 자동 이용 제한. 연속 ZQ는 월평균 대용치',
                status='not_run', source_kind='official', related_evidence_ids=[
                    row['id'] for row in evidence if row.get('symbol') == 'ZQ=F'
                ])

    run('rates', '장기 금리 급변', [why for _, why in rates], rate_rows, [key for key, _ in rates])

    def equity_rows():
        if not last_session:
            _filing_rows(provider, day, cutoff, add)
        for label, source in (
            ('관련 증권사 리서치 공개 원문', None),
            ('CTA·변동성 목표·딜러 감마·레버리지 ETF 수급', CFTC),
            ('BofA Global Fund Manager Survey 현금 비중', None),
            ('BofA Bull & Bear', None),
            ('Goldman Panic', None),
            ('CNN Fear & Greed 원문', 'https://www.cnn.com/markets/fear-and-greed'),
            ('Zweig Breadth Thrust용 NYSE 상승·하락 원자료', None),
        ):
            add('추가 조사', label, None, source, status='not_run',
                reason='자동 수집 범위 밖이며 공개 원문을 직접 대조해야 함', source_kind='manual_research',
                note='주간 포지션·감마 모형에서 당일 매도 주체를 확정할 수 없음.' if source == CFTC else None)
        _currency_row(provider, calendar, session, cutoff, add)

    run('equity_drivers', '주식 급변·신용 불안 원문 조사', [why for _, why in (*equity, *credit_stress)],
        equity_rows, [key for key, _ in (*equity, *credit_stress)])

    def stress_rows():
        for series, label in (('DRTSCILM', '미국 은행 C&I 대출 기준 순긴축 비율'),
                              ('DRSDCILM', '미국 은행 C&I 대출 수요 순강화 비율')):
            row = _macro_row(provider, series, label, day, add, max_age=160,
                             scope='Fed SLOOS 분기 설문. 대기업·중기업에 관한 은행 응답 순비율.')
            row['sources'] = [row['source'], SLOOS]
        _sofr_row(provider, day, add)

    vix = {row['id'] for row in evidence if row.get('symbol') == '^VIX'}
    stress = [item for item in equity if item[0] in vix] + credit_stress
    run('financial_stress', '금융 스트레스 보완', [why for _, why in stress], stress_rows,
        [key for key, _ in stress])

    if unknown:
        investigations.append({'key': 'threshold_coverage', 'label': '급변 판단에 필요한 자료',
                               'status': 'unavailable', 'reason': '비교 가능 자료 미확인: ' + ', '.join(unknown),
                               'evidence_ids': [], 'trigger_evidence_ids': []})
    return investigations
