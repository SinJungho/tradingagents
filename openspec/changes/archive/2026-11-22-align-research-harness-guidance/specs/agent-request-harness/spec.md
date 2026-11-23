## MODIFIED Requirements

### Requirement: 요청 유형 분류

저장소 에이전트 MUST 요청한 결과로 리서치 유형을 선택하고 같은 유형에는 같은 기본 경로를 적용해야 한다. 미국장 마감·장후는 `market-report`, 종목 종합 분석과 매매 판단은 `stock-scenario`, 팩터 비교·발굴은 `stock-discovery`, 보유 조회·점검은 `portfolio-check`, 차트·기술적 분석과 검증·드로잉은 `tratto-chart`, 백테스트는 `backtest-eval`, 13F·하원 공시는 `portfolio-disclosures`를 적용해야 한다.

#### Scenario: 미국장 마감·장후 보고서

- **WHEN** 사용자가 미국장 마감·장후 정리를 요청할 때
- **THEN** 에이전트는 동부시간 20시 기준 직전 완료 거래일을 확인하고 `tradingagents market-report`를 실행한다
- **AND** 자료 전용 요청과 개발 검증에는 `--no-llm`을 사용한다

#### Scenario: 종목이 지정된 요청

- **WHEN** 사용자가 종목 종합 분석을 요청할 때
- **THEN** 에이전트는 종목과 기준일을 확인하고 `tradingagents --ticker <T> --date <D>` 경로를 사용한다
- **AND** 종합 분석에 포함한 기술적 분석에는 기존 Market Analyst 도구를 사용한다

#### Scenario: 실계좌를 허용한 종목 시나리오

- **WHEN** 사용자가 매수·보유·매도 또는 비중 판단을 요청할 때
- **THEN** 보유 JSON이 지정되지 않았으면 에이전트는 사전 허용된 `tradingagents portfolio live --symbol <T>`의 기본 요약을 사용하고 명시적 심층 요청에만 `--full-workflow`를 사용한다

#### Scenario: 보유 JSON을 제공한 종목 시나리오

- **WHEN** 사용자가 보유 JSON 파일을 지정하고 종목 판단을 요청할 때
- **THEN** 에이전트는 `tradingagents --ticker <T> --date <D> --portfolio <file.json>`로 해당 보유 정보를 반영한다

#### Scenario: 티커 목록을 제공한 결정론적 종목 발굴

- **WHEN** 사용자가 지정 종목의 팩터 비교나 후보 발굴을 요청할 때
- **THEN** 에이전트는 `discover --tickers`를 실행해 결정론적 팩터 신호를 보고한다
- **AND** 후속 종목 분석은 사용자가 선택한 후보에만 적용한다

#### Scenario: 심층 분석을 지정하지 않은 포트폴리오 점검

- **WHEN** 사용자가 일반 포트폴리오 점검을 요청할 때
- **THEN** 에이전트는 `portfolio live`를 사용하고 명시적 심층 점검에만 `--full-workflow`를 사용한다

#### Scenario: 보유 조회 전용

- **WHEN** 사용자가 보유 현황만 요청할 때
- **THEN** 에이전트는 `portfolio live --no-scenarios`로 LLM 없이 읽기 전용 조회를 하고 자료 기준 시각을 확인한다

#### Scenario: 백테스트

- **WHEN** 사용자가 그래프 판단, 팩터 신호, 차트 가격 구간의 과거 성과를 검증할 때
- **THEN** 에이전트는 평가 대상에 따라 `backtest`, `style-backtest`, `zone-backtest run --period validate`를 사용한다

#### Scenario: 13F 및 하원 공시

- **WHEN** 사용자가 13F 기관 보유 또는 미국 하원 주식 보유·거래 공시를 요청할 때
- **THEN** 에이전트는 `portfolio-disclosures` 절차로 공식 공시를 조회한다

#### Scenario: 출처와 실행 지원

- **WHEN** 새 데이터 출처 채택, 반복적인 API·인증 실패, 외부 프로젝트 비교가 필요한 경우
- **THEN** 에이전트는 각각 `data-source-check`, `api-doctor`, `reference-research`를 적용한다

### Requirement: 미구현 기능 처리

저장소 에이전트 MUST 현재 CLI에 없는 기능을 실행된 것처럼 보고해서는 안 된다. 결정론적 종목 발굴은 지정 종목의 `discover --tickers` 또는 시장 구간의 `discover --universe`를 사용한다. 팩터별 신호와 출처·실패 범위를 보고하고 후속 종목 분석은 사용자가 선택한 후보에만 적용한다. 새 기능 구현은 OpenSpec 변경으로 시작해야 한다.

#### Scenario: 시장 전체 발굴 지원

- **WHEN** 사용자가 시장 전체에서 후보 발굴을 요청할 때
- **THEN** 에이전트는 `tradingagents discover --universe all`을 실행한다

#### Scenario: 지정 티커 발굴 지원

- **WHEN** 사용자가 발굴할 티커 목록을 제공할 때
- **THEN** 에이전트는 기존 팩터 계산을 사용하는 `tradingagents discover --tickers <T1,T2>`를 실행한다

#### Scenario: 종목 발굴 명령 부재

