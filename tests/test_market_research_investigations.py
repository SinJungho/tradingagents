from datetime import date, timedelta
from types import SimpleNamespace

import exchange_calendars as xcals
import pandas as pd

from tradingagents.market_research_investigations import (
    CFTC_API,
    CFTC_SCHEDULE,
    ET,
    _auction_rows,
    _cftc_rows,
    _dated_release_text,
    _official_release_sources,
    _release_values,
    collect_investigations,
)


class Provider:
    def __init__(self, events=()):
        self.events = events
        self.macro_calls = []

    def intraday(self, symbol, day):
        return pd.DataFrame(
            {'Close': [100, 102, 108, 110, 999], 'Volume': [1, 2, 3, 4, 1000]},
            index=pd.DatetimeIndex([f'{day} {hour}' for hour in ('08:25', '08:40', '12:55', '16:55', '17:00')], tz=ET),
        )

    def macro(self, series, day):
        self.macro_calls.append(series)
        obs = day - timedelta(days=1)
        return {'value': 4, 'period': obs.isoformat(), 'vintage': obs.isoformat(), 'unit': 'Percent',
                'previous': 4.1, 'previous_period': (obs - timedelta(days=1)).isoformat()}

    def bls_calendar(self, day):
        return self.events

    def bea_calendar(self, day):
        return []

    def policy_calendar(self, day):
        return []

    def earnings_release(self, symbol, day):
        return {'filings': [
            {'accepted_at': f'{day}T20:01:00-05:00', 'url': 'https://www.sec.gov/Archives/edgar/future'},
        ]}


def add_to(evidence):
    def add(section, label, value, source, *, unit=None, period=None, published=None, status='available', reason=None, **extra):
        row = {'id': str(len(evidence) + 1), 'section': section, 'label': label, 'value': value,
               'source': source, 'unit': unit, 'observation_period': period, 'published_at': published,
               'status': status, 'reason': reason, **extra}
        evidence.append(row)
        return row
    return add


def investigate(provider, day, cutoff='20:00', *, index_return=0.5, vix_change=0.5, rates=1):
    calendar = xcals.get_calendar('XNYS')
    window = {'day': day, 'cutoff': f'{day}T{cutoff}:00-05:00'}
    evidence = [
        {'symbol': '^GSPC', 'id': 'E1', 'label': 'S&P 500', 'value': {'return_1d': index_return}},
        {'symbol': '^IXIC', 'id': 'E2', 'label': 'Nasdaq', 'value': {'return_1d': 0.5}},
        {'symbol': '^VIX', 'id': 'E3', 'label': 'VIX', 'change_points': vix_change,
         'value': {'return_1d': 20}, 'calculations': {'dates': ['2026-11-11', day], 'price_closes': [10, 17]}},
        {'series': 'DGS10', 'id': 'E4', 'label': 'Treasury', 'change_bp': rates, 'observation_period': day},
    ]
    output = collect_investigations(provider, window, calendar, evidence, add_to(evidence))
    return {row['key']: row for row in output}, evidence


def test_quiet_day_checks_daily_credit_but_skips_weekly_and_conditional_research():
    provider = Provider()
    investigations, evidence = investigate(provider, '2026-11-12', vix_change=None)

    for key in ('weekly_flows', 'release_reaction', 'rates', 'equity_drivers', 'financial_stress'):
        assert investigations[key]['status'] == 'not_run'
        assert not investigations[key]['required']
    assert investigations['credit']['required']
    assert provider.macro_calls == ['BAMLH0A0HYM2', 'BAMLC0A0CM']
    assert investigations['threshold_coverage']['status'] == 'unavailable'
    assert '^VIX' in investigations['threshold_coverage']['reason']

    es = next(row for row in evidence if row.get('symbol') == 'ES=F')
    assert es['value']['price'] == 110
    assert es['value']['volume_observed'] == 10
    assert es['value']['open_interest'] is None
    assert es['value']['rollover'] is None
    assert es['value']['contract_month'] is None
    assert es['status'] == 'partial'
    assert str(es['observed_at']).endswith('T17:00:00-05:00')


