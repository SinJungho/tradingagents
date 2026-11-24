"""Shared, point-in-time daily US market evidence."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from tradingagents.dataflows.market_report import (
    ALFRED_CSV_URL,
    BITSTAMP_OHLC_URL,
    INDICES,
    MACRO,
    MARKETS,
    RATE_CHANGE_SERIES,
    REAL_TREASURY_RATES,
    SECTORS,
    TREASURY_RATES,
    error_reason,
    finite,
    quote_url,
)
from tradingagents.stock_discovery import SPY_HOLDINGS_SOURCE

ET = ZoneInfo('America/New_York')
VOLATILITY_SYMBOLS = ('^VIX', '^VIX9D')
BAR_SIZE = pd.Timedelta(minutes=5)


def price_stats(frame, sessions, fallback_close=None):
    """Do not compress missing sessions into falsely comparable 1/5/20-day returns."""
    empty = {'close': None, 'return_1d': None, 'return_5d': None, 'return_20d': None}
    if frame is None or frame.empty or 'Close' not in frame:
        closes = pd.Series(index=sessions, dtype=float)
        if fallback_close is not None and len(closes):
            closes.iloc[-1] = fallback_close
            empty = {**empty, 'close': finite(fallback_close)}
        return empty, closes
    frame = frame.copy()
    frame.index = pd.DatetimeIndex([pd.Timestamp(x).date() for x in frame.index])
    if frame.index.has_duplicates:
        return empty, pd.Series(index=sessions, dtype=float)
    frame = frame.reindex(sessions)
    closes = pd.to_numeric(frame['Close'], errors='coerce')
    closes = closes.where((closes > 0) & (closes < float('inf')))
    if fallback_close is not None and pd.isna(closes.iloc[-1]):
        closes.iloc[-1] = fallback_close
    result = {**empty, 'close': finite(closes.iloc[-1])}
    for count in (1, 5, 20):
        window = closes.iloc[-count-1:]
        if len(window) == count + 1 and window.notna().all():
            result[f'return_{count}d'] = finite((window.iloc[-1] / window.iloc[0] - 1) * 100)
    return result, closes


def has_split_on_day(frame, day):
    if frame is None or frame.empty or 'Stock Splits' not in frame:
        return False
    for index in frame.index:
        if pd.Timestamp(index).date() == day:
            values = frame.loc[[index], 'Stock Splits']
            if any((value := finite(item)) is not None and value > 0 and value != 1 for item in values):
                return True
    return False


def breadth_stats(histories):
    count = len(histories)
    out = {'constituents': count}
    for period in (1, 50, 200):
        valid = [s.iloc[-max(2, period):] for s in histories.values()
                 if len(s) >= max(2, period) and s.iloc[-max(2, period):].notna().all()]
        out[f'success_{period}'] = len(valid)
        out[f'excluded_{period}'] = count - len(valid)
        if period == 1:
            for label, compare in [('advancing', lambda a, b: a > b), ('declining', lambda a, b: a < b), ('unchanged', lambda a, b: a == b)]:
                out[f'{label}_pct'] = 100 * sum(compare(s.iloc[-1], s.iloc[-2]) for s in valid) / len(valid) if valid else None
        else:
            out[f'above_ma{period}_pct'] = 100 * sum(s.iloc[-1] > s.mean() for s in valid) / len(valid) if valid else None
    return out


def short_list(names, limit=10):
    """Name the first few symbols and count the rest; full lists stay in evidence.json."""
    return ', '.join(names[:limit]) + (f' 외 {len(names) - limit}개' if len(names) > limit else '')


def bounded_bars(frame, start, end):
    if frame is None or frame.empty or not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        return pd.DataFrame()
    frame = frame.sort_index()
    # Providers timestamp the starts of bars.
    selected = frame[(frame.index >= start) & (frame.index + BAR_SIZE <= end)]
    if 'Close' not in selected:
        return pd.DataFrame()
    return selected[selected['Close'].map(finite).notna()]


def collect_daily(provider, window, calendar, add, missing):
    day = pd.Timestamp(window['day']).date()
    cutoff, close = pd.Timestamp(window['cutoff']).tz_convert(ET), pd.Timestamp(window['close'])
    snapshot = window.get('analysis_mode', False)
    session = calendar.date_to_session(day)
    session_open = calendar.session_open(session)
    sessions = calendar.sessions_in_range(day - timedelta(days=410), day)
    histories = {}
    history_metadata = {}
    prices = {}

    def price_history(symbol):
        frame = None
        daily_error = None
        try:
            frame = provider.daily(symbol, day)
        except Exception as exc:
            daily_error = error_reason(exc)
        target = [index for index in frame.index if pd.Timestamp(index).date() == day] if frame is not None else []
        target_value = finite(frame.loc[target[-1], 'Close']) if target and 'Close' in getattr(frame, 'columns', ()) else None
        split_blocked = has_split_on_day(frame, day)
        # A volatility series can finish after the equity close. Don't use a
        # date-only daily bar at an intraday cutoff or in a close-pinned analysis.
        cutoff_only = cutoff < close or (snapshot and symbol in VOLATILITY_SYMBOLS)
        if cutoff_only and target:
            frame = frame.drop(index=target)
        daily_close = not cutoff_only and target_value is not None and target_value > 0
        fallback_close = None
        fallback_observed = None
        fallback_error = None
        if not daily_close and not split_blocked:
            try:
                bars = provider.intraday(symbol, day)
                regular = bounded_bars(bars, session_open, min(close, cutoff))
                if not regular.empty:
                    fallback_close = finite(regular['Close'].iloc[-1])
                    if fallback_close is not None and fallback_close > 0:
                        fallback_observed = (regular.index[-1] + BAR_SIZE).isoformat()
                    else:
                        fallback_close = None
            except Exception as exc:
                fallback_error = error_reason(exc)
        values, closes = price_stats(frame, sessions, fallback_close)
        meta = {
            'close_source': 'same_day_5m_regular_close_proxy' if fallback_close is not None else ('daily_close' if daily_close else 'unavailable'),
            'observed_at': (fallback_observed if fallback_close is not None else
                            window['close'] if daily_close and symbol not in VOLATILITY_SYMBOLS else None),
            'cutoff_only': cutoff_only,
            'split_blocked': split_blocked,
            'daily_error': daily_error,
            'fallback_error': fallback_error,
        }
        return values, closes, meta

    def daily(symbol, section, label, unit='USD', proxy=False):
        if symbol in prices:
            return prices[symbol]
        try:
            values, closes, meta = price_history(symbol)
            histories[symbol] = closes
            history_metadata[symbol] = meta
            incomplete = any(v is None for v in values.values())
            proxy_used = meta['close_source'] == 'same_day_5m_regular_close_proxy'
            reason = None
            if meta['split_blocked']:
                reason = '해당일 주식 분할로 5분 봉과 일봉 가격 단위를 안전하게 맞출 수 없음'
            elif proxy_used:
                reason = ('분석 기준 시각까지 완료된 정규장 5분 봉 사용' if meta['cutoff_only'] else
                          '일봉 종가 결측으로 당일 마지막 완료 정규장 5분 봉 대용치를 사용')
            elif incomplete:
                reason = '해당 거래일 가격 또는 동일 거래일 비교 이력 부족'
                failures = [x for x in (meta['daily_error'], meta['fallback_error']) if x]
                if failures:
                    reason += f"; 공급자 오류 범주: {', '.join(failures)}"
            row = add(section, label, values, quote_url(symbol), unit=unit, period=window['day'],
                      status='partial' if incomplete or proxy_used or meta['split_blocked'] else 'available',
                      reason=reason, symbol=symbol, proxy=proxy, source_kind='secondary',
                      price_basis='Yahoo Close 가격수익률; 현금 분배금 제외',
                      close_source=meta['close_source'], observed_at=meta['observed_at'],
                      source_failures={key: meta[key] for key in ('daily_error', 'fallback_error') if meta[key]},
                      note=(reason if proxy_used else '일간 지수 종가; 공급자 공개 시각 미확인'
                            if symbol in VOLATILITY_SYMBOLS else None),
                      calculations={'dates': [d.date().isoformat() for d in closes.index[-21:]],
                                    'price_closes': [finite(v) for v in closes.iloc[-21:]]})
        except Exception as exc:
            histories[symbol] = pd.Series(index=sessions, dtype=float)
            history_metadata[symbol] = {'close_source': 'unavailable', 'observed_at': None,
                                        'split_blocked': False, 'daily_error': error_reason(exc),
                                        'fallback_error': None}
            row = missing(section, label, quote_url(symbol), error_reason(exc))
        prices[symbol] = row
        return row

    for symbol, label in INDICES.items():
        daily(symbol, '지수', label, '지수')
    vix = prices['^VIX']
    vix_values = vix.get('calculations', {}).get('price_closes', [])
    vix['change_points'] = (
        round(vix_values[-1] - vix_values[-2], 8)
        if vix.get('close_source') == 'daily_close' and len(vix_values) >= 2
        and all(value is not None for value in vix_values[-2:]) else None
    )
    if snapshot and vix.get('observed_at'):
        try:
            observed = pd.Timestamp(vix['observed_at']).tz_convert(ET)
            prior_day = calendar.previous_session(session).date()
            prior_cutoff = pd.Timestamp(datetime.combine(prior_day, observed.time(), ET))
            previous, prior_observed = last_intraday(provider, '^VIX', prior_cutoff)
            if prior_observed == prior_cutoff:
                vix['change_points'] = round(vix['value']['close'] - previous, 8)
                vix['previous_observed_at'] = prior_observed.isoformat()
        except Exception:
            # The VIX level remains usable even if a matching previous bar is unavailable.
            pass
    benchmark = prices['^GSPC']['value'] or {}
    sector_rows = []
    for symbol, label in SECTORS.items():
        row = daily(symbol, '업종', f'{label} ({symbol}, ETF 대용치)', proxy=True)
        sector_rows.append(row)
        if row['value']:
            row['benchmark_id'] = prices['^GSPC']['id']
            for period in (1, 5, 20):
                key = f'return_{period}d'
                own, base = row['value'][key], benchmark.get(key)
                row['value'][f'relative_{period}d_pp'] = finite(own - base) if own is not None and base is not None else None
    for period in (1, 5, 20):
        key = f'return_{period}d'
        values = sorted({r['value'][key] for r in sector_rows if r['value'] and r['value'][key] is not None}, reverse=True)
        for row in sector_rows:
            if row['value']:
                value = row['value'][key]
                row['value'][f'rank_{period}d'] = values.index(value) + 1 if value is not None else None

    for symbol, label in [('SPY', '시가총액 가중 S&P 500'), ('RSP', '동일가중 S&P 500')]:
        daily(symbol, '시장 폭·참여도', f'{label} ({symbol}, ETF 대용치)', proxy=True)
    for left, right, label in [('^RUT', '^GSPC', '중소형–대형 지수 상대 성과'), ('RSP', 'SPY', '동일가중–시가총액 가중 ETF 상대 성과')]:
        lhs, rhs = prices[left]['value'] or {}, prices[right]['value'] or {}
        differences = {f'relative_{p}d_pp': finite(lhs[f'return_{p}d'] - rhs[f'return_{p}d'])
                       if lhs.get(f'return_{p}d') is not None and rhs.get(f'return_{p}d') is not None else None for p in (1, 5, 20)}
        add('시장 폭·참여도', label, differences, quote_url(left), unit='퍼센트포인트',
            period=window['day'], inputs=[prices[left]['id'], prices[right]['id']],
            status='partial' if any(v is None for v in differences.values()) else 'available',
            reason='비교 자료 부족' if any(v is None for v in differences.values()) else None)
    membership_source = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    try:
        universe = provider.universe()
        membership_source = universe.source
        approved_membership = not snapshot or membership_covers_cutoff(universe, day, window)
        if universe.source == SPY_HOLDINGS_SOURCE and universe.as_of:
            approved_membership = approved_membership and pd.Timestamp(universe.as_of).date() <= day
        if not approved_membership:
            raise ValueError('기준 시각 당시의 구성 종목 미확인')
        members = {}
        excluded = []
        pending = [symbol for symbol in universe.tickers if symbol not in histories]

        def member_history(symbol):
            try:
                _, closes, meta = price_history(symbol)
                return symbol, closes, meta
            except Exception as exc:
                return symbol, pd.Series(index=sessions, dtype=float), {
                    'close_source': 'unavailable', 'observed_at': None, 'split_blocked': False,
                    'daily_error': error_reason(exc), 'fallback_error': None,
                }

        with ThreadPoolExecutor(max_workers=8) as pool:
            for symbol, closes, meta in pool.map(member_history, pending):
                histories[symbol] = closes
                history_metadata[symbol] = meta
        proxy_symbols = []
        split_blocked_symbols = []
        unavailable_symbols = []
        for symbol in universe.tickers:
            meta = history_metadata.get(symbol, {})
            if meta.get('close_source') == 'same_day_5m_regular_close_proxy':
                proxy_symbols.append(symbol)
            if meta.get('close_source') == 'unavailable':
                unavailable_symbols.append(symbol)
            if meta.get('split_blocked'):
                split_blocked_symbols.append(symbol)
            members[symbol] = histories[symbol]
            if histories[symbol].iloc[-2:].isna().any():
                excluded.append(symbol)
        stats = breadth_stats(members)
        short_history_excluded = {
            period: [symbol for symbol, history in members.items()
                     if history_metadata.get(symbol, {}).get('close_source') != 'unavailable'
                     and not (len(history) >= max(2, period)
                              and history.iloc[-max(2, period):].notna().all())]
            for period in (1, 50, 200)
        }
        spy_proxy = universe.source == SPY_HOLDINGS_SOURCE
        wikipedia_fallback = 'wikipedia.org' in universe.source
        breadth_label = ('SPY 보유 종목 대용치의 시장 폭 (공식 S&P 500 지수 구성 아님)' if spy_proxy
                         else '현재 S&P 500 구성 종목 표본의 시장 폭')
        membership_as_of = (universe.as_of if spy_proxy else
                            None if wikipedia_fallback or 'retrieved' in universe.as_of_label else universe.as_of)
        membership_note = ('SPY ETF 보유 종목 대용치이며 공식 S&P 500 지수 구성 목록이 아님' if spy_proxy
                           else 'Wikipedia 현재 구성표 대체 자료; 구성 기준일 미확인' if wikipedia_fallback else None)
        notes = [membership_note] if membership_note else []
        if any(short_history_excluded.values()):
            notes.append('이력 부족 종목은 해당 구간 분모에서 제외: ' + ' · '.join(
                f"{period}일 {short_list(names)}"
                for period, names in short_history_excluded.items() if names))
        limitations = []
        if unavailable_symbols:
            limitations.append(f'시세 조회 실패 종목 {len(unavailable_symbols)}개: {short_list(unavailable_symbols)}')
        if proxy_symbols:
            limitations.append(f'5분 봉 종가 대용치 사용: {short_list(proxy_symbols)}')
        if split_blocked_symbols:
            limitations.append(f'분할로 제외한 종목: {short_list(split_blocked_symbols)}')
        add('시장 폭·참여도', breadth_label, stats, universe.source,
            unit='비율 % / 종목 수', period=window['day'], membership_as_of=membership_as_of,
            observed_at=min(close, cutoff).isoformat(),
            status='partial' if unavailable_symbols or proxy_symbols or split_blocked_symbols else 'available',
            reason='; '.join(limitations) or None,
            excluded_symbols=excluded, source_kind='etf_holdings_proxy' if spy_proxy else 'secondary',
            note='; '.join([*notes, *limitations]) or None,
            constituents=list(members),
            price_basis='Yahoo Close 가격수익률; 현금 분배금 제외; 결측 종가는 당일 마지막 완료 정규장 5분 봉으로 보완',
            intraday_proxy_symbols=proxy_symbols, split_blocked_symbols=split_blocked_symbols,
            close_source_by_symbol={symbol: history_metadata.get(symbol, {}).get('close_source', 'unavailable') for symbol in members},
            observed_at_by_symbol={symbol: history_metadata.get(symbol, {}).get('observed_at') for symbol in members},
            source_failures_by_symbol={symbol: {key: history_metadata[symbol][key]
                                                for key in ('daily_error', 'fallback_error')
                                                if history_metadata.get(symbol, {}).get(key)}
                                       for symbol in members
                                       if any(history_metadata.get(symbol, {}).get(key)
                                              for key in ('daily_error', 'fallback_error'))},
            calculations={s: {'dates': [d.date().isoformat() for d in h.index[-200:]],
                              'price_closes': [finite(v) for v in h.iloc[-200:]]} for s, h in members.items()})
    except Exception as exc:
        reason = ('기준 시각 당시의 구성 종목 미확인'
                  if str(exc) == '기준 시각 당시의 구성 종목 미확인' else error_reason(exc))
        missing('시장 폭·참여도', 'S&P 500 구성 종목 시장 폭', membership_source, reason)

    add_macro(provider, day, calendar, add, missing)
    add_ten_year_proxy(provider, day, calendar.previous_session(session).date(), min(close, cutoff), add)
    add_cross_assets(provider, sessions, cutoff, add, missing)
    for pair, label in (('btcusd', 'BTC/USD (Bitstamp)'), ('ethusd', 'ETH/USD (Bitstamp)')):
        add_crypto(provider, pair, label, cutoff, add)
    return daily


def membership_covers_cutoff(universe, day, window):
    """Current-only membership feeds cannot reconstruct an old holdings list."""
    if universe.source != SPY_HOLDINGS_SOURCE or not universe.as_of:
        return False
    cutoff = pd.Timestamp(window['cutoff'])
    generated = pd.Timestamp(window['generated_at'])
    observed = pd.Timestamp(universe.as_of).date()
    return observed < day and cutoff <= generated < pd.Timestamp(window['next_open'])


def add_macro(provider, day, calendar, add, missing):
    rate_rows = {}
    for series, label in MACRO.items():
        source = f'https://fred.stlouisfed.org/series/{series}'
        primary_error = None
        try:
            try:
                data = provider.macro(series, day)
            except Exception as exc:
                if series not in TREASURY_RATES or not hasattr(provider, 'treasury_vintage'):
                    raise
                primary_error = error_reason(exc)
                data = provider.treasury_vintage(series, day)
            period = pd.Timestamp(data['period']).date()
            vintage = pd.Timestamp(data['vintage']).date()
            value = finite(data['value'])
            if pd.isna(period) or pd.isna(vintage) or period > vintage or vintage >= day or value is None:
                raise ValueError('Invalid macro observation or vintage')
            change_fields = {}
            if series in RATE_CHANGE_SERIES:
                prior = finite(data.get('previous'))
                prior_day = data.get('previous_period')
                same_basis = (prior is not None and prior_day and calendar.is_session(period)
                              and period > calendar.first_session.date()
                              and calendar.previous_session(period).date() == pd.Timestamp(prior_day).date())
                change_fields = {
                    'change_bp': round((value - prior) * 100, 8) if same_basis else None,
                    'previous_value': prior if same_basis else None,
                    'previous_observation_period': prior_day if same_basis else None,
                }
            age = (day - period).days
            max_age = {'Daily': 10, 'Monthly': 100, 'Quarterly': 200}.get(data['frequency'], 100)
            row = add('매크로', label, value, source, unit=data['unit'], period=data['period'],
                      frequency=data['frequency'], vintage=data['vintage'], series=series, source_kind='official',
                      status='stale' if age > max_age else 'available',
                      reason='관측 기간이 통상 발표 주기보다 오래됨' if age > max_age else None,
                      note='전일까지의 FRED 빈티지; 정확한 발표 시각 미확인',
                      **({'source_api': ALFRED_CSV_URL, 'source_failures': {'fred': primary_error}}
                         if primary_error else {}), **change_fields)
            if series in TREASURY_RATES:
                rate_rows[series] = row
        except Exception as exc:
            reason = error_reason(exc)
            if primary_error:
                reason = f'FRED {primary_error}; ALFRED {reason}'
            missing('매크로', label, source, reason)
    if len({row['observation_period'] for row in rate_rows.values()}) > 1:
        dates = ', '.join(f"{row['label']} {row['observation_period']}" for row in rate_rows.values())
        for row in rate_rows.values():
            row['note'] += f'; 관련 금리 관측일이 서로 다름({dates})'
    real_rates = [rate_rows[series] for series in REAL_TREASURY_RATES if series in rate_rows]
    same_current = len(real_rates) == 2 and real_rates[0]['observation_period'] == real_rates[1]['observation_period']
    if not same_current or any(row['change_bp'] is None for row in real_rates):
        for row in real_rates:
            row.update(change_bp=None, previous_value=None, previous_observation_period=None)
            row['note'] += '; 5년·10년 실질금리의 공통 비교일 미확인'


def last_intraday(provider, symbol, cutoff):
    cutoff = cutoff.tz_convert(ET)
    frame = bounded_bars(provider.intraday(symbol, cutoff.date()), cutoff.normalize(), cutoff)
    if frame.empty:
        raise ValueError('완료 5분 봉 미확인')
    return finite(frame['Close'].iloc[-1]), frame.index[-1].tz_convert(ET) + BAR_SIZE


def add_ten_year_proxy(provider, day, prior_day, cutoff, add):
    """Use the same clock-time quote in both sessions for the same-day rate trigger."""
    symbol, label = '^TNX', '10년물 수익률 지수 (^TNX 대용치)'
    source = quote_url(symbol)
    # The provider's historical close is around 15:00 ET. Compare at or before
    # that clock time on both days, capped by the requested analysis boundary.
    cutoff = min(cutoff.tz_convert(ET), pd.Timestamp(datetime.combine(day, time(15), ET)))
    try:
        level, observed = last_intraday(provider, symbol, cutoff)
    except Exception as exc:
        return add('매크로', label, None, source, period=day.isoformat(), series='TNX',
                   source_kind='proxy', status='unavailable', reason=error_reason(exc))
    previous = prior_observed = change_bp = None
    reason = '같은 시각의 직전 거래일 5분 봉 또는 최신 관측 미확인'
    try:
        prior_cutoff = pd.Timestamp(datetime.combine(prior_day, observed.tz_convert(ET).time(), ET))
        previous, prior_observed = last_intraday(provider, symbol, prior_cutoff)
        if prior_observed == prior_cutoff and cutoff - observed <= 3 * BAR_SIZE:
            change_bp = round((level - previous) * 100, 8)
            reason = None
    except Exception as exc:
        reason = f'{reason}({error_reason(exc)})'
    return add('매크로', label, level, source, period=day.isoformat(), unit='Percent',
               observed_at=observed.isoformat(), series='TNX', symbol=symbol, source_kind='proxy',
               rate_trigger_proxy=True, change_bp=change_bp, previous_value=previous,
               previous_observed_at=prior_observed.isoformat() if prior_observed is not None else None,
               status='available' if change_bp is not None else 'partial', reason=reason,
               note='Yahoo 10년물 수익률 지수. 15:00 ET 이내의 같은 시각 완료 5분 봉 비교. 미 재무부 고정만기 금리와 기준이 다름')


def add_cross_assets(provider, sessions, cutoff, add, missing):
    for symbol, (label, unit) in MARKETS.items():
        commodity = symbol.endswith('=F')
        try:
            level, observed = last_intraday(provider, symbol, cutoff)
        except Exception as exc:
            missing('매크로', label, quote_url(symbol), error_reason(exc))
            continue
        changes = {}
        reasons = {}
        comparisons = {}
        for period in ((1, 5, 20) if commodity else (1,)):
            if len(sessions) <= period:
                reasons[period] = '비교 거래일 미확인'
                continue
            prior_day = sessions[-period-1].date()
            prior_cutoff = pd.Timestamp(datetime.combine(prior_day, observed.time(), ET))
            try:
                previous, previous_at = last_intraday(provider, symbol, prior_cutoff)
                if previous_at != prior_cutoff:
                    raise ValueError('동일 시각 완료 봉 없음')
                comparisons[period] = {'value': previous, 'observed_at': previous_at.isoformat()}
                if level > 0 and previous > 0:
                    changes[period] = finite((level / previous - 1) * 100)
                else:
                    reasons[period] = '비교 가격이 양수가 아니어서 가격 변화율 미계산'
            except Exception as exc:
                label_period = '직전 거래일' if period == 1 else f'{period}거래일 전'
                reasons[period] = f'{label_period} {prior_cutoff:%H:%M} ET 완료 5분 봉 미확인({error_reason(exc)})'
        note = '기준 이내 마지막 완료 5분 봉과 같은 ET 시각에 끝난 과거 봉을 비교'
        extra = {}
        if commodity:
            note += '; Yahoo 연속 선물이라 롤 영향 가능. 계약월·롤 일자·잠정치 여부 미확인'
            extra.update({f'return_{period}d': changes.get(period) for period in (1, 5, 20)})
            extra.update(contract_month=None, rollover='unknown', preliminary=None,
                         price_basis='Yahoo 연속 선물 5분 봉. 계약별 결제가격 미확인',
                         comparison_observations=comparisons, comparison_gaps=reasons)
        add('매크로', label, level, quote_url(symbol), unit=unit,
            period=cutoff.date().isoformat(), observed_at=observed.isoformat(),
            previous_value=comparisons.get(1, {}).get('value'),
            previous_observed_at=comparisons.get(1, {}).get('observed_at'),
            change_pct=changes.get(1), change_reason=reasons.get(1),
            status='partial' if reasons else 'available',
            reason=' · '.join(reasons.values()) or None,
            symbol=symbol, source_kind='secondary', note=note, **extra)


def add_crypto(provider, pair, label, cutoff, add):
    """Compare completed 5-minute candles at the cutoff and elapsed UTC horizons."""
    anchors = {'close': 0, 'return_24h': 1, 'return_7d': 7, 'return_30d': 30}
    source = BITSTAMP_OHLC_URL.format(pair=pair)
    current = cutoff.tz_convert('UTC').floor('5min')
    points = {}
    failures = {}
    for key, days in anchors.items():
        end = current - pd.Timedelta(days=days)
        try:
            candles = provider.crypto_candles(pair, end)
            chosen = bounded_bars(candles, end - BAR_SIZE, end)
            if len(chosen) != 1 or not (value := finite(chosen['Close'].iloc[0])) or value < 0:
                raise ValueError('경계 시각의 완료 5분 봉 미확인')
            points[key] = {'observed_at': end.isoformat(), 'value': value}
        except Exception as exc:
            failures[key] = error_reason(exc)
    close = points.get('close', {}).get('value')
    values = {'close': close}
    for key in tuple(anchors)[1:]:
        values[key] = (finite((close / points[key]['value'] - 1) * 100)
                       if close is not None and key in points else None)
    return add('매크로', label, values if close is not None else None, source,
               unit='USD / 변화 %', period=cutoff.date().isoformat(),
               status='unavailable' if close is None else 'partial' if failures else 'available',
               reason='미확인 봉: ' + ', '.join(f'{key} ({reason})' for key, reason in failures.items())
               if failures else None, observed_at=points.get('close', {}).get('observed_at'),
               source_kind='exchange', calculations=points, source_failures=failures,
               note='Bitstamp 현물 거래소 표본. 기준 시각까지 완료된 UTC 5분 봉의 종가로 경과 시간별 변화율 계산')
