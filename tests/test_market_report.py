"""Offline report contracts: calendar, arithmetic, provenance and graceful failures."""
import json
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
from typer.testing import CliRunner

from cli.main import app
from tradingagents import market_report as mr
from tradingagents.dataflows import market_report as market_data
from tradingagents.dataflows.market_report import PublicMarketData


@pytest.mark.parametrize(('now', 'day', 'close_hour'), [
    ('2026-11-12T19:59:59-05:00', '2026-11-11', 21),
    ('2026-11-12T20:00:00-05:00', '2026-11-12', 21),
    ('2026-11-14T21:00:00-05:00', '2026-11-13', 21),
    ('2026-11-26T21:00:00-05:00', '2026-11-25', 21),
    ('2026-11-27T19:59:00-05:00', '2026-11-25', 21),
    ('2026-11-27T20:00:00-05:00', '2026-11-27', 18),
    ('2026-03-09T20:00:00-04:00', '2026-03-09', 20),
    ('2026-11-02T20:00:00-05:00', '2026-11-02', 21),
    ('2026-07-03T20:00:00-04:00', '2026-07-02', 20),
    ('2026-04-03T20:00:00-04:00', '2026-04-02', 20),
    ('2025-01-09T20:00:00-05:00', '2025-01-08', 21),
])
def test_completed_session(now, day, close_hour):
    window, _ = mr.report_window(datetime.fromisoformat(now))
    assert window['day'] == day
    assert pd.Timestamp(window['close']).hour == close_hour
    assert pd.Timestamp(window['cutoff']).hour == 20
    assert pd.Timestamp(window['next_day']).date() > pd.Timestamp(day).date()


def test_naive_clock_rejected():
    with pytest.raises(ValueError):
        mr.report_window(datetime(2026, 11, 12))


def test_public_market_data_prefers_spy_and_falls_back_to_wikipedia(monkeypatch):
    spy = SimpleNamespace(tickers=("AAA",), source=mr.SPY_HOLDINGS_SOURCE)
    wikipedia = SimpleNamespace(tickers=("BBB",), source="https://en.wikipedia.org/wiki/sp500")
    fetch_spy = Mock(return_value=spy)
    fetch_wikipedia = Mock(return_value=wikipedia)
    monkeypatch.setattr(market_data, "fetch_spy_holdings_universe", fetch_spy)
    monkeypatch.setattr(market_data, "fetch_index_universe", fetch_wikipedia)

    assert PublicMarketData().universe() is spy
    fetch_wikipedia.assert_not_called()

    fetch_spy.side_effect = ValueError("synthetic invalid workbook")
    assert PublicMarketData().universe() is wikipedia
    fetch_wikipedia.assert_called_once_with("sp500")


@pytest.mark.parametrize(('symbol', 'expected'), [
    ('BRK.B', 'BRK-B'),
    ('BF.B', 'BF-B'),
    ('DX-Y.NYB', 'DX-Y.NYB'),
    ('^GSPC', '^GSPC'),
    ('CL=F', 'CL=F'),
    ('AAPL', 'AAPL'),
])
def test_ticker_converts_only_class_share_symbols(monkeypatch, symbol, expected):
    ticker = object()
    requested = []
    monkeypatch.setattr(market_data.yf, 'Ticker', lambda value: requested.append(value) or ticker)

    assert PublicMarketData().ticker(symbol) is ticker
    assert requested == [expected]


def test_return_alignment_uses_close_and_preserves_missing_sessions():
    dates = pd.bdate_range('2026-10-01', periods=21)
    frame = pd.DataFrame({'Close': range(200, 221), 'Adj Close': range(100, 121)}, index=dates)
    values, _ = mr.price_stats(frame, dates)
    assert values['close'] == 220
    assert values['return_20d'] == pytest.approx(10)
    assert values['return_5d'] == pytest.approx((220 / 215 - 1) * 100)
    frame = frame.drop(dates[-3])
    values, _ = mr.price_stats(frame, dates)
    assert values['return_1d'] is not None
    assert values['return_5d'] is None
    assert values['return_20d'] is None
    values, _ = mr.price_stats(frame.drop(columns='Adj Close'), dates)
    assert values['return_1d'] == pytest.approx((220 / 219 - 1) * 100)
    values, closes = mr.price_stats(None, dates, fallback_close=99)
    assert values['close'] == 99 and values['return_1d'] is None
    assert closes.iloc[-1] == 99


def test_same_day_split_blocks_intraday_price_mixing():
    from tradingagents.market_report import has_split_on_day

    day = datetime(2026, 11, 12).date()
    frame = pd.DataFrame({'Close': [100.], 'Stock Splits': [4.]}, index=pd.DatetimeIndex([day]))
    assert has_split_on_day(frame, day)
    frame['Stock Splits'] = 0.
    assert not has_split_on_day(frame, day)


def test_breadth_denominators_are_explicit():
    up = pd.Series(range(1, 201), dtype=float)
    down = up[::-1].reset_index(drop=True)
    flat = pd.Series([100.] * 200)
    missing = pd.Series([float('nan')] * 200)
    result = mr.breadth_stats({'A': up, 'B': down, 'C': flat, 'D': missing})
    assert result['constituents'] == 4
    assert result['success_1'] == result['success_200'] == 3
    assert result['excluded_50'] == 1
    assert result['advancing_pct'] == pytest.approx(100 / 3)
    assert result['above_ma200_pct'] == pytest.approx(100 / 3)
    assert mr.breadth_stats({'D': missing})['advancing_pct'] is None


def test_breadth_short_history_is_available_but_query_failure_is_partial():
    provider = FakePublicData()
    provider.universe = lambda: SimpleNamespace(
        tickers=('AAA',), source='https://example.com/members',
        as_of='2026-11-01', as_of_label='membership as of')
    original = provider.daily

    def short_history(symbol, day):
        frame = original(symbol, day)
        return frame.iloc[-3:] if symbol == 'AAA' else frame

    provider.daily = short_history
    report = mr.collect_report(provider, provider.now)
    breadth = next(row for row in report['evidence'] if row['label'] == '현재 S&P 500 구성 종목 표본의 시장 폭')
    assert breadth['status'] == 'available'
    assert breadth['value']['excluded_50'] == breadth['value']['excluded_200'] == 1
    assert '이력 부족 종목은 해당 구간 분모에서 제외' in breadth['note']
    assert '50일 1개' in breadth['note'] and '200일 1개' in breadth['note']

    provider = FakePublicData()
    provider.universe = lambda: SimpleNamespace(
        tickers=('AAA',), source='https://example.com/members',
        as_of='2026-11-01', as_of_label='membership as of')
    original = provider.daily

    def quote_failure(symbol, day):
        if symbol == 'AAA':
            raise RuntimeError('synthetic quote failure')
        return original(symbol, day)

    provider.daily = quote_failure

    def intraday_failure(symbol, day):
        if symbol == 'AAA':
            raise RuntimeError('synthetic quote failure')
        return FakePublicData.intraday(provider, symbol, day)

    provider.intraday = intraday_failure
    report = mr.collect_report(provider, provider.now)
    breadth = next(row for row in report['evidence'] if row['label'] == '현재 S&P 500 구성 종목 표본의 시장 폭')
    assert breadth['status'] == 'partial'
    assert breadth['close_source_by_symbol']['AAA'] == 'unavailable'


