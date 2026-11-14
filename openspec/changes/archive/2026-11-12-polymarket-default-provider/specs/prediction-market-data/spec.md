## MODIFIED Requirements

### Requirement: Kalshi 공개 자료 조회

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
