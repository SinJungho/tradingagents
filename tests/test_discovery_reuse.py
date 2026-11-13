from unittest.mock import Mock

import pandas as pd
import pytest

from tradingagents import stock_discovery as sd
from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.vendors import sec_edgar


def test_alias_reuses_prices_sec_splits_and_keeps_factors(monkeypatch):
    history = pd.Series(range(1, 301), index=pd.bdate_range(end='2026-11-12', periods=300), dtype=float)
    prices, facts, splits = Mock(return_value=history), Mock(return_value=None), Mock(return_value=pd.Series(dtype=float))
    monkeypatch.setattr(sd, '_closes', prices)
    monkeypatch.setattr(sd, '_facts', facts)
    monkeypatch.setattr(sd, 'get_splits', splits)
    monkeypatch.setattr(sd, 'get_current_date', lambda: '2026-11-12')
    sections = (sd.DiscoveryUniverse('First', 'https://example.com', '2026-11-12', ('AAA.A',)),
                sd.DiscoveryUniverse('Second', 'https://example.com', '2026-11-12', ('AAA-A',)))
    result = sd._score_tickers(('AAA.A', 'AAA-A', 'BBB'), sections=sections)
    assert result.calls == {'prices': 2, 'sec': 2, 'splits': 2}
    assert prices.call_count == facts.call_count == splits.call_count == 2
    assert result.tickers[0].scores == result.tickers[1].scores == result.tickers[2].scores
    assert result.tickers[0].sections == ('First',)
    assert result.tickers[1].sections == ('Second',)
    assert set(result.timings) == {'prices', 'sec', 'splits', 'scoring', 'total_scoring'}
    assert all(v >= 0 for v in result.timings.values())
    sd._score_tickers(('AAA.A',))
    assert prices.call_count == 3  # no cross-run stale cache


def test_failed_alias_is_not_retried_or_hidden(monkeypatch):
    prices = Mock(side_effect=RuntimeError('sensitive detail'))
    monkeypatch.setattr(sd, '_closes', prices)
    monkeypatch.setattr(sd, '_facts', lambda *_: None)
    monkeypatch.setattr(sd, 'get_splits', lambda *_: pd.Series(dtype=float))
    result = sd._score_tickers(('AAA.A', 'AAA-A'))
    assert prices.call_count == 1
    assert [f.ticker for f in result.failures] == ['AAA.A', 'AAA-A']
    assert all(f.reason == 'RuntimeError' for f in result.failures)
    assert 'sensitive' not in result.render()


def test_sec_common_index_once_per_run(monkeypatch):
    fetch = Mock(return_value={'0': {'ticker': 'AAA', 'cik_str': 1}, '1': {'ticker': 'BBB', 'cik_str': 2}})
    monkeypatch.setattr(sec_edgar, '_cached_json', fetch)
    with sec_edgar.company_index_session():
        assert sec_edgar.cik_for('AAA') == '0000000001'
        assert sec_edgar.cik_for('BBB') == '0000000002'
        assert sec_edgar.cik_for('MISSING') is None
    assert fetch.call_count == 1
    with sec_edgar.company_index_session():
        assert sec_edgar.cik_for('AAA') == '0000000001'
    assert fetch.call_count == 2


def test_sec_common_index_failure_reused(monkeypatch):
    fetch = Mock(side_effect=VendorUnavailableError('unavailable'))
    monkeypatch.setattr(sec_edgar, '_cached_json', fetch)
    with sec_edgar.company_index_session():
        for symbol in ('AAA', 'BBB'):
            with pytest.raises(VendorUnavailableError):
                sec_edgar.cik_for(symbol)
    assert fetch.call_count == 1