class FakePublicData:
    def __init__(self):
        self.now = datetime.fromisoformat('2026-11-12T20:30:00-05:00')
        window, calendar = mr.report_window(self.now)
        self.dates = calendar.sessions_in_range('2025-09-01', window['day'])
        self.calls = []

    def daily(self, symbol, day):
        self.calls.append(('daily', symbol))
        values = [100 + i for i in range(len(self.dates))]
        return pd.DataFrame({'Close': values, 'Adj Close': values}, index=self.dates)

    def universe(self):
        return SimpleNamespace(tickers=('AAA', 'BBB', 'CCC'), source='https://example.com/members',
                               as_of='2026-11-01', as_of_label='membership as of')

    def macro(self, series, day):
        return {'value': 4.2, 'period': '2026-11-10', 'unit': 'Percent', 'frequency': 'Daily',
                'vintage': (day - timedelta(days=1)).isoformat()}

    def intraday(self, symbol, day):
        index = pd.DatetimeIndex([f'{day} {hour}' for hour in ('15:55', '16:00', '19:55', '20:00')], tz=mr.ET)
        return pd.DataFrame({'Close': [100., 101., 102., 999.]}, index=index)

    def news(self, symbol):
        return [{'title': 'Confirmed catalyst', 'link': 'https://example.com/news', 'publisher': 'Example',
                 'pub_date': datetime.fromisoformat('2026-11-12T18:00:00-05:00')},
                {'title': 'Future secret', 'link': 'https://example.com/future', 'publisher': 'Example',
                 'pub_date': datetime.fromisoformat('2026-11-12T20:01:00-05:00')},
                {'title': 'Undated secret', 'link': 'https://example.com/undated', 'publisher': 'Example', 'pub_date': None}]

    def calendar(self, day):
        return [
            {'release_name': 'Producer Price Index', 'release_id': 46, 'date': day.isoformat()},
            {'release_name': 'New Residential Construction', 'release_id': 93, 'date': day.isoformat()},
            {'release_name': 'New Residential Sales', 'release_id': 97, 'date': day.isoformat()},
            {'release_name': 'Gross Domestic Product', 'release_id': 53, 'date': day.isoformat()},
        ]

    def census_calendar(self, day):
        source = f'https://www.census.gov/economic-indicators/calendar-listview-{day.year}.html'
        return [
            {'title': 'New Residential Construction', 'scheduled_at': f'{day}T08:30:00-05:00',
             'source': source, 'related_assets': ['미국 주가지수', '미 국채', '달러']},
            {'title': 'New Residential Sales', 'scheduled_at': f'{day}T10:00:00-05:00',
             'source': source, 'related_assets': ['미국 주가지수', '미 국채', '달러']},
        ]

    def bea_calendar(self, day):
        return [{'title': 'Gross Domestic Product', 'scheduled_at': f'{day}T08:30:00-05:00',
                 'source': 'https://www.bea.gov/news/schedule/full',
                 'source_api': 'https://apps.bea.gov/API/signup/release_dates.json',
                 'related_assets': ['미국 주가지수', '미 국채', '달러']}]

    def bls_calendar(self, day):
        return [{'title': 'Producer Price Index', 'scheduled_at': f'{day}T08:30:00-05:00',
                 'source': 'https://www.bls.gov/schedule/news_release/bls.ics',
                 'related_assets': ['미국 주가지수', '미 국채', '달러']}]

    def policy_calendar(self, day):
        return [{'title': 'Synthetic speech', 'scheduled_at': f'{day}T14:00:00-05:00', 'source': 'https://example.com/policy', 'time_label': '2:00 p.m.'}]

    def earnings_release(self, symbol, day):
        source_api = 'https://data.sec.gov/submissions/CIK0000000001.json'
        filings = ([{'filing_date': day.isoformat(), 'accepted_at': f'{day}T16:30:00-05:00',
                    'accession_number': '0000000001-26-000024', 'primary_document': 'aapl-20261112.htm',
                    'url': 'https://www.sec.gov/Archives/edgar/data/1/000000000126000024/aapl-20261112.htm'}]
                   if symbol == 'AAPL' else [])
        return {'source_api': source_api, 'filings': filings}

    def earnings(self, symbol):
        return pd.DataFrame({'Reported EPS': [1.25, 9999.], 'EPS Estimate': [1., 1000.],
                             'Surprise(%)': [25., None]},
                            index=pd.DatetimeIndex(['2026-11-12T16:05:00-05:00',
                                                    '2026-11-13T16:05:00-05:00']))


@pytest.fixture
def report():
    provider = FakePublicData()
    return mr.collect_report(provider, provider.now)


def test_collection_bounds_sources_and_dedup(report):
    rows = report['evidence']
    dxy = next(r for r in rows if r['label'] == '미 달러 지수(ICE DXY)')
    broad_dollar = next(r for r in rows if r['label'] == '무역가중 미 달러 지수(광의, 명목)')
    assert dxy['unit'] == '지수'
    assert dxy['source'] == 'https://finance.yahoo.com/quote/DX-Y.NYB/'
    assert broad_dollar['source'] == 'https://fred.stlouisfed.org/series/DTWEXBGS'
    assert dxy['label'] != broad_dollar['label']
    assert dxy['source'] != broad_dollar['source']
    news = [r for r in rows if r['label'] == 'Confirmed catalyst']
    assert len(news) == 1
    assert len(news[0]['symbols']) > 1
    encoded = json.dumps(report)
    assert 'Future secret' not in encoded and 'Undated secret' not in encoded
    # The sentinel serializes as 9999.0; bare '9999' also matches retrieved_at microseconds.
    assert '9999.0' not in encoded
    futures = next(r for r in rows if r['label'].startswith('ES=F'))
    assert futures['value'] == {'regular_close': 100., 'post_price': 102., 'change_pct': pytest.approx(2)}
    assert pd.Timestamp(futures['observed_at']) <= pd.Timestamp(report['window']['cutoff'])
    sectors = [r for r in rows if r['section'] == '업종']
    assert len(sectors) == 11
    assert all(r['value']['relative_5d_pp'] == 0 for r in sectors)
    assert all(r['value']['rank_1d'] == 1 for r in sectors)
    assert any(r['label'] == 'Producer Price Index' for r in rows)
    official = next(r for r in rows if r['label'] == 'AAPL 8-K Item 2.02 실적 공시')
    assert official['source_kind'] == 'official' and official['source'].startswith('https://www.sec.gov/Archives/')
    assert official['published_at'] == '2026-11-12T16:30:00-05:00'
    yahoo_eps = next(r for r in rows if r['label'] == 'AAPL 실적 EPS·예상치 (Yahoo 2차 출처)')
    assert yahoo_eps['source_kind'] == 'secondary'
    assert yahoo_eps['source'] == 'https://finance.yahoo.com/calendar/earnings?symbol=AAPL'
    assert yahoo_eps['value']['surprise_pct'] == pytest.approx(25.)
    assert 'abs(eps_estimate)' in yahoo_eps['calculation']
    assert '서프라이즈 계산식:' in yahoo_eps['note']
    summary = next(r for r in rows if r['label'] == '표본 실적 공시 확인')
    assert summary['status'] == 'available'
    assert summary['value'] == {'checked': list(mr.COMPANIES), 'with_8k_2_02': ['AAPL'], 'sec_failed': []}
    assert not any(r['label'].startswith(('MSFT ', 'NVDA ', 'AMZN ', 'GOOGL ', 'META ', 'TSLA '))
                   and ('8-K Item 2.02' in r['label'] or 'EPS·예상치' in r['label']) for r in rows)
    for row in rows:
        assert {'value', 'unit', 'observation_period', 'published_at', 'retrieved_at', 'source', 'status'} <= row.keys()


