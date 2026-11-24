## ADDED Requirements

### Requirement: 공개 시장 스트레스 지표 출처

시스템 MUST 시장·거시 리서치에서 VIX/VIX3M 비율과 ICE BofA 하이일드 OAS를 거래일마다 출처·관측일과 함께 제공하고, BofA·Goldman 독점 지표와 Zweig Breadth Thrust는 검증된 원자료 또는 출처가 확인되는 공개 인용이 없으면 미확인으로 표시해야 한다.

#### Scenario: VIX 기간구조의 역전과 해소

- **WHEN** Cboe VIX와 VIX3M의 공통 거래일 종가가 확인된다
- **THEN** 시스템은 VIX/VIX3M 비율, 공통 관측일, 1.0 초과 여부와 전일 대비 역전·해소 전환을 표시한다
- **AND** 종목 기준 시각이 정규장 종가보다 이르면 당일 종가를 사용하지 않는다

#### Scenario: 일별 하이일드 신용 관측

- **WHEN** 시장 보고서 또는 미국 종목의 공통 시장 리서치를 생성한다
- **THEN** 시스템은 FRED가 인용하는 ICE BofA US High Yield OAS의 마지막 검증 가능 빈티지를 조회하고 관측일·조회 상태를 표시한다
- **AND** 원수치 접근이 제한되면 값은 마스킹하고 신용 스트레스 확인 여부와 제한 사유만 제공한다

#### Scenario: 공개 시각을 확인할 수 없는 일별 지수 파일

- **WHEN** Cboe 일별 이력에는 관측일이 있으나 공개 시각이 없다
- **THEN** 시스템은 관측일을 보존하고 게시 시각 미확인을 표시하며 당일 값이 사용 가능한지 기준 시각에 따라 제한한다

#### Scenario: BofA 또는 Goldman 독점 지표가 공개 보도로만 확인됨

- **WHEN** BofA 또는 Goldman 지표의 수치가 공개 기사에 인용되고 원자료에 접근할 수 없다
- **THEN** 시스템은 해당 매체, 기사 URL, 게시 시각, 인용된 기준 시점을 표시하고 이를 2차 출처로 분류한다
- **AND** 원자료 미확인과 인용 수치의 시점 차이를 함께 밝힌다

#### Scenario: 독점 지표의 공개 인용을 확인하지 못함

- **WHEN** BofA·Goldman 값이 공개 출처에서 확인되지 않거나 기준 시점을 판별할 수 없다
- **THEN** 시스템은 대체 점수를 추정하지 않고 미확인으로 표시한다

#### Scenario: Zweig Breadth Thrust 입력 자료 부재

- **WHEN** 산출에 필요한 NYSE 상승·하락 종목 원자료와 평균 방식이 검증되지 않는다
- **THEN** 시스템은 SPY 보유 종목이나 별도 대용 시장 폭을 이용해 Zweig Breadth Thrust를 산출하지 않는다

#### Scenario: CNN Fear & Greed 인용

- **WHEN** CNN Fear & Greed를 보조 지표로 사용한다
- **THEN** 시스템은 CNN 원문, 조회 기준 시각, 지수값을 기록하고 구성요소인 정크본드 수요를 ICE BofA OAS와 같은 수치로 취급하지 않는다
