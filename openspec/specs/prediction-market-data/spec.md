# prediction-market-data Specification

## Purpose
선택 자료로 공개 예측시장 가격을 주제별로 조회하고, 가격 수치의 출처·조회 시각·검색 범위와 과거 시점 제한을 분석가 및 최종 보고서에 전달한다.

## Requirements

### Requirement: 예측시장 공급자 선택

시스템 MUST 설정된 `prediction_markets` 공급자만 사용해야 한다. 기본 설정은 Polymarket이어야 하며 Kalshi는 명시 설정으로 선택할 수 있어야 한다. 각 공급자 구현은 인증 없는 공개 시장 데이터 GET 요청만 사용해야 하며 주문·계좌·쓰기 API를 호출해서는 안 된다. 열린 시장의 가격은 원본 가격 필드와 출처를 명시하고 조회 시각을 함께 제공해야 한다.

#### Scenario: 기본 공급자로 Polymarket 조회

- **WHEN** 별도 공급자 선택 없이 현재 기준일 분석에서 `get_prediction_markets`를 호출할 때
- **THEN** Polymarket 공개 자료에서 찾은 열린 주제 관련 시장과 가격의 출처·조회 시각을 반환한다

#### Scenario: Kalshi 명시 선택

- **WHEN** 사용자가 `prediction_markets` 공급자를 `kalshi`로 명시할 때
- **THEN** 요청은 Kalshi 공개 자료 구현으로만 라우팅된다

#### Scenario: 설정으로 Polymarket 선택

- **WHEN** 사용자가 `prediction_markets` 공급자를 `polymarket`으로 명시할 때
- **THEN** 해당 요청은 Polymarket 구현으로만 라우팅된다

#### Scenario: Kalshi 시장 조회

- **WHEN** 현재 기준일 분석에서 `get_prediction_markets`가 Kalshi로 라우팅될 때
- **THEN** Kalshi 공개 자료에서 찾은 열린 주제 관련 시장과 가격의 출처·조회 시각을 반환한다

#### Scenario: 과거 기준일

- **WHEN** 요청한 분석 기준일이 오늘보다 과거일 때
- **THEN** 시스템은 현재 선택된 공급자의 가격을 과거 정보인 것처럼 제공하지 않고 과거 자료를 지원하지 않는다고 알린다

### Requirement: 검색 범위와 실패의 정직한 표시

공급자는 주제에 일치하는 후보 시장을 제한된 범위에서 검색해야 한다. 검색이 제한되었거나 일치 자료가 없을 때 결과는 선택 공급자 전체 시장의 부재를 뜻하지 않는다고 밝혀야 한다. 선택한 공급자의 연결·응답 오류는 선택 자료 실패 집계에 기록하고, 모델이 가격을 추정하거나 만들어 내지 않도록 안내해야 한다. 공급자는 조회 불가 값을 명확히 표시하고 제한된 검색을 전수 검색처럼 암시하지 않아야 한다(MUST NOT).

#### Scenario: 제한된 후보 조회에서 일치 시장 없음

- **WHEN** 공급자가 조회한 후보 시장에서 주제 일치 자료를 찾지 못할 때
- **THEN** 제한된 검색 범위를 밝히고 선택 공급자 전체에 해당 시장이 없다고 단정하지 않는다

#### Scenario: 공급자 연결 실패

- **WHEN** 선택 공급자 API 호출이 연결·시간 초과 또는 HTTP 오류로 실패할 때
- **THEN** 오류를 `get_prediction_markets` 실패로 기록하고 추정하지 말라는 명시적 안내를 반환한다

### Requirement: Polymarket 선택형 별칭 연결
시스템 MUST 공개 검색에만 기본 direct 또는 cloudfront_alias 연결을 사용하고 잘못된 설정은 오류로 처리해야 한다. 별칭은 시스템 resolver의 공식 호스트 canonical name에서 얻은 유효한 cloudfront.net 하위 DNS 이름이어야 한다. 별칭 HTTPS URL과 TLS SNI를 사용하고 HTTP Host는 공식 호스트를 유지해야 한다. 인증서 검증을 켜고 리다이렉트를 거부하며 30초 timeout, 최대 3회 HTTP 시도와 실행 단위 회로 차단기를 유지해야 한다. 경로 자동 전환은 금지한다.

#### Scenario: 별칭 선택
- **WHEN** cloudfront_alias를 선택하고 유효한 별칭을 얻을 때
- **THEN** 별칭 인증서를 검증하고 공식 Host로 공개 검색을 요청한다

#### Scenario: 별칭 또는 TLS 실패
- **WHEN** 별칭이 없거나 허용되지 않거나 인증서 검증에 실패할 때
- **THEN** 공식 경로로 우회하지 않고 unavailable과 안전한 실패 분류를 기록한다

#### Scenario: 리다이렉트 응답
- **WHEN** 공개 검색이 3xx를 반환할 때
- **THEN** 리다이렉트를 따라가지 않고 조회 실패로 처리한다

### Requirement: 별칭 진단 구분
시스템 MUST doctor에서 공식 경로와 선택된 별칭 경로를 구분하고 HEAD 도달성과 검색 GET 성공을 구분해야 한다. 네트워크 정책은 선택한 별칭 목적지 또는 해결 실패를 표시해야 한다. 로그에는 검색어·응답 본문·인증정보를 남기지 않아야 한다.

#### Scenario: 별칭 경로 진단
- **WHEN** 별칭 연결이 선택된 상태에서 doctor를 실행할 때
- **THEN** 공식 경로 실패를 숨기지 않고 별칭 Host를 적용한 HEAD 결과를 별도로 표시하며 GET은 미검증이라고 알린다
