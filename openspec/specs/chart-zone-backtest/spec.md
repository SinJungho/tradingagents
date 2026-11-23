# chart-zone-backtest Specification

## Purpose
고정 표본과 공개 시점을 적용한 보조 표본을 관리하고, 사전등록한 대조군과 표본 기준으로 일봉 가격 구간의 과거 성과를 평가한다.

## Requirements

### Requirement: 보유 종목 포함 및 우선 처리
시스템은 기본 48종목과 읽기 전용으로 확인한 토스 **미국 상장** 보유 ticker의 합집합을 고정 표본으로 관리하고 현재 보유 종목을 우선 처리해야 한다. 한국 상장 ticker는 XNYS v1 평가에서 제외한다. 추가분은 별도 코호트로 보고하고 보유 확인 이전을 과거 보유로 가정하지 않아야 한다. 계좌 원문과 식별자는 표본에 저장하지 않는다. 불변 sample hash는 같은 ticker/최초 확인 시각/우선순위 입력에 대해 재현돼야 하며 매 조회 시각은 별도 운영 포인터로 둔다. MUST.

#### Scenario: 기본 표본 밖 보유 종목
- **WHEN** 읽기 전용 조회에서 새로운 보유 ticker가 확인된다
- **THEN** 로컬 불변 표본 revision에 추가하고 보유 우선순위를 부여하며 기본 표본 통과 판정과 별도 집계한다.

#### Scenario: 중복 보유 및 매도
- **WHEN** 기본 표본과 보유 ticker가 겹치거나 기존 보유 ticker가 매도된다
- **THEN** 중복 계산하지 않으며 매도된 ticker는 표본에 남기고 현재 보유 우선순위만 해제한다.

#### Scenario: 보유 조회 실패
- **WHEN** 계좌 조회가 실패한다
- **THEN** 보유 없음으로 대체하지 않고 마지막 확인 시각과 우선순위 확인 불가를 표시한다.

#### Scenario: 미국 상장 종목만 포함
- **WHEN** Toss holdings에 미국과 한국 상장 종목이 함께 있다
- **THEN** 미국 ticker만 표본에 추가하고 한국 ticker는 집계에서 제외한다.

#### Scenario: 보유 확인 시각 누락
- **WHEN** 읽기 전용 어댑터가 `retrieved_at`을 반환하지 않는다
- **THEN** point-in-time 적격 날짜를 정할 수 없으므로 표본과 최신 포인터를 갱신하지 않는다.

### Requirement: 미래 정보 없는 가격 구간 평가
zone-backtest는 기준일에 생성 가능한 구간만 평가하고, 미래 첫 터치와 반응·실패 이벤트를 구분해야 한다. support/resistance는 일봉 내부 순서를 알 수 없으므로 첫 터치 봉은 touch rate에만 포함하고 다음 봉부터 성과를 판정한다. inside는 기준일에 이미 구간 안에 있으므로 이전의 최근 구간 밖 종가로 방향을 정하고 기준일을 activation으로 기록한 뒤 다음 세션부터 장벽을 판정한다. 성공·실패가 같은 봉에 발생하면 실패로 처리한다. XNYS 세션 결측은 건너뛰지 않고 data-unknown으로 분류한다. MUST.

#### Scenario: 첫 미래 터치
- **WHEN** 기준일 뒤 support의 저가가 상단에 처음 닿는다
- **THEN** 그 날짜는 터치로 기록하고 해당 봉은 성공·실패 판정에서 제외한다.

#### Scenario: 터치 뒤 양쪽 조건 충족
- **WHEN** 터치 다음 평가 봉에서 성공과 실패 가격이 모두 충족된다
- **THEN** 실패로 판정한다.

#### Scenario: 미터치와 미결
- **WHEN** 평가창 안에서 구간에 닿지 않거나 터치 후 결과가 없다
- **THEN** 각각 `not_touched`와 `touched_unresolved`로 별도 계수한다.

#### Scenario: inside 평가 시작
- **WHEN** 기준일 종가가 inside 구간 안에 있고 과거 구간 밖 종가로 방향을 정할 수 있다
- **THEN** 기준일을 activation으로 기록하고 기준일 다음 XNYS 세션부터 결과를 판정한다.