def test_early_close_last_weekday_opens_weekly_but_excludes_later_bars_and_filings():
    provider = Provider()
    investigations, evidence = investigate(provider, '2026-11-27', cutoff='13:00')
    assert '주의 마지막 거래일' in investigations['weekly_flows']['reason']
    assert investigations['weekly_flows']['status'] == 'partial'
    assert provider.macro_calls == ['BAMLH0A0HYM2', 'BAMLC0A0CM']
    es = next(row for row in evidence if row.get('symbol') == 'ES=F')
    assert es['value']['price'] == 108 and es['value']['volume_observed'] == 6
    assert not any('future' in row.get('source', '') for row in evidence)


def test_release_uses_only_completed_reaction_windows_and_missing_consensus():
    day = '2026-11-12'
    event = {'title': 'Consumer Price Index', 'scheduled_at': f'{day}T08:30:00-05:00',
             'source': 'https://www.bls.gov/'}
    investigations, evidence = investigate(Provider([event]), day, cutoff='08:40')
    assert investigations['release_reaction']['status'] == 'partial'
    assert '공식 일정 도래' in investigations['release_reaction']['reason']
    actual = next(row for row in evidence if row.get('label') == '미국 CPI 발표')
    assert actual['value']['pre_release_consensus'] is None
    assert actual['value']['actual_at_release'] is None
    assert actual['published_at'] is None
    unavailable = [row for row in evidence if '반응' in row.get('label', '')]
    assert len(unavailable) == 4 and all(row['value'] is None for row in unavailable)
    assert all(row['observed_at'] is None for row in unavailable)

    investigations, evidence = investigate(Provider([event]), day, cutoff='08:45')
    es = next(row for row in evidence if row.get('label') == '발표 직후 ES 연속 선물 반응')
    assert es['status'] == 'available' and round(es['value'], 6) == 2
    assert es['observed_at'].endswith('T08:45:00-05:00')

    investigations, _ = investigate(Provider([event]), day, cutoff='08:25')
    assert investigations['release_reaction']['status'] == 'not_run'


def test_thresholds_and_provider_failure_open_only_matching_investigations():
    provider = Provider()

    def failed(series, day):
        raise RuntimeError('provider failed')

    provider.macro = failed
    investigations, evidence = investigate(provider, '2026-11-12', index_return=-2, vix_change=5, rates=10)

    assert investigations['credit']['status'] == 'unavailable'
    assert investigations['credit']['trigger_evidence_ids'] == ['E1', 'E3', 'E4']
    assert investigations['rates']['trigger_evidence_ids'] == ['E4']
    assert investigations['equity_drivers']['trigger_evidence_ids'] == ['E1', 'E3']
    assert investigations['financial_stress']['trigger_evidence_ids'] == ['E3']
    assert investigations['weekly_flows']['status'] == 'not_run'
    assert all(row['value'] is None for row in evidence if ' OAS' in row.get('label', ''))
    flows = next(row for row in evidence if row.get('label', '').startswith('CTA·'))
    assert '당일 매도 주체' in flows['note'] and flows['status'] == 'not_run'
    assert investigations['equity_drivers']['required']
    assert next(row for row in evidence if row['label'] == 'Goldman Panic')['status'] == 'not_run'


