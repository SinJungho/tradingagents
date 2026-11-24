## ADDED Requirements

### Requirement: Tratto 차트 변경 실행 게이트

에이전트 MUST 차트 드로잉 요청에서 Tratto MCP 사전 조회와 데이터 검증 없이 변경 도구를 호출하거나 Yahoo 레이아웃 상태를 직접 수정해서는 안 된다. 드로잉 완료는 요청 라벨과 `chart-drawings-check` 통과 증거가 있을 때만 보고해야 한다.

#### Scenario: Tratto 조회 또는 데이터 검증 누락

- **WHEN** 차트 드로잉 요청에서 Tratto 조회·검증을 거치지 않은 채 변경 도구를 호출할 때
- **THEN** 실행 hook은 변경 호출을 거부하고 필요한 준비 단계를 안내한다

#### Scenario: Yahoo 레이아웃 직접 변경 시도

- **WHEN** 에이전트가 Tratto 대신 Yahoo 차트의 직렬화된 레이아웃·드로잉 상태를 편집하려 할 때
- **THEN** 실행 hook은 브라우저 호출을 거부하고 Tratto 경로를 안내한다

#### Scenario: 완료 증거 누락

- **WHEN** 드로잉 요청을 완료로 보고하려 하지만 검증기가 성공하지 않았을 때
- **THEN** 종료 hook은 완료 보고를 보류하고, 확인된 범위 또는 미완료 사유를 명시하도록 요청한다
