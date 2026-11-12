---
name: backtest-eval
description: TradingAgents 결정이나 스타일 점수의 과거 성과를 백테스트하고 결과를 한계와 함께 해석한다. "백테스트 돌려줘", "이 전략 예측력 있어?", "style-backtest", "과거 성과 검증", "신호가 맞았는지" 요청에 사용한다.
---

# 백테스트와 예측력 평가

## 1. 도구 선택

| 평가 대상 | 명령 | LLM 호출 |
| --- | --- | --- |
| 그래프 전체 결정(등급) | `tradingagents backtest <T1,T2> --start <D> --end <D> --every 7 [--analysts market,news]` | 셀마다 전체 그래프 실행 |
| 코드 계산 스타일 점수 | `tradingagents style-backtest <T1,T2> --start <D> --end <D> --every 30` | 없음 |

- `backtest`는 비용이 크다. 실행 전에 셀 수(티커 × 날짜)와 대략의 LLM 호출 수를 알리고 사용자 허용을 받는다. 중단된 실행은 `--run-id`로 이어간다.
- `style-backtest`는 네트워크 자료만 쓰므로 바로 실행해도 된다. 가격 이력이 약 5년이라 모멘텀은 1년, 가치·성장·품질은 앞뒤 1년씩 여유가 필요하다.

## 2. 종목군

- "내 보유 종목으로 검증해줘"면 토스 실계좌에서 **종목 목록만** 가져온다(실계좌 조회 허용 필요). LLM 시나리오 없이 조회만 한다:

  ```bash
  tradingagents portfolio live --no-scenarios
  ```

  새로 생긴 `~/.tradingagents/portfolio/portfolio_live_<시각>.json`의 `positions[].symbol`과 `market_country`만 읽는다. 수량·평가액 등 다른 값은 읽거나 옮기지 않는다. `market_country`가 `US`인 종목은 그대로 쓰고, 한국 종목은 `backtest`에서만 Yahoo 접미사(`.KS`/`.KQ`)를 붙여 쓴다. `style-backtest`는 SEC 공시 기업(미국)만 된다.
- 실계좌의 현재 수량·평단은 백테스트에 넣지 않는다. 오늘의 보유를 과거 날짜 분석에 주면 그때 없던 정보가 들어간다. `--portfolio`가 꼭 필요하면 과거 시점을 가정한 JSON을 사용자에게 받는다.
- 오늘 고른 종목(보유 종목 포함)만 쓰면 생존편향과 선택편향이 생긴다. 지금 들고 있는 종목은 대개 그동안 잘 오른 종목이다. 업종을 섞고 부진 종목도 포함하며, 결과에 편향을 명시한다.
- 과거 지수 구성종목 자료(FMP 등)가 없으면 "전체 시장 성과"라고 쓰지 않는다.

## 3. 해석 기준

- 등급·신호별 건수, 적중률, 평균과 중앙값 초과수익을 함께 본다. 평균만 보면 소수 대형 수익 종목에 끌린다.
- 예측력 판정: Bullish > Neutral > Bearish 순서가 평균과 중앙값 모두에서 나타나고 건수가 충분할 때만 "예측력 있음"이라고 쓴다.
- 보유기간이 겹치는 월별 격자는 독립 관측치가 적다. `backtest` 기본 보유기간은 5거래일이라 장기 신호 채점에 맞지 않는다.
- 결과를 OpenSpec 변경 README나 보고서에 남길 때는 표본, 기간, 벤치마크, 보유기간, 한계를 함께 적는다.

이전 결과: `openspec/changes/archive/2026-11-11-style-factor-scores/README.md`.
