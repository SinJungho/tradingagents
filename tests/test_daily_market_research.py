"""Point-in-time checks for the reusable public market evidence."""
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import exchange_calendars as xcals
import pandas as pd
import pytest

from tradingagents.daily_market_research import (
    BAR_SIZE,
    ET,
    add_cross_assets,
    add_crypto,
    add_macro,
    add_ten_year_proxy,
    collect_daily,
)
from tradingagents.dataflows import market_report as market_data


def recorder():
    rows = []

    def add(section, label, value, source, *, period=None, status='available', reason=None, **extra):
        row = {
            'id': f'E{len(rows) + 1}', 'section': section, 'label': label, 'value': value,
            'source': source, 'observation_period': period, 'status': status, 'reason': reason,
            **extra,
        }
        rows.append(row)
        return row

    def missing(section, label, source, reason):
        return add(section, label, None, source, status='unavailable', reason=reason)

    return rows, add, missing


@pytest.fixture
def calendar():
    return xcals.get_calendar('XNYS', start='2025-01-01', end='2026-12-20')


def test_friday_crypto_uses_fixed_utc_cutoff_not_weekend_spot():
    cutoff = pd.Timestamp('2026-11-20T20:00:00-05:00')
    end = cutoff.tz_convert('UTC')
    prices = {
        end: 120.,
        end - pd.Timedelta(hours=24): 100.,
        end - pd.Timedelta(days=7): 80.,
        end - pd.Timedelta(days=30): 60.,
    }

    def candles(pair, boundary):
        assert pair == 'btcusd'
        return pd.DataFrame({'Close': [prices[boundary], 999.]},
                            index=pd.DatetimeIndex([boundary - BAR_SIZE, boundary]))

    rows, add, _ = recorder()
    provider = SimpleNamespace(crypto_candles=Mock(side_effect=candles))
    add_crypto(provider, 'btcusd', 'BTC/USD', cutoff, add)
    assert rows[0]['value'] == pytest.approx({
        'close': 120., 'return_24h': 20., 'return_7d': 50., 'return_30d': 100.,
    })
    assert rows[0]['observed_at'] == '2026-11-21T01:00:00+00:00'
    assert provider.crypto_candles.call_count == 4


def test_broken_crypto_comparison_is_partial():
    cutoff = pd.Timestamp('2026-11-20T20:00:00-05:00')
    end = cutoff.tz_convert('UTC')

    def candles(pair, boundary):
        if boundary != end:
            return pd.DataFrame({'Close': [80.]}, index=pd.DatetimeIndex([boundary]))
        return pd.DataFrame({'Close': [100.]}, index=pd.DatetimeIndex([boundary - BAR_SIZE]))

    rows, add, _ = recorder()
    add_crypto(SimpleNamespace(crypto_candles=candles), 'ethusd', 'ETH/USD', cutoff, add)
    assert rows[0]['value'] == {'close': 100., 'return_24h': None, 'return_7d': None, 'return_30d': None}
    assert rows[0]['status'] == 'partial'


def test_commodity_calculations_use_continuous_prices_and_preserve_unknown_roll(calendar):
    cutoff = pd.Timestamp('2026-11-20T20:00:00-05:00')
    sessions = calendar.sessions_in_range('2026-10-01', cutoff.date())
    prices = {sessions[-1].date(): 120., sessions[-2].date(): 100.,
              sessions[-6].date(): 80., sessions[-21].date(): 60.}

    def intraday(symbol, day):
        return pd.DataFrame({'Close': [prices[day], 999.]},
                            index=pd.DatetimeIndex([f'{day} 19:55', f'{day} 20:00'], tz=ET))

    rows, add, missing = recorder()
    add_cross_assets(SimpleNamespace(intraday=intraday), sessions, cutoff, add, missing)
    copper = next(row for row in rows if row['symbol'] == 'HG=F')
    assert (copper['return_1d'], copper['return_5d'], copper['return_20d']) == pytest.approx((20., 50., 100.))
    assert copper['comparison_observations'][20]['observed_at'].startswith(str(sessions[-21].date()))
    assert (copper['contract_month'], copper['rollover'], copper['preliminary']) == (None, 'unknown', None)
    assert '연속 선물' in copper['note'] and '롤 영향 가능' in copper['note']


def test_cross_assets_compare_friday_17_et_to_exact_historical_bar(calendar):
    cutoff = pd.Timestamp('2026-11-20T20:00:00-05:00')
    sessions = calendar.sessions_in_range('2026-10-01', cutoff.date())

    def intraday(symbol, day):
        bars = [('16:55', 120.)] if day == cutoff.date() else [('16:55', 100.), ('19:55', 50.)]
        if day == sessions[-6].date():
            bars = [('16:50', 800.), ('19:55', 50.)]
        return pd.DataFrame({'Close': [value for _, value in bars]},
                            index=pd.DatetimeIndex([f'{day} {minute}' for minute, _ in bars], tz=ET).tz_convert('UTC'))

    rows, add, missing = recorder()
    add_cross_assets(SimpleNamespace(intraday=intraday), sessions, cutoff, add, missing)
    assert len(rows) == 4
    for row in rows:
        assert row['change_pct'] == pytest.approx(20.)
        assert row['observed_at'].endswith('T17:00:00-05:00')
        assert row['previous_observed_at'].endswith('T17:00:00-05:00')
        if row['symbol'].endswith('=F'):
            assert row['return_5d'] is None and row['return_20d'] == pytest.approx(20.)
            assert 5 not in row['comparison_observations']
            assert '17:00 ET' in row['comparison_gaps'][5]


