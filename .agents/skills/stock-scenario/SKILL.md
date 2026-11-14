---
name: stock-scenario
description: 지정한 종목을 TradingAgents 그래프로 분석하고 매수·보유·매도 조건부 시나리오를 만든다. "TQQQ 매수 시나리오", "NVDA 분석해줘", "이 종목 팔아야 해?", "비중 얼마나", "보유 주식 반영해서 매매 시나리오" 요청에 사용한다. 사용자가 준 티커 목록의 결정론적 팩터 신호 확인은 `tradingagents discover --tickers <T1,T2>`를 안내하고, 시장 전체 후보 탐색 요청에는 `tradingagents discover --universe all` 또는 `--universe <section,...>`을 안내한다.
---

# 종목 분석과 투자 시나리오

`AGENTS.md`의 Single-stock analysis / Investment scenario 흐름을 따른다.

## 1. 경로 선택

기본 경로는 토스 실계좌 보유를 반영하는 `portfolio live`다. 매수·매도·비중 판단은 현재 보유와 통화별 비중을 알아야 의미가 있다.

| 순서 | 상황 | 명령 |
| --- | --- | --- |
| 1 (기본) | 실계좌 조회를 허용받음. 대상 종목은 보유 여부와 무관(미보유는 관심종목으로 분석) | `tradingagents portfolio live --symbol <T>` |
| 2 | 실계좌 허용이 없고 보유 현황을 JSON 파일로 줌 | `tradingagents --ticker <T> --date <YYYY-MM-DD> --portfolio <file.json>` |
| 3 | 보유와 무관한 순수 종목 분석 요청 | `tradingagents --ticker <T> --date <YYYY-MM-DD>` |

- 매매·비중 요청인데 실계좌 허용이 없으면 1번을 실행하지 말고, "실계좌 조회(읽기 전용)와 LLM 분석을 허용하면 보유를 반영해 분석한다"고 한 번 안내한 뒤 사용자가 고른 경로로 간다. 이미 이번 대화에서 허용했다면 다시 묻지 않는다.
- 1번은 `portfolio-check` skill의 실행 조건(환경변수 이름, 계좌 선택)을 먼저 확인한다. 여러 종목이면 `--symbol`을 반복한다(최대 `--max-symbols`).
- 기본 시나리오 분석은 경량 경로를 쓴다. 사용자가 심층 분석, Bull/Bear 토론, Trader·Risk·Portfolio Manager 결정을 요청한 경우에만 1번 명령에 `--full-workflow`를 추가한다.
- 과거 날짜 분석은 1번으로 할 수 없다(실계좌는 현재 시점). 과거 기준일이 필요하면 2·3번을 쓴다.
- 사용자가 준 티커 목록의 결정론적 팩터 신호 확인에는 `tradingagents discover --tickers <T1,T2>`를 안내한다. 시장 전체 후보 탐색은 `tradingagents discover --universe all`로, 선택 구간 탐색은 `--universe sp500,sp600,smallcap`처럼 실행한다. `russell2000` 구간은 iShares 출처가 CSV 대신 HTML을 반환하는 동안 실패하므로 원인을 그대로 전하고 다른 구간을 대안으로 안내한다. 이 탐색은 Yahoo·SEC 공개 데이터의 결정론적 신호만 계산하고 LLM을 자동 호출하지 않는다. 결과의 2차 구성 목록, Russell 2000 ETF 보유종목 프록시, 시가총액 구간 기준을 알린다. 후보를 사용자가 최대 10개 직접 선택한 뒤 각 티커에 기존 단일 종목 분석 흐름을 적용한다.
- 모든 실행은 다른 명령과 묶지 않은 단독 명령으로 하고, `--ticker`는 첫 인자로 둔다.

## 2. 상품 특성 확인

- ETF·레버리지 ETF(TQQQ, SOXL 등)는 기업 재무(EPS·ROE)가 없다. 펀드 개요·보유 종목·비용률을 근거로 쓰고, 레버리지 상품은 일간 재조정에 따른 변동성 손실과 보유기간 위험을 반드시 다룬다.
- `style_scores`는 개별 기업 전용이며 예측력이 확인되지 않았으므로 매매 근거로 쓰지 않는다.

## 3. 보고 형식

1. 결론 한 줄: 최종 등급(Buy/Overweight/Hold/Underweight/Sell)과 근거 요약
2. 근거: 기본 경량 경로는 Market·News·Fundamentals 분석과 포트폴리오 종합의 핵심을 보고한다. 전체 워크플로를 요청한 경우에만 Bull/Bear 쟁점, Research Manager, Trader·Risk·Portfolio Manager 결정을 포함한다.
3. 포트폴리오 영향: 현재 비중, 추가 매수·매도 시 통화별 비중 변화(계산 가능한 경우만)
4. 조건부 시나리오: 매수·보유·매도 각각의 실행 조건(가격 구간, 지표, 이벤트), 손절·재검토 조건
5. 자료 기준 시각과 미확인 자료

계산 근거가 없는 목표가·기대수익은 쓰지 않는다. 분석이 TradingAgents 그래프 결과인지, 그래프 없이 내가 직접 정리한 것인지 구분해 밝힌다.
