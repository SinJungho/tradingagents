# agent-request-harness Specification

## Purpose
투자 리서치 요청을 유형별로 분류하고 같은 유형의 반복 요청에 같은 처리 흐름을 적용하는 저장소 에이전트 규칙을 정의한다.

## Requirements

### Requirement: 요청 유형 분류

저장소 에이전트 MUST 투자 리서치 요청을 포트폴리오 점검, 종목 발굴, 단일 종목 분석, 투자 시나리오 중 하나로 분류하고 유형별로 정해진 처리 흐름을 적용해야 한다. 같은 유형의 반복 요청에는 같은 흐름과 기본값을 적용해야 한다. 종목 시나리오는 사전 허용된 `tradingagents portfolio live --symbol <T>`의 기본 경량 경로를 사용해야 하며, `--full-workflow`는 사용자가 심층 분석을 요청한 경우에만 사용해야 한다. 사용자가 보유 JSON 파일을 제공한 경우에는 `tradingagents --ticker <T> --date <D> --portfolio <file.json>`를 사용해야 한다.

#### Scenario: 종목이 지정된 요청

- **WHEN** 사용자가 티커를 지정해 분석을 요청할 때
- **THEN** 에이전트는 단일 종목 분석으로 분류하고 종목 발굴 단계를 건너뛴다

#### Scenario: 심층 분석을 지정하지 않은 포트폴리오 점검

- **WHEN** 사용자가 심층 분석을 지정하지 않고 포트폴리오 점검을 요청할 때
- **THEN** 에이전트는 일반 요약 모드를 사용하고 `--full-workflow`는 사용자가 지정한 경우에만 사용한다

#### Scenario: 티커 목록을 제공한 결정론적 종목 발굴

- **WHEN** 사용자가 평가할 티커 목록을 제공할 때
- **THEN** 에이전트는 `tradingagents discover --tickers <T1,T2>`를 실행하고 해당 티커의 기존 결정론적 팩터 신호만 안내한다

#### Scenario: 실계좌를 허용한 종목 시나리오

- **WHEN** 사용자가 티커 매수·보유·매도 시나리오를 요청할 때
- **THEN** 에이전트는 허용을 다시 묻지 않고 `tradingagents portfolio live --symbol <T>`의 기본 경량 경로로 현재 보유를 반영한다
- **AND** 심층 분석을 요청하지 않으면 `--full-workflow`를 사용하지 않는다

#### Scenario: 보유 JSON을 제공한 종목 시나리오

- **WHEN** 사용자가 실계좌 조회 대신 보유 JSON 파일을 제공할 때
- **THEN** 에이전트는 `tradingagents --ticker <T> --date <D> --portfolio <file.json>`로 해당 보유 정보를 반영한다

### Requirement: 질문 최소화

저장소 에이전트 MUST 저장소·설정·이전 대화에서 확인 가능한 정보는 다시 묻지 않아야 한다. 결과를 바꾸는 필수 입력이 없을 때만 사용자에게 질문해야 한다.

#### Scenario: 필수 입력 누락

- **WHEN** 투자 시나리오 요청에 대상 종목이나 보유 정보가 없고 저장소에서도 확인할 수 없을 때
- **THEN** 에이전트는 누락된 입력만 질문한다

### Requirement: 미구현 기능 처리

저장소 에이전트 MUST 현재 CLI에 없는 기능을 실행된 것처럼 보고해서는 안 된다. 지정된 티커 목록의 결정론적 발굴은 `tradingagents discover`로 지원되며, 시장 전체 후보는 `tradingagents discover --universe all` 또는 `sp500,sp600,smallcap` 등 구간으로 지원됨을 안내해야 한다. Russell 2000 구간은 공개 출처 상태에 따라 실패로 표시될 수 있음을 함께 알려야 한다. 팩터 간 통합 순위나 LLM 분석이 아니며 출처·실패 범위를 밝혀야 한다. 새 기능 구현이 필요하면 OpenSpec 변경을 먼저 만들어야 한다.

#### Scenario: 시장 전체 발굴 지원

- **WHEN** 사용자가 티커 목록 없이 시장 전체 종목 발굴을 요청할 때
- **THEN** 에이전트는 `tradingagents discover --universe all`을 안내하고 선택된 종목만 단일 종목 분석으로 연결한다

#### Scenario: 지정 티커 발굴 지원

- **WHEN** 사용자가 발굴할 티커 목록을 제공할 때
- **THEN** 에이전트는 기존 팩터 계산을 사용하는 `tradingagents discover --tickers <T1,T2>`를 안내한다

#### Scenario: 종목 발굴 명령 부재

- **WHEN** 사용자가 현재 CLI에 없는 발굴 명령이나 옵션을 요청할 때
- **THEN** 에이전트는 이를 실행했다고 주장하지 않고 지원되는 `discover --universe` 범위를 안내하며 새 동작은 OpenSpec 변경으로 진행한다

#### Scenario: Russell 2000 구간 출처 실패

- **WHEN** 사용자가 Russell 2000 구간 발굴을 요청하고 공개 보유 종목 출처가 CSV를 제공하지 않을 때
- **THEN** 에이전트는 구간 실패 원인을 그대로 전하고 `sp600`·`smallcap` 같은 다른 구간을 대안으로 안내한다

### Requirement: 실계좌·LLM 실행 조건

저장소 에이전트 MUST 토스 실계좌 읽기 전용 조회와 `tradingagents portfolio live`의 기본 LLM 요약을 사전 허용된 실행으로 다루고 허용을 다시 묻지 않아야 한다. `--full-workflow`는 사용자가 심층 분석을 요청한 경우에만 사용해야 하며, 그 밖의 실제 LLM 분석(`--ticker`, `backtest`, `market-report`)도 사용자의 명시적 요청이 있을 때만 실행해야 한다. 브로커 접근은 조회 전용이어야 하며 주문 관련 호출을 실행해서는 안 된다. 계산 근거가 없는 목표 가격이나 목표 수익률을 제시해서는 안 된다.

#### Scenario: 실행 방식이 명시되지 않은 점검 요청

- **WHEN** 사용자가 실행 방식을 따로 정하지 않고 포트폴리오 점검을 요청할 때
- **THEN** 에이전트는 허용을 다시 묻지 않고 `tradingagents portfolio live`로 실계좌를 읽기 전용 조회하고 기본 LLM 요약을 실행한다

#### Scenario: 심층 분석 요청이 없는 포트폴리오 점검

- **WHEN** 사용자가 심층 분석을 요청하지 않고 포트폴리오 점검을 요청할 때
- **THEN** 에이전트는 기본 요약 경로를 사용하고 `--full-workflow`를 추가하지 않는다

#### Scenario: 실계좌 조회 외 LLM 실행

- **WHEN** 에이전트가 `--ticker` 분석, `backtest`, `market-report` LLM 해석을 실행하려 할 때
- **THEN** 사용자가 해당 분석을 요청한 경우에만 실행하고 실행 전 확인 훅을 거친다