@pytest.mark.parametrize(('source', 'label', 'kind', 'membership'), [
    (sd.NASDAQ100_SOURCE, 'membership as of', 'secondary', '2026-11-01'),
    (sd.ISHARES_IWM_SOURCE, 'holdings as of', 'proxy', '2026-11-01'),
    (sd.NASDAQ_LISTED_SOURCE, 'file generated', 'official', '2026-11-01'),
    (sd.INDEX_SOURCES['sp500'][1], 'list retrieved', 'secondary', None),
    ('Yahoo Finance equity screener', 'market-cap snapshot', 'secondary', None),
])
def test_source_dates_not_conflated(source, label, kind, membership):
    universe = sd.DiscoveryUniverse('Synthetic', source, '2026-11-01', ('AAA',), label)
    info = universe.provenance
    assert info['source_kind'] == kind
    assert info['membership_as_of'] == membership
    assert info['retrieved_at'].endswith('+00:00')
    assert all(url.startswith('https://') for url in info['source_urls'])


def test_parallel_split_prefetch_keeps_order_and_per_ticker_outcomes(monkeypatch):
    from tradingagents.dataflows.errors import NoMarketDataError

    history = pd.Series(range(1, 301), index=pd.bdate_range(end='2026-11-12', periods=300), dtype=float)
    seen = []

    def splits(symbol):
        seen.append(symbol)
        if symbol == 'NODATA':
            raise NoMarketDataError(symbol, symbol, 'no split rows')
        if symbol == 'BROKEN':
            raise RuntimeError('synthetic split failure')
        return pd.Series(dtype=float)

    monkeypatch.setattr(sd, '_closes', lambda *_: history)
    monkeypatch.setattr(sd, '_facts', lambda *_: None)
    monkeypatch.setattr(sd, 'get_splits', splits)
    monkeypatch.setattr(sd, 'get_current_date', lambda: '2026-11-12')
    names = ('ZZZ', 'NODATA', 'BROKEN', 'AAA', 'AAA')
    result = sd._score_tickers(names)

    assert sorted(seen) == ['AAA', 'BROKEN', 'NODATA', 'ZZZ']
    assert result.calls['splits'] == 4
    assert [entry.ticker for entry in result.tickers] == list(names)
    assert [(f.ticker, f.source) for f in result.failures] == [('BROKEN', 'Yahoo Finance split history')]
    by_ticker = {entry.ticker: entry.scores['value'] for entry in result.tickers}
    assert 'split history' in by_ticker['NODATA'].missing
    assert 'split history' in by_ticker['BROKEN'].missing
    assert 'split history' not in by_ticker['ZZZ'].missing


def test_parallel_price_prefetch_keeps_per_ticker_outcomes_and_failure_order(monkeypatch):
    from tradingagents.dataflows.errors import NoMarketDataError

    history = pd.Series(range(1, 301), index=pd.bdate_range(end='2026-11-12', periods=300), dtype=float)
    seen = []

    def closes(symbol):
        seen.append(symbol)
        if symbol == 'NODATA':
            raise NoMarketDataError(symbol, symbol, 'no price rows')
        if symbol == 'BROKEN':
            raise RuntimeError('synthetic price failure')
        return history

    def splits(symbol):
        if symbol == 'BROKEN':
            raise RuntimeError('synthetic split failure')
        return pd.Series(dtype=float)

    monkeypatch.setattr(sd, '_closes', closes)
    monkeypatch.setattr(sd, '_facts', lambda *_: None)
    monkeypatch.setattr(sd, 'get_splits', splits)
    monkeypatch.setattr(sd, 'get_current_date', lambda: '2026-11-12')
    names = ('ZZZ', 'NODATA', 'BROKEN', 'ZZZ')
    result = sd._score_tickers(names)

    assert sorted(seen) == ['BROKEN', 'NODATA', 'ZZZ']
    assert result.calls['prices'] == 3
    assert [entry.ticker for entry in result.tickers] == list(names)
    # Within a ticker, the price failure still precedes the split failure, as in the sequential loop.
    assert [(f.ticker, f.source) for f in result.failures] == [
        ('BROKEN', 'Yahoo Finance price history'), ('BROKEN', 'Yahoo Finance split history')]
    momentum = {entry.ticker: entry.scores['momentum'].signal for entry in result.tickers}
    assert momentum['NODATA'] == momentum['BROKEN'] != momentum['ZZZ']
