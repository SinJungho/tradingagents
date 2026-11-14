# portfolio-scenario-analysis Specification Delta

## ADDED Requirements

### Requirement: 보유 현황 기반 전체 결정 그래프

시스템 MUST 사용자가 `--full-workflow`를 지정하면 선택된 각 보유 종목에 대해 기존 TradingAgents의 분석가, Bull/Bear 조사 토론, Research Manager, Trader, Aggressive/Neutral/Conservative Risk 토론과 Portfolio Manager 최종 결정 단계를 순서대로 실행해야 한다. 그래프에는 계좌 식별자, 주문 이력, 원시 브로커 응답을 전달하지 않아야 한다. 현금 잔고가 확인되지 않으면 매수 가능 금액을 현금으로 간주하지 않아야 한다. 결과 보고서 MUST Trader 계획, Risk 토론, 최종 결정과 등급을 종목별로 표시하고 제안 전용으로 유지해야 한다.

#### Scenario: 전체 결정 워크플로 사용

- **WHEN** `portfolio live --full-workflow`가 선택된 보유 종목을 분석할 때
- **THEN** 기존 TradingAgents 결정 그래프가 전체 보유 현황 맥락에서 종목별로 실행된다
- **AND** 보고서에 Trader 계획, Risk 토론, Portfolio Manager 결정이 구분되어 표시된다
- **AND** 종목 조사는 전체 그래프 결과를 재사용하며 중복 조사 LLM 호출을 하지 않는다

#### Scenario: 기본 조사 모드 유지

- **WHEN** 사용자가 `--full-workflow`를 지정하지 않을 때
- **THEN** 기존 종목 조사와 포트폴리오 시나리오 경로 및 비용 특성을 유지한다

#### Scenario: 실제 현금 잔고 미확인

- **WHEN** 브로커가 실제 현금 잔고를 제공하지 않고 매수 가능 금액만 제공할 때
- **THEN** 매수 가능 금액은 Portfolio Manager 입력의 현금 잔고로 전달되지 않는다
- **AND** 각 보유 종목의 통화는 평균 매입가와 함께 명시된다

#### Scenario: 일부 종목 전체 그래프 실패

- **WHEN** 전체 결정 그래프가 일부 종목에서 실패할 때
- **THEN** 나머지 종목 분석은 보존하고 실패 종목의 안전한 오류 범주와 재시도 가능 여부를 보고한다
- **AND** 원시 예외, 인증정보, 계좌 식별자 및 원시 브로커 응답은 보고하지 않는다

