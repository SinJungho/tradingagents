# chart-zone-analysis Specification

## Purpose
미국 종목의 일봉 가격 구간을 재현 가능하게 계산하고 Tratto 차트의 원본 봉 및 드로잉 좌표와 대조하는 기준을 정의한다.

## Requirements

### Requirement: 결정론적 일봉 가격 구간
시스템은 Yahoo Finance 일봉의 고정 스냅샷 prefix와 XNYS `as_of` 세션을 사용해 v1 가격 구간을 계산해야 한다. 계산은 고정된 Wilder ATR, 확정 ZigZag 피벗, 50% KDE 확률질량 HDR, 폭 상한과 안정 동점 규칙을 사용하며, 미래 미확정 피벗과 `as_of` 이후 봉을 포함하지 않는다. MUST.

#### Scenario: 같은 스냅샷 재계산
- **WHEN** 같은 Yahoo 일봉 스냅샷과 같은 `as_of`·params 버전으로 다시 계산한다
- **THEN** 정규화된 결과 bytes와 snapshot SHA-256이 동일하다.

#### Scenario: 미래 자료 추가
- **WHEN** `as_of` 뒤 봉만 바꾼다
- **THEN** `as_of`까지 확정된 피벗·구간·점수·추세 결과는 변하지 않는다.

#### Scenario: 당일 미확정 피벗
- **WHEN** 반전 임계값이 `as_of` 이후 처음 충족된다
- **THEN** 그 꼭짓점은 `as_of` 결과의 터치나 구간 계산에 들어가지 않는다.

#### Scenario: 불완전 이력
- **WHEN** 완전한 유효 봉이 504개 미만이거나 입력 자료가 결측이다
- **THEN** 결측은 채우지 않고 `unknowns`와 `insufficient`를 출력한다.

### Requirement: 피보나치 되돌림 앵커
시스템은 `as_of`까지 확정된 마지막 두 ZigZag 피벗을 피보나치 되돌림의 시작·끝 앵커로 출력해야 한다. 앵커 가격은 해당 봉의 원래 고가·저가이고, 0.236·0.382·0.5·0.618·0.786 되돌림 가격과 앵커 주변 확인 window를 함께 출력한다. 모델이나 Tratto는 앵커를 고르거나 고치지 않는다. MUST.

#### Scenario: 마지막 스윙 유지
- **WHEN** 끝 앵커 뒤 봉이 끝 앵커 가격과 시작 앵커 가격을 넘지 않는다
- **THEN** `fib_retracement.status`는 `ok`이고 `check_windows`에 `fib_start`·`fib_end`가 들어간다.

#### Scenario: 스윙 무효
- **WHEN** 끝 앵커 뒤 봉이 끝 앵커 극값을 갱신하거나 시작 앵커 가격을 넘는다
- **THEN** 상태는 `invalidated`이고 `new_extreme_after_end` 또는 `start_breached` 이유를 남긴다.

#### Scenario: 앵커 부족
- **WHEN** 확정 피벗이 두 개 미만이거나 마지막 스윙이 세션 결측을 가로지른다
- **THEN** 상태는 `unavailable`이고 피보나치 확인 window를 만들지 않는다.

### Requirement: Anchored VWAP 앵커와 값
시스템은 마지막 피보나치 스윙 시작 봉과 `as_of` 이전 가장 최근 Yahoo 실적 발표의 첫 거래 세션을 앵커로 일봉 Anchored VWAP을 계산해야 한다. 값은 앵커 봉부터 `as_of`까지 (고가+저가+종가)/3을 거래량으로 가중 평균하고, 날짜별 값·마지막 값·종가와의 ATR 거리를 출력한다. 장 마감(16:00 ET) 이후 발표는 다음 XNYS 세션을 앵커로 쓰고, 발표 시각이 없으면 날짜를 쓰며 `release_time_known=false`를 남긴다. 모델은 앵커나 값을 계산하지 않는다. MUST.

#### Scenario: 실적 발표 앵커
- **WHEN** `as_of` 이전 실적 발표 시각이 장 마감 이후다
- **THEN** 다음 XNYS 세션이 `anchor_date`이고 `check_windows.avwap_earnings`가 그 날짜를 포함한다.

#### Scenario: 미래 실적 일정 제외
- **WHEN** 실적 일정이 `as_of` 이후 세션에 해당한다
- **THEN** 그 일정은 앵커로 쓰지 않는다.

#### Scenario: 자료 부족
- **WHEN** 실적 일정을 가져오지 못했거나 앵커 이후 거래량 결측·세션 결측이 있다
- **THEN** 해당 VWAP은 `unavailable`과 이유를 출력하고 값을 만들지 않는다.