#### Scenario: 누락된 미래 세션
- **WHEN** 60개 평가 세션 중 Yahoo 행이 하나라도 누락된다
- **THEN** 누락 세션을 다음 행으로 대체하지 않고 해당 사건을 `unresolved_data`로 제외한다.

### Requirement: 공정한 대조군과 의존성 보정
평가는 random-unconditional 및 ticker·기준일·구간 유형·변동성 상태를 정확히 맞춘 matched baseline을 별도 산출해야 한다. support/resistance의 matched 폭 차이는 0.05 ATR 이하, `distance_atr` 차이는 0.25 ATR 이하로 제한한다. inside matched 구간은 실제 구간과 같은 폭으로 기준일 종가를 포함한다. random-unconditional은 실제 구간 중첩을 거부하지만 matched는 중첩을 허용하고 겹침 수를 보고한다. 1,000회 이내에 200개 대조군을 만들지 못하면 해당 실제 구간을 `unmatched`로 분리한다. 결과는 conditional hit rate, eligible zones 대비 유효 적중률, touch rate를 구분하고 종목 군집과 시간 block 3/6/12 의존성을 반영해야 한다. MUST.

#### Scenario: 공통 매칭 후보 부족
- **WHEN** 사전 고정된 matched 기준을 만족하는 대조군을 생성할 수 없다
- **THEN** 해당 사건을 unmatched로 기록하고 효능 추정에 임의 대체하지 않는다.

#### Scenario: 시간·종목 의존성
- **WHEN** 신뢰구간을 계산한다
- **THEN** 짝지은 사건을 유지하고 종목/날짜 군집을 반영하며 block 3/6/12 민감도와 유효 표본 수를 보고한다.

#### Scenario: matched 구간이 실제 구간과 겹침
- **WHEN** 폭·거리를 맞춘 matched baseline 후보가 실제 구간과 겹친다
- **THEN** 해당 후보를 제거하지 않고 결과에 겹침 수를 남긴다.

### Requirement: 표본 충분도와 통과 상태
주 통과 판정은 primary fixed cohort의 matched baseline 대비 effective hit lift를 사용해야 한다. 유형별 bootstrap lower 95% bound가 0보다 크고 support/resistance의 low/high ATR tercile point lift가 모두 0보다 커야 한다. inside는 별도 endpoint로 lower bound>0을 요구한다. 두 directional endpoint에는 one-sided α=0.025를 적용해 family-wise 오류 상한을 0.05로 둔다. 최소 10개 ticker, 50개 기준일, 100개 distinct touch episode 및 block별 완전 시간 block 6개가 없으면 해당 판정은 `inconclusive`다. MUST.

#### Scenario: 현재 검증 기간이 최소 기준일 수 미달
- **WHEN** 검증 기간에 50개 distinct 기준일이 아직 없다
- **THEN** 평가 상태는 `inconclusive`이며 기준일 간격을 임의로 줄이지 않는다.

#### Scenario: 최신 평가는 실패 또는 미결
- **WHEN** 최신 평가가 `failed`, `inconclusive`, `not_evaluated`다
- **THEN** 과거 통과 기록은 `last_passed_evaluation` 이력으로만 보존하고 `effective_status`로 쓰지 않는다.

### Requirement: 검증 표본 격리
파라미터 선택은 튜닝 기간에서만 가능하고 검증 기간의 열람 이후 설정 변경은 새 버전·새 holdout이 없으면 금지해야 한다. 고정 48종목과 13F 코호트, 레버리지 ETF는 주 통과 판정에서 섞지 않는다. MUST.

#### Scenario: 검증 자료에서 파라미터 조정
- **WHEN** 검증 결과를 본 뒤 수치/threshold를 바꾸려 한다
- **THEN** 기존 validation 결과는 무효화하고 새 버전과 미사용 검증 기간을 요구한다.

#### Scenario: 최신 평가 실패
- **WHEN** 최신 evaluation이 failed 또는 inconclusive다
- **THEN** 이전 passed 기록은 이력으로 보존하되 현재 효과 상태는 passed가 아니다.

