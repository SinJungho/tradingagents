## MODIFIED Requirements

### Requirement: 지수와 시장 폭

시스템 MUST S&P 500, Nasdaq Composite, Dow Jones, Russell 2000 및 VIX의 최신 확인 가능한 종가와 일간·주간·월간 변화를 제공해야 한다. 또한 상승·하락 종목 비율과 대형주·중소형주 참여도를 포함해야 하며, 산출할 수 없는 시장 내부 지표는 누락으로 명시해야 한다. S&P 500 시장 폭 표본은 검증된 SPDR SPY ETF 보유 종목을 우선 사용하고, 해당 자료의 보유 기준일과 `etf_holdings_proxy` 출처 종류를 보존해야 한다. 보고서는 SPY 보유 종목이 공식 S&P 500 지수 구성 목록이 아닌 대용치임을 라벨과 주석으로 밝혀야 한다. SPY 자료를 조회하거나 검증할 수 없으면 Wikipedia 현재 구성으로 대체하고, 그 경우 구성 기준일은 미확인으로 표시해야 한다.

#### Scenario: 지수 또는 시장 폭 자료 일부 누락

- **WHEN** 한 지수나 시장 폭 지표의 데이터가 제공되지 않거나 기준 시각이 다를 때
- **THEN** 보고서는 확인 가능한 다른 지표를 계속 제공하고 해당 값과 기준 시각을 누락 또는 불일치로 표시한다

#### Scenario: SPY 보유 종목으로 시장 폭을 산출

- **WHEN** SPY 보유 종목 XLSX가 유효하고 주식 티커 수가 허용 범위이며 보유 기준일을 읽을 수 있을 때
- **THEN** 시스템은 해당 보유 티커를 시장 폭 표본으로 사용하고 evidence에 기준일과 `etf_holdings_proxy`를 기록한다
- **AND** 보고서 라벨과 주석은 이를 공식 S&P 500 지수 구성이 아닌 SPY 보유 종목 대용치로 표시한다

#### Scenario: SPY 자료 실패로 Wikipedia 현재 구성 대체

- **WHEN** SPY 보유 종목을 가져오거나 파싱·검증할 수 없을 때
- **THEN** 시스템은 기존 Wikipedia 현재 구성 경로를 사용한다
- **AND** evidence와 Markdown은 구성 기준일을 미확인으로 표시한다
