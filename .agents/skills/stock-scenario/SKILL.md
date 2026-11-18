---
name: stock-scenario
description: 지정한 종목을 TradingAgents 그래프로 분석하고 매수·보유·매도 조건부 시나리오를 만든다. "TQQQ 매수 시나리오", "NVDA 분석해줘", "이 종목 팔아야 해?", "비중 얼마나", "보유 주식 반영해서 매매 시나리오" 요청에 사용한다. 티커 목록의 팩터 신호 확인이나 시장 전체 후보 탐색은 stock-discovery를 쓴다.
---

# 종목 분석과 투자 시나리오

`AGENTS.md`의 Single-stock analysis / Investment scenario 흐름을 따른다.

## 1. 경로 선택

기본 경로는 토스 실계좌 보유를 반영하는 `portfolio live`다. 매수·매도·비중 판단은 현재 보유와 통화별 비중을 알아야 의미가 있다. 실계좌 읽기 전용 조회는 저장소 소유자가 사전 허용했으므로 허용을 묻지 않는다.

| 순서 | 상황 | 명령 |
| --- | --- | --- |
| 1 (기본) | 매수·보유·매도·비중 요청. 대상 종목은 보유 여부와 무관(미보유는 관심종목으로 분석) | `tradingagents portfolio live --symbol <T>` |
| 2 | 사용자가 실계좌 대신 보유 현황 JSON 파일을 줌 | `tradingagents --ticker <T> --date <YYYY-MM-DD> --portfolio <file.json> --analysts market,news,fundamentals --save --no-show` |
| 3 | 보유와 무관한 순수 종목 분석 요청 | `tradingagents --ticker <T> --date <YYYY-MM-DD> --analysts market,news,fundamentals --save --no-show` |

- 실계좌 조회가 설정 문제로 실패하면(토스 환경변수 누락·인증 실패) 원인을 알리고 `api-doctor` skill로 넘기거나 2·3번 경로를 제안한다.
- 1번은 `portfolio-check` skill의 실행 조건(환경변수 이름, 계좌 선택)을 먼저 확인한다. 여러 종목이면 `--symbol`을 반복한다(최대 `--max-symbols`). 기본은 경량 경로이고, 사용자가 심층 분석, Bull/Bear 토론, Trader·Risk·Portfolio Manager 결정을 요청한 경우에만 `--full-workflow`를 추가한다.
- 과거 날짜 분석은 1번으로 할 수 없다(실계좌는 현재 시점). 과거 기준일이 필요하면 2·3번을 쓴다.
- `--analysts`는 `market`, `sentiment`, `news`, `fundamentals` 중에서 고른다. 생략하면 상품 유형이 허용하는 분석가를 모두 실행한다. 사용자가 범위를 정하지 않았으면 표의 기본 조합을 쓴다.
- 2·3번은 터미널 없이 실행하므로 질문 단계를 모두 플래그로 채운다. 답이 빠지면 실행 전에 멈추고 필요한 플래그·변수 이름을 알려 준다. `--html`은 기본으로 `complete_report.html`도 만든다. 모델·출력 언어·토론 횟수는 `TRADINGAGENTS_LLM_PROVIDER`, `TRADINGAGENTS_DEEP_THINK_LLM`, `TRADINGAGENTS_QUICK_THINK_LLM`, `TRADINGAGENTS_OUTPUT_LANGUAGE`, `TRADINGAGENTS_MAX_DEBATE_ROUNDS`, `TRADINGAGENTS_MAX_RISK_ROUNDS`로 정한다(값은 `.env`에서 읽고 출력하지 않는다). 중간에 멈춘 실행은 `--checkpoint`로 이어간다.
- 모든 실행은 다른 명령과 묶지 않은 단독 명령으로 하고, `--ticker`는 첫 인자로 둔다. 실제 LLM을 호출하므로 사용자가 분석을 요청했을 때만 실행한다.
- 티커 목록의 결정론적 팩터 신호나 시장 전체 후보가 필요하면 `stock-discovery` skill로 먼저 후보를 고르고, 사용자가 고른 종목만 이 흐름으로 분석한다.

## 2. 결과 읽기

- 2·3번 보고서는 `results_dir/reports/<티커>_<시각>/complete_report.md`에 저장된다(`results_dir` 기본값 `~/.tradingagents/logs`, `TRADINGAGENTS_RESULTS_DIR`로 변경). 1번은 `~/.tradingagents/portfolio/portfolio_live_<시각>.{json,md}`다.
- 보고서 구성: I. Analyst Team Reports, II. Research Team Decision(Bull/Bear, Research Manager), III. Trading Team Plan(Trader), IV. Risk Management Team Decision(Aggressive/Conservative/Neutral), V. Portfolio Manager Decision, VI. Data Source Failures, Output Quality Review Warnings. 내용이 있는 섹션만 나온다.
- Output Quality Review Warnings는 근거 자료에서 확인되지 않은 수치 후보와 제공 보유 상태와 직접 충돌하는 표현을 결정론적으로 표시한다. 경고된 수치는 근거로 옮기지 않는다.
- VI. Data Source Failures는 선택 자료 조회 실패를 메서드·오류 범주·재시도 가능 여부·횟수로 보여 준다. 실패한 자료는 미확인으로 보고하고 0이나 추정값으로 채우지 않는다.
- 예측시장(기본 Polymarket) 확률은 제한된 검색 범위의 후보 시장 결과다. 일치 시장이 없다는 것이 시장 부재를 뜻하지 않는다고 밝힌다.

## 3. 상품 특성 확인

- ETF·레버리지 ETF(TQQQ, SOXL 등)는 기업 재무(EPS·ROE)가 없다. 펀드 개요·보유 종목·비용률을 근거로 쓰고, 레버리지 상품은 일간 재조정에 따른 변동성 손실과 보유기간 위험을 반드시 다룬다.
- `style_scores`는 개별 기업 전용이며 `style-backtest`에서 예측력이 확인되지 않았으므로 매매 근거로 쓰지 않는다.

## 4. 보고 형식

1. 결론 한 줄: 최종 등급(Buy/Overweight/Hold/Underweight/Sell)과 근거 요약
2. 근거: 기본 경량 경로는 Market·News·Fundamentals 분석과 포트폴리오 종합의 핵심을 보고한다. 전체 워크플로를 요청한 경우에만 Bull/Bear 쟁점, Research Manager, Trader·Risk·Portfolio Manager 결정을 포함한다. 수치에는 출처와 기준 시각을 붙인다.
3. 포트폴리오 영향: 현재 비중, 추가 매수·매도 시 통화별 비중 변화(계산 가능한 경우만). 거래 표현은 제공 보유 상태에 맞춘다(미보유: 신규 진입, 보유: 추가·유지·축소·청산, 음수 수량: 숏). 보유 정보가 없으면 보유를 가정하지 않는다.
4. 조건부 시나리오: 매수·보유·매도 각각의 실행 조건(가격 구간, 지표, 이벤트), 손절·재검토·무효화 조건. `portfolio live` 경로는 단기·중기·장기 × 상승·기본·하락 구조를 따른다.
5. 자료 기준 시각, 품질 경고, 자료 조회 실패와 미확인 자료

계산 근거가 없는 목표가·기대수익은 쓰지 않는다. 분석이 TradingAgents 그래프 결과인지, 그래프 없이 내가 직접 정리한 것인지 구분해 밝힌다.