def test_no_earnings_day_has_only_available_sample_summary():
    provider = FakePublicData()
    provider.earnings_release = lambda symbol, day: {
        'source_api': 'https://data.sec.gov/submissions/CIK0000000001.json', 'filings': []}
    report = mr.collect_report(provider, provider.now)
    rows = [row for row in report['evidence'] if row['section'] == '기업·실적']
    summary = next(row for row in rows if row['label'] == '표본 실적 공시 확인')
    per_ticker_earnings = [row for row in rows if row['label'] != summary['label']
                           and ('8-K Item 2.02' in row['label'] or 'Yahoo 실적 EPS' in row['label']
                                or 'EPS·예상치' in row['label'] or '가이던스' in row['label'])]
    assert summary['status'] == 'available'
    assert summary['value'] == {'checked': list(mr.COMPANIES), 'with_8k_2_02': [], 'sec_failed': []}
    assert not [row for row in per_ticker_earnings if row['status'] != 'available']
    assert not per_ticker_earnings


def test_successful_empty_news_and_schedules_are_none_found_and_not_warnings():
    provider = FakePublicData()
    provider.news = lambda symbol: []
    provider.calendar = lambda day: []
    provider.census_calendar = lambda day: []
    provider.bea_calendar = lambda day: []
    provider.bls_calendar = lambda day: []
    provider.policy_calendar = lambda day: []
    provider.earnings = lambda symbol: pd.DataFrame()
    report = mr.collect_report(provider, provider.now)
    rows = report['evidence']
    empty_labels = ('^GSPC 뉴스', 'FRED 선별 미국 주요 발표', 'Census 공식 일정 표본',
                    'BEA 공식 일정 표본', 'BLS 공식 일정 표본', 'Fed 정책 일정')
    none_rows = [row for row in rows if row['label'] in empty_labels]
    assert len(none_rows) == len(empty_labels)
    assert all(row['status'] == 'none_found' for row in none_rows)
    warnings = mr.quality_warnings(report)
    assert not any(any(warning.startswith(row['id'] + ' ') for warning in warnings) for row in none_rows)
    assert not any('DOL' in row['label'] for row in rows)
    earnings = next(row for row in rows if row['label'] == '표본 다음 거래일 실적 일정 확인')
    assert earnings['status'] == 'available'
    assert earnings['value'] == {'checked': list(mr.COMPANIES), 'scheduled': [], 'failed': []}
    markdown = mr.render_markdown(report)
    none_count = sum(row['status'] == 'none_found' for row in rows)
    assert f'해당 없음 {none_count}' in markdown
    assert '상태: 해당 없음' in markdown


def test_news_and_calendar_query_failures_remain_unavailable_and_warn():
    provider = FakePublicData()
    provider.news = lambda symbol: (_ for _ in ()).throw(RuntimeError('synthetic news failure'))
    provider.calendar = lambda day: (_ for _ in ()).throw(RuntimeError('synthetic calendar failure'))
    report = mr.collect_report(provider, provider.now)
    news = next(row for row in report['evidence'] if row['label'] == '^GSPC 뉴스')
    calendar = next(row for row in report['evidence'] if row['label'] == 'FRED 선별 미국 주요 발표')
    warnings = mr.quality_warnings(report)
    assert news['status'] == calendar['status'] == 'unavailable'
    assert any(warning.startswith(news['id'] + ' ') for warning in warnings)
    assert any(warning.startswith(calendar['id'] + ' ') for warning in warnings)


@pytest.mark.parametrize(('failures', 'expected_status'), [
    ((), 'available'),
    (('MSFT',), 'partial'),
    (tuple(mr.COMPANIES), 'unavailable'),
])
def test_next_day_earnings_schedule_summary_statuses(failures, expected_status):
    provider = FakePublicData()

    def earnings(symbol):
        if symbol in failures:
            raise RuntimeError('synthetic earnings failure')
        if symbol == 'AAPL':
            return pd.DataFrame(index=pd.DatetimeIndex(['2026-11-13T09:00:00-05:00']))
        return pd.DataFrame()

    provider.earnings = earnings
    report = mr.collect_report(provider, provider.now)
    summary = next(row for row in report['evidence'] if row['label'] == '표본 다음 거래일 실적 일정 확인')
    scheduled = ['AAPL'] if 'AAPL' not in failures else []
    assert summary['status'] == expected_status
    assert summary['value'] == {'checked': list(mr.COMPANIES), 'scheduled': scheduled,
                                'failed': list(failures)}
    assert ('AAPL 실적 예정' in [row['label'] for row in report['evidence']]) == bool(scheduled)


def test_partial_sec_failure_is_recorded_in_sample_summary():
    provider = FakePublicData()
    original = provider.earnings_release

    def earnings_release(symbol, day):
        if symbol == 'MSFT':
            raise RuntimeError('synthetic SEC failure')
        return original(symbol, day)

    provider.earnings_release = earnings_release
    report = mr.collect_report(provider, provider.now)
    summary = next(row for row in report['evidence'] if row['label'] == '표본 실적 공시 확인')
    assert summary['status'] == 'partial'
    assert summary['reason'] == 'SEC 조회 실패 종목: MSFT'
    assert summary['value']['with_8k_2_02'] == ['AAPL']
    assert summary['value']['sec_failed'] == ['MSFT']
    assert any(row['label'] == 'AAPL 8-K Item 2.02 실적 공시' for row in report['evidence'])


def test_missing_sector_not_ranked_and_no_repeated_daily():
    provider = FakePublicData()
    original = provider.daily
    def daily(symbol, day):
        if symbol == 'XLC':
            raise RuntimeError('sensitive raw response')
        return original(symbol, day)
    provider.daily = daily
    report = mr.collect_report(provider, provider.now)
    row = next(r for r in report['evidence'] if r['label'].startswith('커뮤니케이션'))
    assert row['value']['close'] == 100
    assert row['value']['return_1d'] is None
    assert row['close_source'] == 'same_day_5m_regular_close_proxy'
    assert row['status'] == 'partial'
    assert 'sensitive' not in json.dumps(report)
    assert len(provider.calls) == len(set(provider.calls))


