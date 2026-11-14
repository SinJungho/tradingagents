## ADDED Requirements

### Requirement: 일시 공급자 실패 2차 조회

시스템 MUST 종목 발굴의 병렬 미리 조회에서 일시적 공급자 실패(`VendorUnavailableError`)로 끝난 심볼만 한 번 더 조회하고, 그 결과를 최종 결과로 써야 한다. 자료 없음과 다른 오류는 다시 조회하지 않아야 하며, 호출 수 집계와 실패 기록 형식은 유지해야 한다.

#### Scenario: 일시 실패 뒤 회복

- **WHEN** 한 심볼의 분할 이력 조회가 첫 패스에서 `VendorUnavailableError`, 2차 조회에서 성공할 때
- **THEN** 그 종목에는 분할 이력 실패가 기록되지 않는다

#### Scenario: 자료 없음은 다시 묻지 않음

- **WHEN** 한 심볼의 조회가 `NoMarketDataError`로 끝날 때
- **THEN** 그 심볼은 2차 조회 대상이 아니다
