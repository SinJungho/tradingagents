# Polymarket 연결 복원력 명세

## ADDED Requirements

### Requirement: 실행 단위 Polymarket 연결 실패 차단

시스템 MUST 하나의 분석 실행에서 Polymarket 연결·DNS·타임아웃 오류가 발생한 뒤 같은 실행의 후속 예측시장 조회를 네트워크 요청 없이 차단해야 한다. 차단된 각 조회는 기존 데이터 출처 실패 기록에 포함되어야 한다. 시스템 MUST 실행 실패 기록을 drain할 때 차단 상태를 초기화해야 한다.

#### Scenario: 첫 조회에서 연결 오류

- **WHEN** 실행 중 Polymarket 요청이 연결·DNS·타임아웃 오류로 실패하고 이후 같은 실행에서 다른 주제의 예측시장 조회가 발생할 때
- **THEN** 첫 조회는 실패를 기록하고, 후속 조회는 네트워크 요청 없이 unavailable 대체 문구를 반환한다
- **AND** 두 조회 모두 출처 실패 기록에 포함된다

#### Scenario: 분석 실행 종료 후 상태 초기화

- **WHEN** 실행의 출처 실패 기록을 drain할 때
- **THEN** 이후 분석 실행은 Polymarket 네트워크 조회를 다시 시도할 수 있다

### Requirement: 예측시장 unavailable 문구의 추정 금지 지시

시스템 MUST 예측시장 자료를 조회할 수 없을 때 모델이 예측시장 확률이나 수치를 작성 또는 추정하지 말고 출처가 unavailable이라고 밝히도록 대체 문구에 명시해야 한다.

#### Scenario: 연결 실패 또는 차단된 조회

- **WHEN** Polymarket 자료를 네트워크 오류 또는 실행 단위 차단으로 제공할 수 없을 때
- **THEN** 반환 문구는 예측시장 수치를 쓰거나 추정하지 말라고 모델에 지시하고 자료를 unavailable로 표시한다