def test_intraday_close_proxy_fills_sector_and_breadth_with_provenance():
    provider = FakePublicData()
    original = provider.daily
    missing_today = {'XLC', 'AAA', 'BBB', 'CCC'}

    def daily(symbol, day):
        frame = original(symbol, day)
        if symbol in missing_today:
            frame['Close'] = 100.
            frame.loc[pd.Timestamp(day), 'Close'] = float('nan')
        return frame

    provider.daily = daily
    report = mr.collect_report(provider, provider.now)
    sector = next(r for r in report['evidence'] if r['label'].startswith('커뮤니케이션'))
    assert sector['value']['close'] == 100
    assert sector['value']['return_1d'] == pytest.approx(0)
    assert sector['status'] == 'partial'
    assert sector['close_source'] == 'same_day_5m_regular_close_proxy'
    assert pd.Timestamp(sector['observed_at']) == pd.Timestamp('2026-11-12T16:00:00-05:00')

    breadth = next(r for r in report['evidence'] if r['label'] == '현재 S&P 500 구성 종목 표본의 시장 폭')
    assert breadth['value']['success_1'] == 3
    assert breadth['intraday_proxy_symbols'] == ['AAA', 'BBB', 'CCC']
    assert all(breadth['close_source_by_symbol'][s] == 'same_day_5m_regular_close_proxy'
               for s in ('AAA', 'BBB', 'CCC'))


def test_breadth_marks_spy_proxy_date_and_wikipedia_fallback_unknown():
    provider = FakePublicData()
    provider.universe = lambda: SimpleNamespace(
        tickers=("AAA", "BBB", "CCC"), source=mr.SPY_HOLDINGS_SOURCE,
        as_of="2026-11-11", as_of_label="holdings as of",
    )

    report = mr.collect_report(provider, provider.now)
    spy_breadth = next(row for row in report["evidence"] if row["source"] == mr.SPY_HOLDINGS_SOURCE)

    assert spy_breadth["source_kind"] == "etf_holdings_proxy"
    assert spy_breadth["membership_as_of"] == "2026-11-11"
    assert "공식 S&P 500 지수 구성 아님" in spy_breadth["label"]
    markdown = mr.render_markdown(report)
    assert "구성 기준일: 2026-11-11" in markdown
    assert "SPY ETF 보유 종목 대용치이며 공식 S&P 500 지수 구성 목록이 아님" in markdown

    provider.universe = lambda: SimpleNamespace(
        tickers=("AAA", "BBB", "CCC"),
        source="https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        as_of="2026-11-11", as_of_label="membership as of",
    )
    fallback_report = mr.collect_report(provider, provider.now)
    fallback = next(row for row in fallback_report["evidence"] if "wikipedia.org" in row["source"])

    assert fallback["source_kind"] == "secondary"
    assert fallback["membership_as_of"] is None
    assert "구성 기준일 미확인" in fallback["note"]
    assert "Wikipedia 현재 구성표 대체 자료; 구성 기준일 미확인" in mr.render_markdown(fallback_report)


def test_all_vendor_failures_still_preserve_structure(tmp_path):
    provider = Mock(spec=FakePublicData)
    for name in ('daily', 'universe', 'macro', 'intraday', 'news', 'calendar', 'census_calendar',
                 'bea_calendar', 'bls_calendar', 'earnings', 'earnings_release', 'policy_calendar'):
        getattr(provider, name).side_effect = RuntimeError('secret credential')
    report = mr.collect_report(provider, datetime.fromisoformat('2026-11-12T20:30:00-05:00'))
    mr.write_narrative(report, llm=Mock(invoke=Mock(side_effect=RuntimeError('llm key'))))
    path = mr.save_report(report, tmp_path)
    markdown = (path / 'report.md').read_text()
    for section in mr.SECTIONS:
        assert f'## {section}' in markdown
    assert '불완전 보고서' in markdown and 'LLM 해석 실패' in markdown
    assert 'secret credential' not in markdown and 'llm key' not in markdown
    summary = next(row for row in report['evidence'] if row['label'] == '표본 실적 공시 확인')
    assert summary['status'] == 'unavailable'
    assert summary['value']['sec_failed'] == list(mr.COMPANIES)
    assert len(list(path.iterdir())) == 3


def test_html_tables_links_toc_and_escaping(report, tmp_path):
    report['evidence'][0]['label'] = '<script>alert(1)</script>'
    first = mr.save_report(report, tmp_path)
    second = mr.save_report(report, tmp_path)
    assert first != second
    html = (first / 'report.html').read_text()
    assert '<table>' in html and 'href="#section-9"' in html
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert 'href="https://finance.yahoo.com/' in html
    markdown = (first / 'report.md').read_text()
    assert '자료 상태: 확인' in markdown and '부분·미확인 항목:' in markdown
    assert '서프라이즈 계산식:' in markdown and r'surprise\_pct' in markdown
    assert '제한: 확인 불가' not in markdown
    saved = json.loads((first / 'evidence.json').read_text())
    assert saved['window'] == report['window']
    assert saved['quality_warnings'] == mr.quality_warnings(report)


def test_fake_llm_evidence_validation(report):
    valid = next(e['id'] for e in report['evidence'] if e['status'] == 'available')
    partial = next(e for e in report['evidence'] if e['section'] == '업종')
    partial['status'] = 'partial'
    partial['reason'] = 'synthetic close proxy'
    llm = Mock(invoke=Mock(return_value=SimpleNamespace(content=json.dumps([
        {'section': '핵심 요약', 'text': '해석: 확인된 가격 흐름이며 원인은 미확인입니다.', 'evidence_ids': [partial['id']]}]))))
    mr.write_narrative(report, llm=llm)
    assert report['llm_status'] == 'available'
    prompt = json.loads(llm.invoke.call_args.args[0][1][1])
    assert any(item['id'] == partial['id'] and item['status'] == 'partial' for item in prompt['evidence'])
    assert all('calculations' not in item for item in prompt['evidence'])
    llm.invoke.return_value.content = json.dumps([{'section': '핵심 요약', 'text': '99% 상승 전망', 'evidence_ids': [valid]}])
    report['narrative'] = []
    mr.write_narrative(report, llm=llm)
    assert report['llm_status'] == 'failed' and not report['narrative']
    assert any('근거 연결' in w for w in mr.quality_warnings(report))


def test_future_macro_rejected_and_stale_reported():
    provider = FakePublicData()
    provider.macro = lambda series, day: {'value': 1., 'period': '2026-11-13', 'vintage': '2026-11-12', 'unit': '%', 'frequency': 'Daily'}
    report = mr.collect_report(provider, provider.now)
    assert all(e['status'] == 'unavailable' for e in report['evidence'] if e['source'].startswith('https://fred.stlouisfed.org/series/'))
    provider.macro = lambda series, day: {'value': 1., 'period': '2020-01-01', 'vintage': '2026-11-11', 'unit': '%', 'frequency': 'Daily'}
    report = mr.collect_report(provider, provider.now)
    assert any(e['status'] == 'stale' for e in report['evidence'])


def test_provider_cache_includes_failures():
    provider = PublicMarketData()
    fetch = Mock(return_value=123)
    assert provider._once(('key',), fetch) == provider._once(('key',), fetch) == 123
    assert fetch.call_count == 1
    broken = Mock(side_effect=RuntimeError('secret'))
    for _ in range(2):
        with pytest.raises(ValueError, match='RuntimeError'):
            provider._once(('bad',), broken)
    assert broken.call_count == 1


