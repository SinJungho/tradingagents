## MODIFIED Requirements

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