### Requirement: 백테스트 이력 적격성
고정 표본의 각 ticker는 첫 유효 행부터 마지막 유효 행까지 XNYS 예정 세션의 결측·잘못된 OHLC 비율이 1% 이하여야 한다. 연속 XNYS 종가 변화가 절댓값 50% 이상이고 Yahoo `Stock Splits` 요인이 가격 변화를 ±20% 로그 허용 안에서 설명하지 못하면 해당 ticker 이력을 평가에서 제외해야 한다. IONQ의 2021-10-01 이전 행은 제외해야 한다. 표본 ticker 목록은 유지하고 평가 기록에 제외 이유와 측정값을 보존해야 한다. MUST.

#### Scenario: 결측 또는 설명되지 않은 가격 단절
- **WHEN** ticker의 결측 봉 비율이 1%를 넘거나 분할로 설명되지 않는 50% 이상 하루 단절이 있다
- **THEN** 그 ticker 이력을 평가 입력에서 제외하고 평가 기록에는 ticker 및 제외 이유를 남긴다.

#### Scenario: IONQ 합병 전 이력
- **WHEN** Yahoo history에 2021-10-01 이전 IONQ 봉이 포함된다
- **THEN** 해당 행을 snapshot hash와 계산에서 제외하고 제외 행 수를 품질 기록에 남긴다.

### Requirement: SEC 13F prospective-only sample
SEC quarterly dataset으로 별도 `sec_13f` 코호트를 만들 수 있어야 한다. `report_period`는 공개시각으로 쓰지 않는다. accepted timestamp가 없으면 dataset과 mapping 관측(및 확인 가능한 accepted timestamp) 이후 첫 XNYS session부터 편입하고 과거 기준일로 소급하지 않는다. 13F 코호트는 fixed/Toss와 별도 집계하며 primary 통계 통과 판정에 합치지 않는다. MUST.

#### Scenario: SEC filing은 관측 이후부터만 편입
- **WHEN** filing의 report period가 ZIP observation보다 오래됐지만 ZIP이 새로 관측된다
- **THEN** 해당 종목의 eligible date는 `max(dataset_downloaded_at, mapping_observed_at, accepted_at_if_available)` 다음 XNYS session으로 정하고 과거 기준일에 소급 편입하지 않는다.

#### Scenario: latest report와 amendment 전이
- **WHEN** 같은 CIK/report period에 initial report, restatement, new-holdings-entry amendment가 함께 있다
- **THEN** restatement는 해당 filer의 이전 holdings를 대체하고 new-holdings-entry amendment는 기존 holdings에 추가하며, amendment type을 확정할 수 없으면 그 filer를 ambiguous로 제외한다.

### Requirement: 13F 보통주 매핑과 단위
CUSIP은 `exchCode=US` OpenFIGI 결과가 정확히 하나이고 FIGI/ticker, `marketSector=Equity`, `securityType=Common Stock`을 갖춘 경우만 자동 연결한다. 원금·옵션·fund/ETF와 모호한 mapping은 별도 제외 사유로 남긴다. SEC `VALUE`와 share/principal amount 단위를 혼합하지 않는다. MUST.

#### Scenario: value와 share 단위
- **WHEN** SEC information table에 `VALUE`, `SSHPRNAMT`, `SSHPRNAMTTYPE`가 함께 있다
- **THEN** `VALUE`는 SEC가 정의한 $1,000 단위에서 USD로 정규화하고 `SH`와 `PRN` amount는 합산하지 않으며 `PRN`과 `PUTCALL` 행은 ticker 후보에서 제외한다.

#### Scenario: mapping 충돌과 보통주 분류
- **WHEN** 한 CUSIP이 여러 ticker/FIGI 후보를 반환하거나 instrument type이 보통주가 아니다
- **THEN** 자동 표본에 편입하지 않고 `ambiguous` 또는 `ambiguous_security_type`으로 기록한다.

#### Scenario: SEC refresh는 시장/언어 모델과 독립
- **WHEN** `zone-sample refresh --source sec`를 실행한다
- **THEN** SEC ZIP/submissions와 OpenFIGI만 조회하고 Yahoo 가격, Toss 계좌, LLM에는 접근하지 않는다.