- **WHEN** 사용자가 현재 CLI에 없는 발굴 명령이나 옵션을 요청할 때
- **THEN** 에이전트는 실행 여부와 실제로 지원되는 범위를 보고하며 새 동작은 OpenSpec 변경으로 진행한다

#### Scenario: Russell 2000 구간 출처 실패

- **WHEN** Russell 2000 구간의 공개 보유 종목 출처가 CSV를 제공하지 않을 때
- **THEN** 에이전트는 구간 실패 원인을 전하고 `sp600`·`smallcap` 등 지원되는 다른 구간을 안내한다

## ADDED Requirements

### Requirement: 차트 분석 경로와 근거

저장소 에이전트 MUST 종목·봉 주기·기준 거래일·가격 조정 기준을 확인하고 가격 구조·추세·거래량에서 분석을 시작해야 한다. 요청에 필요한 보조지표만 사용하고 가격 경계와 추세선 앵커는 검증된 데이터에서 계산해야 한다. 현재 가격이 구간 안에 있으면 상단과 하단의 이탈 조건을 각각 설명해야 한다.

#### Scenario: 분석만 요청된 미국 일봉 가격 구간

- **WHEN** 사용자가 미국 종목의 일봉 가격 구조나 지지·저항 분석을 요청할 때
- **THEN** 에이전트는 `chart-zones --tickers <T> --json`으로 시작하고 검증된 계산 근거와 조건을 보고한다
- **AND** 분석만 요청했다면 드로잉을 변경하지 않는다

#### Scenario: 5년 일봉과 추세선

- **WHEN** 사용자가 5년 일봉 또는 장기·최근 추세선을 요청할 때
- **THEN** 에이전트는 `tratto-chart`의 거래일·OHLCV 검증과 전후 5봉 피벗 절차를 적용한다

### Requirement: 차트 검증 및 변경 범위

저장소 에이전트 MUST 가격 구간을 차트와 대조할 때 `chart-check`를 사용해야 한다. 표시 요청은 실제 대상 탭의 종목·주기·기존 객체를 확인한 뒤 해당 분석 경로에서 검증한 좌표를 사용해야 한다. 같은 좌표의 객체는 재사용하고 삭제는 사용자가 명시한 대상에만 적용해야 한다.

#### Scenario: 차트 대조만 요청

- **WHEN** 사용자가 차트 가격 구간의 대조만 요청할 때
- **THEN** 에이전트는 `chart-check`의 대조 결과를 보고하고 드로잉을 변경하지 않는다

#### Scenario: 검증 후 표시 요청

- **WHEN** 사용자가 검증과 표시를 요청할 때
- **THEN** 에이전트는 `chart-zones` 구간은 `chart-check` 결과가 `ok`일 때, 5년 일봉 결과는 거래일·OHLCV 검증을 통과했을 때 표시한다

#### Scenario: CSV 가격 불일치

- **WHEN** 스킬의 재조회 후에도 `chart-check`가 `mismatch`를 반환할 때
- **THEN** 에이전트는 불일치를 보고하고 드로잉을 추가하지 않는다

#### Scenario: 동일 좌표 재요청

- **WHEN** 사용자 탭에 요청한 종류와 날짜·가격 좌표의 객체가 이미 있을 때
- **THEN** 에이전트는 기존 객체를 재사용하고 중복 생성을 피한다

### Requirement: 차트 완료 증거

저장소 에이전트 MUST 변경 전후 `read_drawings`의 날짜·가격을 비교하고, 실제 사용자 탭을 다시 열어 표시가 유지되는지 확인해야 한다. 차트 캡처와 `drawings.json`에 근거를 남겨야 한다. 연결·좌표·화면 중 필수 증거가 빠지면 확인된 단계까지만 보고해야 한다. 차트 데이터 일치, 드로잉 확인, 통계적 예측력은 각각의 결과로 보고해야 한다.

#### Scenario: 재열기 후 표시 누락

- **WHEN** 변경 직후 좌표가 일치했지만 실제 사용자 탭을 다시 열자 표시가 누락될 때
- **THEN** 에이전트는 드로잉을 미완료로 보고하고 확인된 좌표 대조와 재열기 실패를 기록한다

#### Scenario: 차트 일치와 백테스트 미결

- **WHEN** 차트 데이터는 일치하지만 가격 구간 백테스트 결과가 미결일 때
- **THEN** 에이전트는 차트 일치와 별도로 드로잉 확인 결과 및 통계적 예측력 미확인을 기록한다

### Requirement: 리서치 답변 품질

저장소 에이전트 MUST 미국장 판단, 핵심 근거 2~3개와 판단 변경 조건을 먼저 제시하고 상세 근거는 기존 보고서에 연결해야 한다. 골드만삭스 자료와 판교불패 영상은 당일 쟁점에 관련될 때에만 원자료와 대조해야 한다.

#### Scenario: 시장 폭 누락

- **WHEN** 시장 폭이 미확인일 때
- **THEN** 에이전트는 상승이 확산됐다는 판단을 유보하고 근거가 확인된 범위를 보고한다

#### Scenario: 보유 수량 또는 평가액 누락

- **WHEN** 보유 수량이나 평가액이 미확인일 때
- **THEN** 에이전트는 비중 조정 수치를 유보하고 미확인 항목을 표시한다
