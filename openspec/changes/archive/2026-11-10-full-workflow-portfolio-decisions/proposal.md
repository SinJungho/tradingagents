# Proposal

## Why

`portfolio live`의 기본 분석 경로는 종목 조사와 기간별 포트폴리오 시나리오만 수행한다. TradingAgents의 종목별 Trader, Risk debate, Portfolio Manager 최종 결정을 기존 보유 현황에 연결해 실제 보유를 고려한 매매 검토 자료를 제공한다.

## What Changes

- 명시적 `--full-workflow` 옵션으로 기존 TradingAgents 전체 결정 그래프를 종목별로 실행한다.
- 정규화된 전체 보유 종목·수량·평균 매입가·통화만 그래프에 전달한다. 실제 현금 자료가 없으면 매수 가능 금액을 현금으로 대체하지 않는다.
- 기존 종목 분석 결과를 재사용해 시장·뉴스·펀더멘털 조사와 기간별 포트폴리오 시나리오를 유지하면서 Trader 계획, Risk 토론, Portfolio Manager 결정을 로컬 보고서에 기록한다.
- 기본 조사 모드의 비용과 결과는 유지한다. 주문 실행·수정·취소는 범위에 포함하지 않는다.

## Capabilities

### Modified Capabilities

- `portfolio-scenario-analysis`: 선택형 전체 TradingAgents 결정 단계를 보유 현황에 연결하고 안전하게 보고한다.

## Impact

- `cli/portfolio.py`, 포트폴리오 시나리오·보고서 모델, CLI 및 포트폴리오 컨텍스트 테스트, `docs/portfolio-analysis.md`.
- 실제 LLM 호출은 `--full-workflow`를 지정한 경우에만 늘어난다. 브로커 사용은 기존 읽기 전용 조회 경로로 제한한다.
