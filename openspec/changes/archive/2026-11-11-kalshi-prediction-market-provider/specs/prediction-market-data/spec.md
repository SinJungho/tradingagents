# 예측시장 자료 명세

## Purpose

선택 자료로 공개 예측시장 가격을 읽고, 수치의 출처와 제한을 분석가에게 전달한다.

## ADDED Requirements

### Requirement: Kalshi 공개 자료 조회

시스템 MUST 설정된 `prediction_markets` 공급자만 사용해야 한다. 기본 설정은 Kalshi이며 Polymarket을 명시 설정으로 선택할 수 있어야 한다. Kalshi 구현은 인증 없는 공개 시장 데이터 GET 요청만 사용해야 하며 주문·계좌·쓰기 API를 호출해서는 안 된다. 열린 시장의 Yes 가격은 원본 가격 필드와 출처를 명시하고, 조회 시각을 함께 제공해야 한다.

#### Scenario: Kalshi 시장 조회

- **WHEN** 현재 기준일 분석에서 `get_prediction_markets`가 Kalshi로 라우팅될 때
- **THEN** Kalshi 공개 자료에서 찾은 열린 주제 관련 시장과 가격의 출처·조회 시각을 반환한다

#### Scenario: 설정으로 Polymarket 선택

- **WHEN** 사용자가 `prediction_markets` 공급자를 `polymarket`으로 명시할 때
- **THEN** 해당 요청은 Polymarket 구현으로만 라우팅된다

#### Scenario: 과거 기준일

- **WHEN** 요청한 분석 기준일이 오늘보다 과거일 때
- **THEN** 시스템은 현재 Kalshi 가격을 과거 정보인 것처럼 제공하지 않고 과거 자료를 지원하지 않는다고 알린다

### Requirement: 검색 범위와 실패의 정직한 표시

공급자는 주제에 일치하는 후보 시리즈를 제한된 범위에서 검색해야 한다. 검색이 제한되었거나 일치 자료가 없을 때 결과는 Kalshi 전체 시장의 부재를 뜻하지 않는다고 밝혀야 한다. 연결·응답 오류는 선택 자료 실패 집계에 기록하고, 모델이 가격을 추정하거나 만들어 내지 않도록 안내해야 한다. 공급자는 조회 불가 값을 명확히 표시하고, 제한된 검색을 전수 검색처럼 암시하지 않아야 한다(MUST NOT).

#### Scenario: 제한된 후보 조회에서 일치 시장 없음

- **WHEN** 공급자가 조회한 후보 시리즈에서 주제 일치 시장을 찾지 못할 때
- **THEN** 제한된 검색 범위를 밝히고 Kalshi에 시장이 없다고 단정하지 않는다

#### Scenario: 공급자 연결 실패

- **WHEN** Kalshi API 호출이 연결·시간 초과 또는 HTTP 오류로 실패할 때
- **THEN** 오류를 `get_prediction_markets` 실패로 기록하고 추정하지 말라는 명시적 안내를 반환한다
