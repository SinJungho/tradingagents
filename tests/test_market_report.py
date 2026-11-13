"""Offline report contracts: calendar, arithmetic, provenance and graceful failures."""
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
from typer.testing import CliRunner

from cli.main import app
from tradingagents import market_report as mr
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
            {'release_name': 'New Home Sales', 'release_id': 94, 'date': day.isoformat()},
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

    def policy_calendar(self, day):
        return [{'title': 'Synthetic speech', 'scheduled_at': f'{day}T14:00:00-05:00', 'source': 'https://example.com/policy', 'time_label': '2:00 p.m.'}]

    def earnings(self, symbol):
        return pd.DataFrame({'Reported EPS': [9999.]}, index=pd.DatetimeIndex(['2026-11-13T16:05:00-05:00']))


@pytest.fixture
def report():
    provider = FakePublicData()
    return mr.collect_report(provider, provider.now)


def test_collection_bounds_sources_and_dedup(report):
    rows = report['evidence']
    news = [r for r in rows if r['label'] == 'Confirmed catalyst']
    assert len(news) == 1
    assert len(news[0]['symbols']) > 1
    encoded = json.dumps(report)
    assert 'Future secret' not in encoded and 'Undated secret' not in encoded
    assert '9999' not in encoded
    futures = next(r for r in rows if r['label'].startswith('ES=F'))
    assert futures['value'] == {'regular_close': 100., 'post_price': 102., 'change_pct': pytest.approx(2)}
    assert pd.Timestamp(futures['observed_at']) <= pd.Timestamp(report['window']['cutoff'])
    sectors = [r for r in rows if r['section'] == '업종']
    assert len(sectors) == 11
    assert all(r['value']['relative_5d_pp'] == 0 for r in sectors)
    assert all(r['value']['rank_1d'] == 1 for r in sectors)
    assert any(r['label'] == 'Producer Price Index' for r in rows)
    for row in rows:
        assert {'value', 'unit', 'observation_period', 'published_at', 'retrieved_at', 'source', 'status'} <= row.keys()


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


def test_all_vendor_failures_still_preserve_structure(tmp_path):
    provider = Mock(spec=FakePublicData)
    for name in ('daily', 'universe', 'macro', 'intraday', 'news', 'calendar', 'census_calendar',
                 'bea_calendar', 'earnings', 'policy_calendar'):
        getattr(provider, name).side_effect = RuntimeError('secret credential')
    report = mr.collect_report(provider, datetime.fromisoformat('2026-11-12T20:30:00-05:00'))
    mr.write_narrative(report, llm=Mock(invoke=Mock(side_effect=RuntimeError('llm key'))))
    path = mr.save_report(report, tmp_path)
    markdown = (path / 'report.md').read_text()
    for section in mr.SECTIONS:
        assert f'## {section}' in markdown
    assert '불완전 보고서' in markdown and 'LLM 해석 실패' in markdown
    assert 'secret credential' not in markdown and 'llm key' not in markdown
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
        'count': 3,
        'release_dates': [
            {'release_name': 'Producer Price Index', 'release_id': 46, 'date': day.isoformat()},
            {'release_name': 'Euro Short Term Rate', 'release_id': 502, 'date': day.isoformat()},
            {'release_name': 'Nasdaq Daily Index Data', 'release_id': 328, 'date': day.isoformat()},
        ],
    })
    provider = PublicMarketData()
    assert [row['release_name'] for row in provider.calendar(day)] == ['Producer Price Index']

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
    sales = [row for row in report['evidence'] if row['label'] == 'New Home Sales']
    assert len(sales) == 1
    assert sales[0]['scheduled_at'] == '2026-11-13T10:00:00-05:00'
    gdp = [row for row in report['evidence'] if row['label'] == 'Gross Domestic Product']
    assert len(gdp) == 1
    assert gdp[0]['scheduled_at'] == '2026-11-13T08:30:00-05:00'
    assert 'https://www.bea.gov/news/schedule/full' in gdp[0]['sources']
    gaps = [row for row in report['evidence'] if row['status'] == 'unavailable']
    coverage_gap = next(row for row in gaps if row['label'] == 'BLS·DOL 공식 일정')
    assert coverage_gap['source'] == 'https://www.bls.gov/schedule/news_release/'
    assert coverage_gap['reason'] == '자동 수집 대상 아님(공개 일정 자동 조회 차단); CPI·고용·PPI·주간 실업수당 시각 미확인'
    assert 'sources' not in coverage_gap
    markdown = mr.render_markdown(report)
    assert '[원문](<https://fred.stlouisfed.org/release?rid=93>)' in markdown
    assert '[원문](<https://www.census.gov/economic-indicators/calendar-listview-2026.html>)' in markdown


def test_census_http_403_is_a_report_gap():
    from tradingagents.dataflows.market_report import PublicDataError

    provider = FakePublicData()
    provider.census_calendar = lambda day: (_ for _ in ()).throw(PublicDataError('HTTPError'))
    report = mr.collect_report(provider, provider.now)
    gap = next(row for row in report['evidence'] if row['label'] == 'Census 공식 경제 일정')
    assert gap['status'] == 'unavailable'
    assert gap['reason'] == 'HTTPError'
    assert gap['source'] == 'https://www.census.gov/economic-indicators/calendar-listview-2026.html'


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