def test_ten_year_trigger_requires_same_clock_time_on_prior_session():
    day, prior = date(2026, 11, 20), date(2026, 11, 19)
    cutoff = pd.Timestamp('2026-11-20T20:00:00-05:00')
    shift_prior = False

    def intraday(symbol, query_day):
        assert symbol == '^TNX'
        minute = '14:50' if query_day == prior and shift_prior else '14:55'
        price = 4. if query_day == prior else 4.1
        return pd.DataFrame({'Close': [price]}, index=pd.DatetimeIndex([f'{query_day} {minute}'], tz=ET))

    rows, add, _ = recorder()
    provider = SimpleNamespace(intraday=intraday)
    add_ten_year_proxy(provider, day, prior, cutoff, add)
    assert rows[0]['change_bp'] == 10
    assert rows[0]['observed_at'] == '2026-11-20T15:00:00-05:00'
    assert rows[0]['previous_observed_at'] == '2026-11-19T15:00:00-05:00'
    shift_prior = True
    add_ten_year_proxy(provider, day, prior, cutoff, add)
    assert rows[1]['change_bp'] is None
    assert rows[1]['status'] == 'partial'


def test_fred_observation_comparison_keeps_dates_and_rejects_nonadjacent(calendar):
    day = date(2026, 11, 20)
    prior_day = '2026-11-18'

    def macro(series, as_of):
        return {'value': 4.1, 'period': '2026-11-19', 'vintage': '2026-11-19',
                'previous': 4., 'previous_period': prior_day, 'unit': '%', 'frequency': 'Daily'}

    rows, add, missing = recorder()
    provider = SimpleNamespace(macro=macro)
    add_macro(provider, day, calendar, add, missing)
    rates = {row['series']: row for row in rows}
    assert {'DGS5', 'DFII5', 'DFII10'} <= set(rates)
    assert rates['DGS5']['label'] != rates['DFII5']['label']
    assert rates['DFII5']['change_bp'] == rates['DFII10']['change_bp'] == 10
    assert rates['DGS10']['change_bp'] == 10
    assert rates['DGS10']['previous_observation_period'] == '2026-11-18'
    prior_day = '2026-11-17'
    rows.clear()
    add_macro(provider, day, calendar, add, missing)
    assert next(row for row in rows if row['series'] == 'DGS10')['change_bp'] is None


@pytest.mark.parametrize('series', ('DGS10', 'DFII5'))
def test_alfred_fallback_requires_requested_vintage_and_excludes_future(monkeypatch, series):
    day = date(2026, 11, 20)
    monkeypatch.setattr(market_data.fred, '_fred_today', lambda: '2026-11-21')
    fetch = Mock(return_value=SimpleNamespace(text=(
        f'observation_date,{series}_20261119\n2026-11-18,4.00\n2026-11-19,4.10\n2026-11-20,9.99\n'
    )))
    monkeypatch.setattr(market_data, 'get_with_retry', fetch)
    provider = market_data.PublicMarketData()
    result = provider.treasury_vintage(series, day)
    assert fetch.call_args.kwargs['params']['vintage_date'] == '2026-11-19'
    assert result['value'] == 4.1
    assert result['previous'] == 4.
    assert result['period'] == result['vintage'] == '2026-11-19'
    fetch.return_value.text = 'observation_date,DGS5\n2026-11-19,4.10\n'
    with pytest.raises(market_data.PublicDataError):
        provider.treasury_vintage('DGS5', day)


def test_analysis_cutoff_rejects_unfinished_early_close_day_and_future_membership(calendar):
    day = date(2026, 11, 27)
    session = calendar.date_to_session(day)
    close = calendar.session_close(session)
    cutoff = close - pd.Timedelta(minutes=15)
    next_session = calendar.next_session(session)
    sessions = calendar.sessions_in_range(day - timedelta(days=410), day)
    provider = SimpleNamespace(
        daily=Mock(return_value=pd.DataFrame({'Close': [100.] * (len(sessions) - 1) + [999.]}, index=sessions)),
        universe=lambda: SimpleNamespace(tickers=('AAA',), source='https://example.com/members',
                                         as_of='2026-11-30', as_of_label='retrieved on'),
    )

    def intraday(symbol, query_day):
        sample = pd.Timestamp(f'{query_day} 12:40', tz=ET)
        times = pd.DatetimeIndex([sample, sample + BAR_SIZE, sample + 4 * BAR_SIZE])
        return pd.DataFrame({'Close': [105., 999., 999.]}, index=times)

    provider.intraday = intraday
    rows, add, missing = recorder()
    collect_daily(provider, {'day': day.isoformat(), 'cutoff': cutoff.isoformat(),
                             'close': close.isoformat(), 'generated_at': cutoff.isoformat(),
                             'analysis_mode': True,
                             'next_open': calendar.session_open(next_session).isoformat()},
                  calendar, add, missing)
    sp500 = next(row for row in rows if row.get('symbol') == '^GSPC')
    assert close.tz_convert(ET).hour == 13
    assert sp500['value']['close'] == 105.
    assert sp500['observed_at'] == cutoff.tz_convert(ET).isoformat()
    breadth = next(row for row in rows if row['label'] == 'S&P 500 구성 종목 시장 폭')
    assert breadth['status'] == 'unavailable'
    assert not any(call.args[0] == 'AAA' for call in provider.daily.call_args_list)