def test_dtwexbgs_macro_uses_synthetic_fred_metadata(monkeypatch):
    day = datetime(2026, 11, 12).date()
    monkeypatch.setattr(market_data.fred, '_fred_today', lambda: '2026-11-13')

    def request(endpoint, params):
        if endpoint == 'series':
            return {'seriess': [{'units': 'Index Jan 2006=100, Not Seasonally Adjusted', 'frequency': 'Daily'}]}
        assert endpoint == 'series/observations'
        assert params['realtime_start'] == '2026-11-11'
        return {'observations': [{'date': '2026-11-06', 'value': '121.8803'}]}

    monkeypatch.setattr(market_data.fred, '_request', request)
    data = PublicMarketData().macro('DTWEXBGS', day)
    assert data == {
        'value': 121.8803,
        'period': '2026-11-06',
        'unit': 'Index Jan 2006=100, Not Seasonally Adjusted',
        'frequency': 'Daily',
        'vintage': '2026-11-11',
    }


def test_dtwexbgs_is_distinct_and_survives_yahoo_dxy_failure():
    provider = FakePublicData()
    provider.macro = lambda series, day: {
        'value': 121.8803, 'period': '2026-11-06',
        'unit': 'Index Jan 2006=100, Not Seasonally Adjusted',
        'frequency': 'Daily', 'vintage': (day - timedelta(days=1)).isoformat(),
    }
    original_intraday = provider.intraday

    def intraday(symbol, day):
        if symbol == 'DX-Y.NYB':
            raise RuntimeError('synthetic Yahoo failure')
        return original_intraday(symbol, day)

    provider.intraday = intraday
    report = mr.collect_report(provider, provider.now)
    dxy = next(row for row in report['evidence'] if row['label'] == '미 달러 지수(ICE DXY)')
    broad = next(row for row in report['evidence'] if row['label'] == '무역가중 미 달러 지수(광의, 명목)')
    assert dxy['status'] == 'unavailable'
    assert dxy['unit'] is None
    assert broad['status'] == 'available'
    assert broad['value'] == 121.8803
    assert broad['unit'] == 'Index Jan 2006=100, Not Seasonally Adjusted'
    assert broad['observation_period'] == '2026-11-06'
    assert broad['vintage'] == '2026-11-11'
    assert broad['frequency'] == 'Daily'
    assert broad['source'] == 'https://fred.stlouisfed.org/series/DTWEXBGS'
    assert dxy['label'] != broad['label']
    assert dxy['source'] != broad['source']


def test_dtwexbgs_weekly_h10_delay_uses_existing_max_age():
    provider = FakePublicData()
    provider.now = datetime.fromisoformat('2026-11-13T20:30:00-05:00')

    def macro_for(period):
        provider.macro = lambda series, day: {
            'value': 121.8803, 'period': period,
            'unit': 'Index Jan 2006=100, Not Seasonally Adjusted',
            'frequency': 'Daily', 'vintage': (day - timedelta(days=1)).isoformat(),
        }
        report = mr.collect_report(provider, provider.now)
        return next(row for row in report['evidence'] if row['label'] == '무역가중 미 달러 지수(광의, 명목)')

    within_week = macro_for('2026-11-06')
    beyond_max_age = macro_for('2026-11-02')
    assert within_week['status'] == 'available'
    assert within_week['observation_period'] == '2026-11-06'
    assert beyond_max_age['status'] == 'stale'
    assert beyond_max_age['observation_period'] == '2026-11-02'


def test_sec_earnings_release_uses_eastern_acceptance_date(monkeypatch):
    from tradingagents.dataflows.vendors import sec_edgar

    payload = {'filings': {'recent': {
        'form': ['8-K', '8-K', '10-Q'],
        'items': ['2.02,9.01', '2.02', '2.02'],
        'filingDate': ['2026-11-12', '2026-11-13', '2026-11-12'],
        'acceptanceDateTime': ['2026-11-13T00:30:23.000Z', '2026-11-13T05:30:23.000Z',
                               '2026-11-13T00:30:23.000Z'],
        'accessionNumber': ['0000000001-26-000024', '0000000001-26-000025', '0000000001-26-000026'],
        'primaryDocument': ['aapl-20261112.htm', 'aapl-later.htm', 'aapl-quarterly.htm'],
    }}}
    monkeypatch.setattr(sec_edgar, 'cik_for', Mock(return_value='0000000001'))
    fetch = Mock(return_value=payload)
    monkeypatch.setattr(sec_edgar, '_fetch_json', fetch)
    provider = PublicMarketData()

    result = provider.earnings_release('AAPL', date(2026, 11, 12))
    assert result['source_api'] == 'https://data.sec.gov/submissions/CIK0000000001.json'
    assert len(result['filings']) == 1
    assert result['filings'][0]['accepted_at'] == '2026-11-12T19:30:23-05:00'
    assert result['filings'][0]['url'] == ('https://www.sec.gov/Archives/edgar/data/1/'
                                           '000000000126000024/aapl-20261112.htm')
    assert provider.earnings_release('AAPL', date(2026, 11, 12)) == result
    assert fetch.call_count == 1


def test_sec_earnings_release_without_item_202(monkeypatch):
    from tradingagents.dataflows.vendors import sec_edgar

    monkeypatch.setattr(sec_edgar, 'cik_for', lambda symbol: '0000000001')
    monkeypatch.setattr(sec_edgar, '_fetch_json', lambda url: {'filings': {'recent': {
        'form': ['8-K'], 'items': ['9.01'], 'filingDate': ['2026-11-12'],
        'acceptanceDateTime': ['2026-11-13T00:30:23.000Z'],
        'accessionNumber': ['0000000001-26-000024'], 'primaryDocument': ['aapl-20261112.htm'],
    }}})
    result = PublicMarketData().earnings_release('AAPL', date(2026, 11, 12))
    assert result['filings'] == []


def test_sec_earnings_release_failure_is_cached_and_sanitized(monkeypatch):
    from tradingagents.dataflows import market_report as data
    from tradingagents.dataflows.vendors import sec_edgar

    monkeypatch.setattr(sec_edgar, 'cik_for', lambda symbol: '0000000001')
    fetch = Mock(side_effect=RuntimeError('synthetic private response'))
    monkeypatch.setattr(sec_edgar, '_fetch_json', fetch)
    provider = PublicMarketData()

    for _ in range(2):
        with pytest.raises(data.PublicDataError) as caught:
            provider.earnings_release('AAPL', date(2026, 11, 12))
        assert str(caught.value) == 'RuntimeError'
        assert 'synthetic private response' not in str(caught.value)
    assert fetch.call_count == 1


def test_yahoo_partial_eps_does_not_compute_surprise():
    provider = FakePublicData()
    provider.earnings = lambda symbol: pd.DataFrame(
        {'Reported EPS': [1.25], 'EPS Estimate': [float('nan')], 'Surprise(%)': [25.]},
        index=pd.DatetimeIndex(['2026-11-12T16:05:00-05:00']))
    report = mr.collect_report(provider, provider.now)
    row = next(r for r in report['evidence'] if r['label'] == 'AAPL 실적 EPS·예상치 (Yahoo 2차 출처)')
    assert row['value']['reported_eps'] == pytest.approx(1.25)
    assert row['value']['eps_estimate'] is None and row['value']['surprise_pct'] is None
    assert row['status'] == 'partial' and row['calculation'] is None