def test_cftc_publication_cutoff_uses_previous_observation_before_friday_release(monkeypatch):
    day = date(2026, 11, 20)
    schedule = """<h3><strong>2026 Release Schedule</strong></h3>
    <table><tr><td>Month</td><td>Dates</td></tr><tr><td>November</td><td>13</td><td>20</td><td>30*</td></tr></table>"""
    positions = [{
        'report_date_as_yyyy_mm_dd': obs.isoformat() + 'T00:00:00.000',
        'cftc_contract_market_code': code, 'lev_money_positions_long': '12',
        'lev_money_positions_short': '15', 'lev_money_positions_spread': '2', 'open_interest_all': '50',
    } for obs in (date(2026, 11, 17), date(2026, 11, 10))
        for code in ('13874A', '209742', '043602')]

    def fetch(url, *_args, **_kwargs):
        assert url in (CFTC_API, CFTC_SCHEDULE)
        return SimpleNamespace(text=schedule, json=lambda: positions)

    monkeypatch.setattr('tradingagents.market_research_investigations._fetch', fetch)
    before, after = [], []
    _cftc_rows(day, pd.Timestamp('2026-11-20T15:29:59-05:00'), add_to(before))
    _cftc_rows(day, pd.Timestamp('2026-11-20T20:00:00-05:00'), add_to(after))
    assert before[0]['observation_period'] == '2026-11-10'
    assert after[0]['observation_period'] == '2026-11-17'
    assert after[0]['status'] == 'available'
    assert after[0]['value']['ES']['net'] == -3


def test_treasury_auction_fallback_excludes_same_day_results(monkeypatch):
    called = []

    def fetch(url, _agency, *, params):
        called.append((url.rsplit('/', 1)[-1], params['filter']))
        rows = []
        if url.endswith('/auctions_query'):
            rows = [{'auction_date': day, 'security_type': 'Note', 'security_term': '10-Year',
                     'high_yield': 4, 'bid_to_cover_ratio': 2.2} for day in ('2025-09-10', '2025-09-12')]
        return SimpleNamespace(json=lambda: {'data': rows, 'meta': {'total-count': len(rows)}})

    monkeypatch.setattr('tradingagents.market_research_investigations._fetch', fetch)
    evidence = []
    _auction_rows(date(2025, 9, 12), add_to(evidence))
    assert called == [
        ('treasury_securities_auctions_v2', 'comp_auction_close_date:gte:2025-09-05,comp_auction_close_date:lte:2025-09-11'),
        ('auctions_query', 'auction_date:gte:2025-09-05,auction_date:lte:2025-09-11'),
    ]
    assert [row['date'] for row in evidence[0]['value']] == ['2025-09-10']
    assert evidence[0]['status'] == 'partial'


def test_corrected_bls_archive_does_not_supply_actual_at_original_release(monkeypatch):
    def fetch(url, _agency, **_kwargs):
        if '/cpi_' not in url:
            return SimpleNamespace(status_code=404)
        return SimpleNamespace(status_code=200, content=(
            b'<pre>Embargoed until 8:30 a.m. ET. November 12, 2026. '
            b'This news release was corrected. '
            b'The Consumer Price Index for All Urban Consumers (CPI-U) rose 9.9 percent.</pre>'
        ))

    monkeypatch.setattr('tradingagents.market_research_investigations._fetch', fetch)
    monkeypatch.setattr('tradingagents.market_research_investigations._bea_release_url', lambda _: None)
    rows, errors = _official_release_sources(date(2026, 11, 12))
    assert rows['cpi'][1].hour == 8
    assert rows['cpi'][2] is None
    assert '최초 공개 값' in errors['cpi']


def test_original_bls_and_fomc_release_values_and_revisions():
    day = date(2025, 9, 5)
    page = ('Transmission of material in this news release is embargoed until USDL-25-1344 '
            '8:30 a.m. (ET) Friday, September 5, 2025. '
            'Total nonfarm payroll employment changed little (+22,000). '
            'The unemployment rate edged up to 4.3 percent. '
            'The change in total nonfarm payroll employment for June was revised down by 27,000, '
            'from +14,000 to -13,000, and the change for July was revised up by 6,000, from +73,000 to +79,000.')
    text, stamp = _dated_release_text(page, day)
    assert stamp.isoformat() == '2025-09-05T08:30:00-04:00'
    values = _release_values('employment', text)
    assert values['payroll_change'] == 22000 and values['unemployment_pct'] == 4.3
    assert values['payroll_revisions']['June']['revised'] == -13000
    assert _release_values('fomc', 'decided to raise the target range for the federal funds rate by '
                           '1/4 percentage point to 3-3/4 to 4 percent')['target_range_pct'] == [3.75, 4]
