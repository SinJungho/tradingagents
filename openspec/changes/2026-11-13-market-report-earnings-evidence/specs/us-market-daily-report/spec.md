## ADDED Requirements

### Requirement: 실적 발표 확인과 값 출처

시스템 MUST 보고 대상일의 고정 기업 표본에서 SEC EDGAR submissions의 8-K Item 2.02를 확인하고, `acceptanceDateTime`을 미국 동부시간으로 변환해 대상일을 판정해야 한다. 제출 확인 항목은 공식 공시 링크와 접수 시각을 표시해야 하며, 일치 항목이 없거나 조회에 실패하면 그 상태를 구분하고 실적 발표 자체가 없었다고 단정해서는 안 된다. Yahoo `Reported EPS`와 `EPS Estimate`는 2차 출처로 표시해야 하며, 두 값이 모두 유효하고 예상 EPS가 0이 아닐 때만 `((Reported EPS - EPS Estimate) / abs(EPS Estimate)) * 100`으로 서프라이즈를 계산하고 식을 남겨야 한다. 구조화된 무료 가이던스 출처가 없으면 가이던스를 미확인으로 둬야 한다. 기존 다음 거래일 실적 예정 항목은 유지해야 한다.

#### Scenario: 대상일에 8-K Item 2.02가 제출됨

- **WHEN** SEC submissions의 8-K 항목에 Item 2.02가 있고 `acceptanceDateTime`을 동부시간으로 바꾼 날짜가 보고 대상일일 때
- **THEN** 보고서는 해당 기업의 공식 공시 링크와 동부시간 접수 시각을 표시한다

#### Scenario: 대상일에 일치하는 제출이 없거나 SEC 조회가 실패함

- **WHEN** 대상일 동부시간 기준 Item 2.02 제출이 없거나 SEC 데이터를 읽지 못할 때
- **THEN** 보고서는 조회 결과 없음과 자료 조회 실패를 구분하고, 실적 발표 부재로 단정하지 않는다

#### Scenario: Yahoo EPS 값의 일부가 없거나 가이던스 출처가 없음

- **WHEN** Yahoo 행에 Reported EPS 또는 EPS Estimate가 없거나 구조화된 무료 가이던스 출처가 없을 때
- **THEN** Yahoo EPS 자료를 2차 출처로 표시하고, 두 EPS가 모두 유효할 때만 명시된 식으로 서프라이즈를 계산하며, 가이던스는 미확인으로 둔다

#### Scenario: 다음 거래일 예정 실적을 수집함

- **WHEN** 보고서가 기존 다음 거래일 실적 일정을 수집할 때
- **THEN** 기존 Yahoo 예정일 항목의 동작을 유지한다