def test_official_filing_without_yahoo_day_row_has_partial_eps_only_for_filer():
    provider = FakePublicData()
    provider.earnings = lambda symbol: pd.DataFrame(
        {'Reported EPS': [None], 'EPS Estimate': [None], 'Surprise(%)': [None]},
        index=pd.DatetimeIndex(['2026-11-13T16:05:00-05:00']))
    report = mr.collect_report(provider, provider.now)
    rows = [row for row in report['evidence'] if row['label'].endswith('EPS·예상치 (Yahoo 2차 출처)')]
    assert len(rows) == 1 and rows[0]['label'].startswith('AAPL ')
    assert rows[0]['status'] == 'partial'
    assert rows[0]['value'] == {'reported_eps': None, 'eps_estimate': None, 'surprise_pct': None}


def test_cli_no_llm_and_help(monkeypatch, report, tmp_path):
    monkeypatch.setattr(mr, 'collect_report', lambda: report)
    llm = Mock(side_effect=AssertionError('No real LLM'))
    monkeypatch.setattr(mr, 'write_narrative', llm)
    runner = CliRunner()
    result = runner.invoke(app, ['market-report', '--no-llm', '--output-dir', str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert '2026-11-12' in result.output and '불완전 보고서' in result.output
    llm.assert_not_called()
    assert 'market-report' in runner.invoke(app, ['--help']).output


def test_fed_policy_calendar_time_and_layout():
    from tradingagents.dataflows.market_report import fed_events

    html = '''<div class="row"><div class="col-xs-2"><p>2:00 p.m.</p></div>
    <div class="col-xs-7"><p>Speech</p><p><em>Inflation outlook</em></p></div>
    <div class="col-xs-3"><p>13</p></div></div>
    <div class="row"><div class="col-xs-2">TBA</div><div class="col-xs-7">Meeting</div>
    <div class="col-xs-3">13–14</div></div>'''
    events = fed_events(html, datetime(2026, 11, 13).date(), 'https://example.com/fed')
    assert events[0]['scheduled_at'] == '2026-11-13T14:00:00-05:00'
    assert events[1]['scheduled_at'] is None
    assert fed_events(html, datetime(2026, 11, 20).date(), 'https://example.com/fed') == []
    with pytest.raises(ValueError):
        fed_events('<div>Layout changed</div>', datetime(2026, 11, 13).date(), 'https://example.com/fed')


def test_us_calendar_sources_filter_noise_and_convert_bea_time(monkeypatch):
    from tradingagents.dataflows import market_report as data

    day = datetime(2026, 11, 13).date()
    monkeypatch.setattr(data.fred, '_request', lambda endpoint, params: {
        'count': 6,
        'release_dates': [
            {'release_name': 'Producer Price Index', 'release_id': 46, 'date': day.isoformat()},
            {'release_name': 'Euro Short Term Rate', 'release_id': 502, 'date': day.isoformat()},
            {'release_name': 'Nasdaq Daily Index Data', 'release_id': 328, 'date': day.isoformat()},
            {'release_name': 'FOMC Press Release', 'release_id': 101, 'date': day.isoformat()},
            {'release_name': 'New Residential Sales', 'release_id': 97, 'date': day.isoformat()},
            {'release_name': 'G.17 Industrial Production and Capacity Utilization', 'release_id': 13,
             'date': day.isoformat()},
        ],
    })
    provider = PublicMarketData()
    # G.17 is left to the Fed calendar, which carries its time; FRED would only duplicate it untimed.
    assert [row['release_name'] for row in provider.calendar(day)] == ['Producer Price Index',
                                                                      'New Residential Sales']

    payload = {
        'Gross Domestic Product': {'release_dates': ['2026-11-13T13:30:00+00:00']},
        'Euro Area GDP': {'release_dates': ['2026-11-13T13:30:00+00:00']},
    }
    monkeypatch.setattr(data, 'get_with_retry', lambda *args, **kwargs: SimpleNamespace(json=lambda: payload))
    events = provider.bea_calendar(day)
    assert len(events) == 1
    assert events[0]['title'] == 'Gross Domestic Product'
    assert pd.Timestamp(events[0]['scheduled_at']) == pd.Timestamp('2026-11-13T08:30:00-05:00')


@pytest.mark.parametrize(('day', 'key', 'expected'), [
    ('2026-03-13', '202603130830', '2026-03-13T08:30:00-04:00'),
    ('2026-11-13', '202611130830', '2026-11-13T08:30:00-05:00'),
])
def test_census_calendar_uses_target_year_and_eastern_dst(monkeypatch, day, key, expected):
    from tradingagents.dataflows import market_report as data

    displayed_date = datetime.fromisoformat(day).strftime('%B %d, %Y')
    html = f'''<table id="calendar">
      <tr><td class="hiden">Header</td></tr>
      <tr height="20"><td><a href="/housing/">New Residential
        Construction</a></td><td sorttable_customkey="{key}">{displayed_date}</td>
        <td>8:30 AM</td><td>January 2026</td><td class="hiden">A{key}</td></tr>
      <tr><td><a>Construction Spending</a></td><td sorttable_customkey="{key}">{displayed_date}</td>
        <td>8:30 AM</td></tr>
      <tr><td><a>New Residential Sales</a></td><td>{displayed_date}</td>
        <td>Time not listed</td><td>January 2026</td></tr>
    </table>'''
    calls = []
    monkeypatch.setattr(data, 'get_with_retry', lambda url, **kwargs: (
        calls.append((url, kwargs)) or SimpleNamespace(content=html.encode('utf-8'))))
    events = PublicMarketData().census_calendar(datetime.fromisoformat(day).date())

    assert len(events) == 2
    by_title = {event['title']: event for event in events}
    assert by_title['New Residential Construction']['scheduled_at'] == expected
    assert by_title['New Residential Sales']['scheduled_at'] is None
    assert calls[0][0] == f'https://www.census.gov/economic-indicators/calendar-listview-{day[:4]}.html'
    assert calls[0][1]['provider'] == 'Census'


def test_census_calendar_reports_http_403_as_missing(monkeypatch):
    import requests

    from tradingagents.dataflows import market_report as data
    from tradingagents.dataflows.market_report import PublicDataError

    def forbidden(*args, **kwargs):
        raise requests.HTTPError('forbidden')

    monkeypatch.setattr(data, 'get_with_retry', forbidden)
    with pytest.raises(PublicDataError, match='HTTPError'):
        PublicMarketData().census_calendar(datetime(2026, 11, 13).date())


def test_next_day_calendar_merges_census_time_and_reports_unavailable_agencies(report):
    rows = [row for row in report['evidence'] if row['label'] == 'New Residential Construction']
    assert len(rows) == 1
    assert rows[0]['scheduled_at'] == '2026-11-13T08:30:00-05:00'
    assert rows[0]['sources'] == [
        'https://fred.stlouisfed.org/release?rid=93',
        'https://www.census.gov/economic-indicators/calendar-listview-2026.html',
    ]
    sales = [row for row in report['evidence'] if row['label'] == 'New Residential Sales']
    assert len(sales) == 1
    assert sales[0]['scheduled_at'] == '2026-11-13T10:00:00-05:00'
    gdp = [row for row in report['evidence'] if row['label'] == 'Gross Domestic Product']
    assert len(gdp) == 1
    assert gdp[0]['scheduled_at'] == '2026-11-13T08:30:00-05:00'
    assert 'https://www.bea.gov/news/schedule/full' in gdp[0]['sources']
    gaps = [row for row in report['evidence'] if row['status'] == 'unavailable']
    ppi = [row for row in report['evidence'] if row['label'] == 'Producer Price Index']
    assert len(ppi) == 1
    assert ppi[0]['scheduled_at'] == '2026-11-13T08:30:00-05:00'
    assert ppi[0]['sources'] == ['https://fred.stlouisfed.org/release?rid=46',
                                 'https://www.bls.gov/schedule/news_release/bls.ics']
    assert not any(row['label'].startswith('BLS:') for row in report['evidence'])
    assert not any('DOL' in row['label'] for row in gaps)
    markdown = mr.render_markdown(report)
    assert '[원문](<https://fred.stlouisfed.org/release?rid=93>)' in markdown
    assert '[원문](<https://www.census.gov/economic-indicators/calendar-listview-2026.html>)' in markdown


def test_weekly_claims_time_gap_is_a_fixed_scope_notice_not_a_warning():
    provider = FakePublicData()
    provider.calendar = lambda day: [{'release_name': 'Unemployment Insurance Weekly Claims Report',
                                      'release_id': 180, 'date': day.isoformat()}]
    report = mr.collect_report(provider, provider.now)
    claims = next(row for row in report['evidence']
                  if row['label'] == 'Unemployment Insurance Weekly Claims Report')
    assert claims['status'] == 'available'
    assert claims['scheduled_at'] is None
    assert '공식 발표 시각 미확인' in claims['note']
    assert not any('DOL' in row['label'] for row in report['evidence'])
    assert not any(warning.startswith(claims['id'] + ' ') for warning in mr.quality_warnings(report))
    assert '주간 실업수당 발표 시각은 수집하지 않습니다' in mr.render_markdown(report)


def test_census_http_403_is_a_report_gap():
    from tradingagents.dataflows.market_report import PublicDataError

    provider = FakePublicData()
    provider.census_calendar = lambda day: (_ for _ in ()).throw(PublicDataError('HTTPError'))
    report = mr.collect_report(provider, provider.now)
    gap = next(row for row in report['evidence'] if row['label'] == 'Census 공식 경제 일정')
    assert gap['status'] == 'unavailable'
    assert gap['reason'] == 'HTTPError'
    assert gap['source'] == 'https://www.census.gov/economic-indicators/calendar-listview-2026.html'


def bls_ics(*events):
    body = ''.join(
        'BEGIN:VEVENT\r\nUID:synthetic\r\n'
        f'DTSTART;TZID=US-Eastern:{start}\r\nDURATION:PT0M\r\n{summary}\r\n'
        'LOCATION:Washington\\, DC\r\nEND:VEVENT\r\n' for start, summary in events)
    return ('BEGIN:VCALENDAR\r\nX-WR-TIMEZONE:US-Eastern\r\nBEGIN:VTIMEZONE\r\nTZID:US-Eastern\r\n'
            'BEGIN:STANDARD\r\nDTSTART:20071104T020000\r\nEND:STANDARD\r\nEND:VTIMEZONE\r\n'
            f'{body}END:VCALENDAR\r\n')


@pytest.mark.parametrize(('day', 'start', 'expected'), [
    ('2026-03-06', '20260306T083000', '2026-03-06T08:30:00-05:00'),
    ('2026-03-09', '20260309T083000', '2026-03-09T08:30:00-04:00'),
    ('2026-10-30', '20261030T083000', '2026-10-30T08:30:00-04:00'),
    ('2026-11-02', '20261102T100000', '2026-11-02T10:00:00-05:00'),
])
def test_bls_calendar_converts_eastern_time_across_dst(monkeypatch, day, start, expected):
    calls = []
    ics = bls_ics((start, 'SUMMARY:Consumer Price Index'))
    monkeypatch.setattr(market_data, 'get_with_retry', lambda url, **kwargs: (
        calls.append((url, kwargs)) or SimpleNamespace(content=ics.encode('utf-8'))))
    events = PublicMarketData().bls_calendar(date.fromisoformat(day))
    assert [(event['title'], event['scheduled_at']) for event in events] == [('Consumer Price Index', expected)]
    assert calls[0][0] == 'https://www.bls.gov/schedule/news_release/bls.ics'
    assert calls[0][1]['provider'] == 'BLS'
    assert calls[0][1]['headers'] == {'User-Agent': market_data.sec_edgar._user_agent()}


def test_bls_calendar_unfolds_lines_and_keeps_selected_releases_only(monkeypatch):
    ics = bls_ics(
        ('20261113T083000', 'SUMMARY:Producer Price\r\n  Index'),
        ('20261113T083000', 'SUMMARY:Producer Price Index'),
        ('20261113T100000', 'SUMMARY:Metropolitan Area Employment and Unemployment (Monthly)'),
        ('20261117T083000', 'SUMMARY:U.S. Import and Export Price Indexes'),
    )
    monkeypatch.setattr(market_data, 'get_with_retry',
                        lambda *args, **kwargs: SimpleNamespace(content=ics.encode('utf-8')))
    provider = PublicMarketData()
    assert provider.bls_calendar(date(2026, 11, 13)) == [{
        'title': 'Producer Price Index', 'scheduled_at': '2026-11-13T08:30:00-05:00',
        'source': 'https://www.bls.gov/schedule/news_release/bls.ics',
        'related_assets': ['미국 주가지수', '미 국채', '달러']}]
    assert provider.bls_calendar(date(2026, 11, 16)) == []


def test_bls_calendar_http_403_and_bad_format_are_unavailable(monkeypatch):
    import requests

    from tradingagents.dataflows.market_report import PublicDataError

    def forbidden(*args, **kwargs):
        raise requests.HTTPError('forbidden')

    monkeypatch.setattr(market_data, 'get_with_retry', forbidden)
    with pytest.raises(PublicDataError, match='HTTPError'):
        PublicMarketData().bls_calendar(date(2026, 11, 13))
    monkeypatch.setattr(market_data, 'get_with_retry',
                        lambda *args, **kwargs: SimpleNamespace(content=b'<html>blocked</html>'))
    with pytest.raises(PublicDataError, match='ValueError'):
        PublicMarketData().bls_calendar(date(2026, 11, 13))

    provider = FakePublicData()
    provider.bls_calendar = lambda day: (_ for _ in ()).throw(PublicDataError('HTTPError'))
    report = mr.collect_report(provider, provider.now)
    gap = next(row for row in report['evidence'] if row['label'] == 'BLS 공식 일정')
    assert (gap['status'], gap['reason']) == ('unavailable', 'HTTPError')
    ppi = next(row for row in report['evidence'] if row['label'] == 'Producer Price Index')
    assert ppi['scheduled_at'] is None


def test_missing_fred_key_explained(monkeypatch):
    from tradingagents.dataflows.market_report import error_reason

    monkeypatch.delenv('FRED_API_KEY', raising=False)
    with pytest.raises(ValueError) as caught:
        PublicMarketData().macro('DGS10', datetime(2026, 11, 12).date())
    assert 'FRED_API_KEY 미설정' in error_reason(caught.value)


def test_post_close_staleness_and_future_bar_rejection():
    provider = FakePublicData()
    original = provider.intraday
    provider.intraday = lambda symbol, day: original(symbol, day).iloc[:2]
    report = mr.collect_report(provider, provider.now)
    rows = [e for e in report['evidence'] if e['section'] == '장후']
    assert all(e['status'] == 'stale' for e in rows)
    frame = pd.DataFrame({'Close': [999.]}, index=pd.DatetimeIndex(['2026-11-12T20:00:00-05:00']))
    assert mr.bounded_bars(frame, pd.Timestamp('2026-11-12T16:00:00-05:00'), pd.Timestamp('2026-11-12T20:00:00-05:00')).empty


def test_news_capped_by_provider_limit_is_a_gap_not_none_found():
    provider = FakePublicData()
    late = [{'title': f'Next day {i}', 'link': f'https://example.com/late/{i}', 'publisher': 'Example',
             'pub_date': datetime.fromisoformat('2026-11-13T09:00:00-05:00')} for i in range(mr.NEWS_FETCH_LIMIT)]
    provider.news = lambda symbol: late if symbol == 'NVDA' else late[:3]
    report = mr.collect_report(provider, provider.now)
    nvda = next(r for r in report['evidence'] if r['label'] == 'NVDA 뉴스')
    aapl = next(r for r in report['evidence'] if r['label'] == 'AAPL 뉴스')
    assert nvda['status'] == 'unavailable' and '최신 기사' in nvda['reason']
    assert aapl['status'] == 'none_found'  # fewer than the cap: the window was reached and was empty
    assert any(w.startswith(nvda['id'] + ' ') for w in mr.quality_warnings(report))


def test_rate_observation_mismatch_is_noted_and_roll_note_is_futures_only():
    provider = FakePublicData()
    periods = {'DGS2': '2026-11-09', 'DGS10': '2026-11-09', 'T10Y2Y': '2026-11-10'}
    provider.macro = lambda series, day: {'value': 4.2, 'period': periods.get(series, '2026-11-10'),
                                          'unit': 'Percent', 'frequency': 'Daily',
                                          'vintage': (day - timedelta(days=1)).isoformat()}
    rows = {r['label']: r for r in mr.collect_report(provider, provider.now)['evidence']}
    for label in ('2년 국채금리', '10년 국채금리', '10년–2년 금리차'):
        assert '관련 금리 관측일이 서로 다름' in rows[label]['note']
        assert '10년–2년 금리차 2026-11-10' in rows[label]['note']
    assert '관측일' not in rows['정책금리(실효 연방기금 월평균)']['note']
    assert '롤' not in rows['미 달러 지수(ICE DXY)']['note']
    assert '롤' in rows['WTI 연속 선물']['note']

    provider.macro = lambda series, day: {'value': 4.2, 'period': '2026-11-10', 'unit': 'Percent',
                                          'frequency': 'Daily', 'vintage': (day - timedelta(days=1)).isoformat()}
    rows = {r['label']: r for r in mr.collect_report(provider, provider.now)['evidence']}
    assert '관측일이 서로 다름' not in rows['10년–2년 금리차']['note']


def test_narrative_prompt_asks_for_the_largest_movers(report):
    llm = Mock(invoke=Mock(side_effect=RuntimeError('stop after capturing the prompt')))
    mr.write_narrative(report, llm=llm)
    system_prompt = llm.invoke.call_args.args[0][0][1]
    assert '가장 크게 움직인 지수·업종·대형주' in system_prompt


def test_narrative_number_check_allows_instrument_names_but_not_figures(report):
    valid = report['evidence'][0]['id']

    def narrate(text):
        llm = Mock(invoke=Mock(return_value=SimpleNamespace(content=json.dumps([
            {'section': '핵심 요약', 'text': text, 'evidence_ids': [valid]}]))))
        mr.write_narrative(report, llm=llm)
        return report['llm_status']

    assert narrate('사실: Russell 2000의 낙폭이 S&P 500보다 컸다.') == 'available'
    assert narrate('사실: Russell 2000이 2% 하락했다.') == 'failed'
    assert narrate('사실: 3분기 실적이 나왔다.') == 'failed'


def test_late_generation_is_flagged_after_next_regular_open():
    on_time, _ = mr.report_window(datetime.fromisoformat('2026-11-12T20:30:00-05:00'))
    late, _ = mr.report_window(datetime.fromisoformat('2026-11-13T09:32:00-05:00'))
    assert on_time['day'] == late['day'] == '2026-11-12'
    assert late['next_open'] == on_time['next_open'] == '2026-11-13T14:30:00+00:00'
    assert not on_time['late_generation'] and late['late_generation']
    provider = FakePublicData()
    provider.now = datetime.fromisoformat('2026-11-13T09:32:00-05:00')
    assert '다음 정규장 개장' in mr.render_markdown(mr.collect_report(provider, provider.now))
    provider.now = datetime.fromisoformat('2026-11-12T20:30:00-05:00')
    assert '다음 정규장 개장' not in mr.render_markdown(mr.collect_report(provider, provider.now))


def test_cross_asset_change_against_prior_session_and_missing_prior():
    provider = FakePublicData()
    original = provider.intraday

    def intraday(symbol, day):
        bars = original(symbol, day)
        return bars * (0.5 if str(day) == '2026-11-11' else 1)

    provider.intraday = intraday
    rows = {r['label']: r for r in mr.collect_report(provider, provider.now)['evidence']}
    dxy = rows['미 달러 지수(ICE DXY)']
    assert dxy['value'] == 102. and dxy['previous_value'] == 51.
    assert dxy['change_pct'] == pytest.approx(100.)
    assert dxy['previous_observed_at'].startswith('2026-11-11T20:00')

    def no_prior(symbol, day):
        if str(day) == '2026-11-11':
            raise RuntimeError('no prior bars')
        return original(symbol, day)

    provider.intraday = no_prior
    rows = {r['label']: r for r in mr.collect_report(provider, provider.now)['evidence']}
    gold = rows['금 연속 선물']
    assert gold['value'] == 102. and gold['change_pct'] is None and '직전 거래일' in gold['change_reason']


def test_low_value_headlines_are_excluded_summarized_and_articles_render_as_rows(report):
    provider = FakePublicData()
    base = provider.news('^GSPC')
    noise = {'title': 'Arista Networks Stock: Is Wall Street Bullish or Bearish?', 'link': 'https://example.com/noise',
             'publisher': 'Barchart', 'pub_date': datetime.fromisoformat('2026-11-12T10:00:00-05:00')}
    provider.news = lambda symbol: [*base, noise]
    result = mr.collect_report(provider, provider.now)
    labels = [r['label'] for r in result['evidence']]
    assert noise['title'] not in labels
    summary = next(r for r in result['evidence'] if r['label'] == '제외한 저가치 헤드라인')
    assert summary['value'] == {'count': 1, 'titles': [noise['title']]}
    llm = Mock(invoke=Mock(side_effect=RuntimeError('capture only')))
    mr.write_narrative(result, llm=llm)
    sent = json.loads(llm.invoke.call_args.args[0][1][1])['evidence']
    assert summary['id'] not in {e['id'] for e in sent}
    markdown = mr.render_markdown(result)
    article = next(r for r in result['evidence'] if r['label'] == 'Confirmed catalyst')
    assert f"| {article['id']} | 11-12 18:00 | [Confirmed catalyst](<https://example.com/news>) |" in markdown
    assert f"### {article['id']} Confirmed catalyst" not in markdown