#### Scenario: LLM 입력 축소
- **WHEN** Market Analyst가 `get_chart_zones`를 호출한다
- **THEN** 날짜별 VWAP 값 목록은 제외하고 마지막 값과 거리만 전달한다.

### Requirement: 증거 기반 종목 분석 도구
Market Analyst는 날짜 고정 `get_chart_zones` 도구를 사용할 수 있어야 하고, 계산된 날짜·가격 근거를 기존 도구 증거 수집 경로에 전달해야 한다. 분석 도구는 계산 결과를 재계산하거나 LLM이 선택한 값을 반환하지 않는다. MUST.

#### Scenario: 단일 종목 분석
- **WHEN** Market Analyst가 요청 종목을 분석한다
- **THEN** `trade_date` 이하 최신 완료 XNYS 세션의 결정론적 결과를 해석하며 종가 basis와 unknowns를 보고한다.

#### Scenario: inside 구간 해석
- **WHEN** 종가가 구간 내부에 있다
- **THEN** inside를 지지/저항 어느 쪽으로도 단정하지 않고 상·하단 이탈 조건을 함께 보고한다.

### Requirement: 다종목 CLI
`tradingagents chart-zones --tickers <T1,...> [--date D] [--json] [--output-dir]`는 최대 10개 ticker를 독립 처리하고 LLM을 호출하지 않아야 한다. 결과는 ticker·as_of·스냅샷 해시로 구분해 저장한다. MUST.

#### Scenario: 목록 중 일부 실패
- **WHEN** 하나의 ticker에서 Yahoo 자료 조회나 계산이 실패한다
- **THEN** 실패 ticker의 오류와 source failure를 기록하고 나머지 ticker 결과를 계속 만든다.

#### Scenario: 주봉 요청
- **WHEN** 사용자가 주봉 계산을 요청한다
- **THEN** 주봉은 미지원이라고 알리고 일봉 결과로 대체하지 않는다.

### Requirement: 차트 내보내기 시간대
`chart-check`는 IANA 시간대로 차트 CSV의 오프셋이 있는 타임스탬프를 거래일로 해석해야 한다. 기본은 America/New_York이며 원본 CSV는 그대로 보존한다. MUST.

#### Scenario: 서울 시간대 일봉 내보내기
- **WHEN** 서울 현지 자정으로 직렬화된 일봉과 함께 `--chart-timezone Asia/Seoul`을 넘긴다
- **THEN** 서울 현지 날짜로 비교하고 결과에 적용 시간대를 남긴다.

### Requirement: 요청별 Tratto 분석 범위
Tratto Skill은 요청된 5년 일봉의 거래일·봉 수를 검증하고 Python의 전후 5봉 피벗으로 가격 구간과 장기·최근 추세선을 선정해야 한다. 보조 도구는 목적에 따라 선택하고, 실제 브라우저 표시와 앵커를 모두 확인해야 한다. MUST.

#### Scenario: 장기 구간 설정에서 주봉 전환
- **WHEN** 5년 범위를 한 번에 설정해 일봉 전체를 확인할 수 없다
- **THEN** 연도별 일봉을 내보내고 중복과 누락을 확인한 뒤 Python 분석을 수행한다.

#### Scenario: 간소화와 전체 검토
- **WHEN** 사용자가 간소화 표시 또는 보조 도구 전체 검토를 요청한다
- **THEN** 간소화는 필요한 항목만 표시하고 전체 요청은 12개 각 항목의 분석 및 표시 결과를 기록한다.

### Requirement: 분리된 검증 상태
시스템은 chart-check 자료 일치와 zone-backtest 통계 상태를 별도 필드로 출력해야 한다. 최신 평가가 `failed`, `inconclusive`, `not_evaluated`라면 과거 passed를 `effective_status`로 유지하지 않는다. MUST.

#### Scenario: 과거 통과 뒤 최신 실패
- **WHEN** append-only 평가 기록의 직전 결과가 passed이고 최신 결과가 failed다
- **THEN** `last_passed_evaluation`에는 과거 기록을 남기되 `latest_evaluation.status` 및 `effective_status`는 failed다.

#### Scenario: 표본 갱신
- **WHEN** 새 표본이 들어오고 재평가는 아직 없다
- **THEN** `pending=true`가 되고 refresh는 평가 결과를 바꾸지 않는다.

#### Scenario: 평가가 오래됨
- **WHEN** 평가 표본보다 최신 완료 분기가 2개 이상 지났다
- **THEN** `stale=true`이며 과거 passed는 effective 통과로 표시되지 않는다.

#### Scenario: 차트 데이터 일치만 통과
- **WHEN** Tratto chart-check가 `ok`이나 통계 평가 상태는 미검증이다
- **THEN** chart validation만 ok로 보고하고 통계 검증은 미검증 문구를 유지한다.
