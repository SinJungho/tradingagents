## ADDED Requirements

### Requirement: 표본 실적 공시 확인

시스템 MUST 보고 대상일의 고정 기업 표본에서 SEC EDGAR submissions의 8-K Item 2.02를 확인하고, `acceptanceDateTime`을 미국 동부시간으로 변환해 대상일을 판정해야 한다. 표본 조회 결과는 한 요약 항목에 모으고, 일치 제출이 없는 종목별 결측 항목을 만들지 않아야 한다. 제출 종목만 공식 공시 링크와 접수 시각이 있는 종목별 항목을 만들어야 한다. 일부 SEC 조회 실패는 실패 종목을 적은 partial 요약으로, 전부 실패는 unavailable 요약으로 표시해야 한다. 기존 다음 거래일 실적 예정 항목은 유지해야 한다.

#### Scenario: 대상일에 8-K Item 2.02가 제출됨

- **WHEN** SEC submissions의 8-K 항목에 Item 2.02가 있고 `acceptanceDateTime`을 동부시간으로 바꾼 날짜가 보고 대상일일 때
- **THEN** 보고서는 해당 기업의 공식 공시 링크와 동부시간 접수 시각을 표시하고 표본 요약에 그 종목을 포함한다

#### Scenario: 대상일에 제출이 없는 정상 확인일

- **WHEN** 표본의 SEC 조회가 모두 성공했고 대상일 동부시간 기준 Item 2.02 제출이 하나도 없을 때
- **THEN** 보고서는 표본 확인 요약 하나만 available로 표시하고 종목별 결측 또는 가이던스 미확인 항목을 만들지 않는다

#### Scenario: 표본 일부 또는 전체의 SEC 조회가 실패함

- **WHEN** SEC submissions 조회가 일부 종목에서 실패하거나 표본 전체에서 실패할 때
- **THEN** 보고서는 실패 종목을 담은 요약을 각각 partial 또는 unavailable로 표시하고 실패별 종목 행을 만들지 않는다

#### Scenario: 다음 거래일 예정 실적을 수집함

- **WHEN** 보고서가 기존 다음 거래일 실적 일정을 수집할 때
- **THEN** 기존 Yahoo 예정일 항목의 동작을 유지한다

### Requirement: 실적 EPS 2차 출처와 서프라이즈 계산

시스템 MUST 8-K Item 2.02 제출 종목에 대해 Yahoo `Reported EPS`와 `EPS Estimate`를 2차 출처로 표시해야 한다. 두 값이 모두 유효하고 예상 EPS가 0이 아닐 때만 `((Reported EPS - EPS Estimate) / abs(EPS Estimate)) * 100`으로 서프라이즈를 계산하고 식을 남겨야 하며, 해당 종목의 Yahoo 대상일 행이 없거나 값이 불완전하면 그 EPS 항목만 partial로 표시해야 한다.

#### Scenario: 제출이 확인된 종목의 Yahoo EPS 값 일부가 없음

- **WHEN** Item 2.02 제출 종목의 Yahoo 대상일 행 또는 Reported EPS·EPS Estimate 중 일부가 없을 때
- **THEN** 해당 종목의 EPS 항목만 partial로 표시하고, 두 EPS가 모두 유효할 때만 명시된 식으로 서프라이즈를 계산한다

### Requirement: 실적 가이던스 미확인 표시

시스템 MUST 구조화된 무료 가이던스 출처가 없으면 가이던스를 미확인으로 표시하되, 대상일 8-K Item 2.02 제출이 하나 이상 확인된 경우에만 가이던스 항목을 추가해야 한다.

#### Scenario: 제출 종목이 있고 가이던스 출처가 없음

- **WHEN** 대상일 Item 2.02 제출 종목이 하나 이상 있고 구조화된 무료 가이던스 출처가 없을 때
- **THEN** 보고서는 가이던스 항목을 미확인으로 표시한다
