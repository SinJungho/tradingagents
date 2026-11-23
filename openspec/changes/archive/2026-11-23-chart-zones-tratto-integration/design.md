# 설계 및 검토 결정

## 범위와 단계 경계

이 변경은 2026-11-18 제거 결정을 보완하는 신규 기능이다. 해당 아카이브의 과거 요구사항과 삭제 내역을 수정하지 않는다. 1단계는 가격 스냅샷·구간·CLI만, 2단계는 Tratto 상호운용성, 3단계는 고정 표본 평가, 4단계는 13F 공개 시점 표본 확장만 다룬다. 각 단계의 앞 단계 수용 기준과 데이터 출처 게이트를 통과하기 전에는 다음 단계에 착수하지 않는다.

## 데이터 계약과 날짜

- 입력은 XNYS 거래일 기준 일봉 OHLCV다. 현재 분석의 `as_of`는 기존 시장 보고서의 ET 20:00 완료 거래일 규칙을 재사용하고, 과거 날짜는 그 날짜 이하 마지막 XNYS 세션으로 정한다. 선택 세션 종가가 확정되지 않았으면 직전 완료 세션을 쓴다. 이후 행은 계산·해시·체크 윈도에서 제외한다.
- 구간 계산용 `history(auto_adjust=False)` 응답을 그대로 보존한다. `auto_adjust=False`는 배당 조정 가격은 아니지만 Yahoo가 과거 split basis를 소급 수정할 수 있다. 행동 열을 저장하고 공급자 응답의 split basis와 거래량 basis를 검증해 manifest에 명시한다. 애플리케이션에서 split 보정을 다시 적용해 이중 조정하지 않는다. 차트의 split basis가 다르면 `chart-check`에서 일치 실패로 취급한다. 배당락 가격 하락은 dividend-adjusted 가격과 혼합하지 않는다.
- 스냅샷 CSV에는 날짜, Open/High/Low/Close/Volume 및 확인된 기업행동 필드를 저장하고 SHA-256을 계산한다. 무결성 해시는 같은 바이트 입력을 식별할 뿐 Yahoo의 과거 자료 수정 가능성을 제거하지 않는다. CSV 원문을 분석 입력에 쓸 때 보간하거나 ffill/bfill하지 않는다. 결측 XNYS 세션은 예정 세션 달력과 비교해 `unknowns`에 날짜·필드·원인을 기록한다.
- ATR은 명시한 Wilder 재귀식과 초기 seed(첫 14개 유효 true range의 산술평균)를 사용한다. 유효한 OHLC가 없는 세션은 계산에서 채우지 않고 연속 구간을 끊는다. 최소 504개의 완전한 유효 세션 미만이면 `insufficient`다. 5년보다 짧은 상장 이력은 수집 가능한 범위만 쓰며 최소 요건은 면제하지 않는다.
- Yahoo 요청은 현재의 `yf_retry`를 재사용하되 차트용 공급자 함수는 no-fill/raw-bar 모드를 둔다. 기존 `route_to_vendor` 카테고리 테이블에 없는 메서드를 임의로 호출하지 않는다. 새 어댑터 오류는 `record_source_failure`에 등록해 CLI 결과에서 공급자 실패와 티커별 무자료를 구분한다.

## 구간 계산 v1 계약

### 고정 파라미터

일봉 5년(최대), Wilder ATR 14, ZigZag 반전 2.0×해당 세션 ATR, KDE 밴드 폭 0.5×피벗 ATR%, 로그 격자 0.05×수집 구간 ATR% 중앙값, 50% 확률질량 영역, 최대 구간 폭 1.0×해당 피벗 집합 ATR% 중앙값, 최소 확정 피벗 2개, 반응 관찰 20 유효 세션(상한 5×피벗 ATR), 점수 최근성 반감기 189 유효 세션, 침투 기준 0.5×해당 시점 ATR, 추세 회귀 전체 이력과 최근 252 유효 세션, 횡보 R²<0.3, 현재 종가 위·아래 각 최대 3개다. 연간 회귀 환산은 252 세션이다. 모든 중간 계산은 float64, 출력은 6자리 반올림이며 가격은 표시에만 통화 자릿수를 적용한다.

### ZigZag와 미래 누출

- 고가/저가를 번갈아 추적하는 확정형 ZigZag를 사용한다. 후보 꼭짓점은 반대 방향으로 해당 꼭짓점 ATR의 2배 이상 움직임이 관측된 첫 세션에서만 확정한다. 꼭짓점 가격은 극값 봉, `confirmed_at`은 반전 임계값이 처음 충족된 세션으로 기록한다.
- `confirmed_at <= as_of`인 피벗만 사용한다. 끝에 열린 꼭짓점, `as_of` 다음 봉에서야 확정될 피벗은 제외한다. 추후 자료가 추가되어도 과거 `as_of` 결과는 그 날 이용 가능했던 입력 prefix로 재계산했을 때 동일해야 한다.
- 같은 고가/저가의 동점은 가장 이른 세션, 같은 세션 고가·저가가 순서를 결정할 수 없는 경우 현재 추세의 반전 확인으로만 처리하고 봉 내부 경로를 추정하지 않는다. 초기 방향은 최초 두 배 ATR 반전이 확인된 방향으로 정해 초기 임의 선택을 없앤다.

### KDE 영역과 후보 선정

- 피벗 가격을 `x_i=ln(price_i)`로 변환한다. 각 가우시안 커널 표준편차는 `0.5×ATR_i/price_i`; 가중치는 `0.5^(경과 유효 세션/189)`다. 로그 격자 폭은 `0.05×수집 구간 ATR% 중앙값`이며 격자 범위는 가장자리 커널에서 6 표준편차까지 포함한다. 커널과 질량 합산은 float64로 수행하고 총 격자 질량으로 50% 기준을 정한다.
- 50% 밀도 영역은 밀도 내림차순 격자 누적 질량이 처음 0.5 이상이 되는 셀의 밀도를 threshold로 삼고, 그 threshold 이상인 모든 셀의 상위집합으로 정의한다. threshold 동점 셀은 모두 포함한다. 각 셀의 로그 가격과 동점 해소는 낮은 가격 우선이며, 연결 성분은 가격 오름차순으로 처리한다. 격자 셀 경계가 아닌 셀 중심을 후보 경계로 사용한다.
- 각 연결 성분의 봉우리는 최대 KDE 셀로 정하고 동점이면 낮은 로그 가격을 택한다. 그 성분 내 50% 질량 구간을 기본 경계로 삼는다. 구간 폭 상한은 해당 성분 피벗들의 ATR% 중앙값으로 한 번 계산한다. 폭 초과 시 봉우리 중심으로 자른 범위와 기본 경계의 교집합을 사용한다.
- 후보 성분이 겹치면 인접 봉우리 사이 최소 KDE 셀을 경계로 나누며, 최소점 동점은 낮은 로그 가격을 택한다. 모든 후보를 이 경계로 자른 후 전체 확정 피벗을 다시 배정하고 0폭/유효 피벗 수 부족 후보를 제거한다. 터치 피벗은 양 경계 포함으로 배정하고, 동등 경계 피벗은 낮은 가격 구간에 한 번만 배정한다.
- 후보 전체의 상호 배타적 분류는 `close` 기준으로 `inside`, `support`(구간 전체가 종가 아래), `resistance`(구간 전체가 종가 위)다. inside는 최소 하나만 남기며, 같은 close 포함 구간은 score 내림차순, 폭 오름차순, lower, upper 오름차순으로 하나를 택한다. support는 가까운 경계 거리 오름차순 후 score 내림차순으로 3개, resistance는 대칭으로 3개다. inside가 있으면 별도 출력하며 위/아래 3개 한도에 포함하지 않는다. 결과 순서는 inside, support 거리순, resistance 거리순으로 안정화한다.

### 점수, 반응, 관통

- 피벗 반응폭은 피벗 다음 세션부터 최대 20 유효 세션 중 `as_of` 이하 데이터만 사용한다. 저점 피벗은 관찰 고가 최댓값−피벗 저가, 고점 피벗은 피벗 고가−관찰 저가 최솟값이다. 미래 자료가 부족해도 가용 기간만 쓰고 `reaction_bars`에 관측 수를 남긴다. 종가와 반대 고저의 당일 순서는 점수의 성과 판정에 쓰지 않는다.
- `r_i=min(max(reaction_range/ATR_i,0),5)`, `w_i=0.5^(피벗 이후 경과 유효 세션/189)`, `score=Σ(w_i*r_i*0.5^b_i)`로 정의한다. `b_i`는 해당 피벗 시점부터 `as_of`까지의 구간 이탈 주기 수다. support 이탈은 종가가 하단−0.5×당일 ATR 아래로 마감, resistance는 상단+0.5×당일 ATR 위로 마감했을 때 시작한다. 최초 이탈 뒤 같은 방향으로 유지된 세션은 반복 세지 않고, 종가가 구간 안으로 복귀한 후 새 이탈이 있을 때만 증가한다. inside의 이탈 횟수는 위·아래 이탈 주기의 합으로 하고 결과에 방향별 수를 별도 기록한다.
- `touch_points`는 후보 닫힌 구간 안의 확정 피벗만 포함하고 가격·극값 날짜·high/low 종류·confirmed_at·reaction_bars·reaction_atr를 기록한다. `touches == len(touch_points)`를 항상 만족한다.

### 결과 계약

각 구간은 type, lower/upper, touches, touch_points, score, distance_atr, 반응 및 관통 요약을 가진다. `inside.distance_atr=0`이며 `break_above=upper+0.5×as_of ATR`, `break_below=lower−0.5×as_of ATR`을 출력하고 단일 invalidation은 없다. support/resistance 거리는 현재 종가와 가까운 경계 사이 절댓값/`as_of` ATR이다. 누락 ATR, 잘못된 0/음수 가격, 빈 시계열을 0으로 대체하지 않는다.

전체/최근 252 유효 세션 `ln(close)`의 OLS slope·R²를 출력한다. R²<0.3은 `sideways`, 그 외 slope 부호에 따라 `up`/`down`이다. 출력에는 as_of, ticker, Yahoo 응답 스냅샷 해시, 가격 조정 설명, ATR, unknowns, 최근 배당락일(있으면 날짜, 없으면 명시적 미확인), 추세, zones, `check_windows`, `validation`을 포함한다.

## 상태와 버전 관리

- `latest_evaluation`은 해당 평가 저장소의 평가시각이 가장 최근인 append-only 기록이다. 기록은 sample ID, params/baseline 버전, 유형별 결과, 평가 시각, 입력·출력 해시를 가진다.
- `last_passed_evaluation`은 참고용으로 가장 최근 통과 기록을 보존하되 현재 판정 권한은 없다. 최신 평가가 `failed`, `inconclusive`, `not_evaluated`이면 `effective_status`도 그 상태다. 과거 통과를 최신 상태로 대체해 표시하지 않는다.
- `pending`은 저장된 최신 표본 식별자와 최신 평가 표본 식별자가 다른지 나타낸다. `stale`은 동일 표본 계보에서 평가 표본보다 최근 완료 분기가 2개 이상 지났는지 나타낸다. 둘은 평가 결과 상태와 별도 메타데이터다. stale 또는 pending인 `passed`는 `effective_status=unverified`로 낮춘다. 평가 실패가 우선 기록된 경우 `effective_status=failed|inconclusive|not_evaluated`를 유지하고 별도 `pending`/`stale` 플래그를 표시한다.
- 초기 평가가 없으면 `latest_evaluation=null`, `last_passed_evaluation=null`, `effective_status=not_evaluated`다. 표본 refresh는 표본 포인터와 `pending`만 갱신하고 평가 결과/상태를 변경하지 않는다.
- 차트 검증은 `chart_validation.status`로 별도 관리한다. chart-check `ok`는 구간 예측력이 검증됐다는 의미가 아니며 `effective_status`를 바꾸지 않는다. 드로잉은 chart-check `ok`와 유효한 구간 계산 결과가 모두 있어야 한다.
- 제안 상태 객체: `latest_evaluation {record_id,sample,params_version,baseline_version,evaluated_at,status,lift,ci95}`, `last_passed_evaluation {record_id,sample,evaluated_at}|null`, `effective_status`, `latest_sample`, `pending`, `stale`, `chart_validation`. `record_id`는 평가 정규화 payload SHA-256 앞 12자다.

## 고정 표본 zone-backtest

### 코호트, 시점, 수정 금지

- 고정 표본은 기본 48종목과 토스 보유 ticker의 합집합으로 확장한다. 사용자가 확정한 범위에 따라 **미국 상장 종목만** 포함하며 한국 상장 종목은 XNYS 거래 달력·가격 기준과 맞지 않아 제외한다. 기존 읽기 전용 계좌 어댑터에서 미국 ticker와 보유 확인 시각만 추출하며 가격 계산은 Yahoo 일봉을 사용한다. LLM 분석을 실행해 ticker를 추출하지 않는다. 계좌 식별자·수량·평가액·원문 응답은 표본 파일, 프롬프트, 로그, 보고서, 원격 tracing에 넣지 않는다. 개인 표본 manifest는 저장소 밖 로컬 경로에 보존한다.
- 기본 처리·보고 순서는 현재 보유 ticker 우선, 나머지 기본 표본, 13F 추가분 순이며 그룹 안에서는 정규화 ticker 오름차순이다. 사용자가 명시적으로 ticker를 지정한 요청은 그 선택을 존중한다. chart-zones의 요청당 최대 10종목 제한은 유지하고 보유가 10개를 넘으면 결정론적 순서로 나누어 처리하며 남은 종목을 누락하지 않는다. 우선순위는 구간 score나 통계 가중치를 바꾸지 않는다.
- 보유 확인으로 추가한 ticker는 이후 매도해도 고정 표본에서 제거하지 않고 현재 보유 우선순위만 해제한다. 신규 보유 편입은 새 불변 sample revision과 해시를 만들고 기존 평가를 덮어쓰지 않는다. 같은 보유 ticker 집합으로 재실행하면 표본 내용은 동일하며 조회 시각은 별도 운영 메타데이터로 둔다. 계좌 조회 실패 시 보유 0개로 해석하지 않고 마지막 확인 시각과 우선순위 확인 불가 상태를 보고한다.
- 보유 추가분은 별도 `holdings_added` 코호트로 보고하며 기본 48종목의 주 통과 판정에 합산하지 않는다. 기본 표본과 중복된 ticker는 한 번만 계산하고 보유 태그를 붙인다. 현재 보유 종목을 과거부터 보유했다고 가정하지 않는다. 확인 시점 이전 성과는 사후 선정 표본의 탐색 결과로만 표시하고, 시점 일관 평가에는 보유 확인 다음 XNYS 세션부터 편입한다. 기존 표본으로 이미 적격이던 과거 사건은 원래 코호트에 유지한다.
- 고정 48종목은 계획 원안의 목록을 그대로 코드와 sample manifest에 고정한다. 구성은 M7 7, 사용자 지정 7, 섹터 대표 16, 고변동 개별주 6, 1배 ETF 6, 2배 ETF 3, 3배 ETF 3이다. 고정 48종목은 사용자 선정의 목적 표본이며 당시 상장 유니버스의 무작위 표본이 아니므로 자체적으로 생존/일반화 편향을 제거하지 않는다. 코호트를 임의로 바꾸지 않고 보고서 주장을 이 표본의 관측 성과로 한정한다. 상장폐지·티커 변경·합병·거래정지 자료 공백을 사유와 함께 남긴다.
- 각 표본 ticker의 첫~마지막 Yahoo 유효 봉 사이 XNYS 세션 중 결측·잘못된 OHLC가 1%를 넘으면 해당 ticker를 평가에서 제외하고 날짜 수·비율·사유를 남긴다. 연속 두 XNYS 세션 종가 변화가 절댓값 50% 이상이고 당일 `Stock Splits`와 조정비율 곱이 ±20% 로그 허용 안에서 맞지 않으면 설명되지 않은 가격 단절로 제외한다. IONQ는 합병 후 첫 거래일인 2021-10-01 이전 행을 제외한다. Yahoo가 현재 표본에서 이력을 제공하지 못해도 ticker는 immutable sample에 남고 제외 사유를 기록한다.
- 학습/검증 기간은 sample v1에서 튜닝 2019-01~2024-08, 검증 시작 2024-11로 하되 기준일 간격 20 유효 세션, 미래 결과 관찰창 60세션을 쓴다. 튜닝 기준일 중 마지막 60개 미래 세션이 첫 검증 기준일보다 앞서는 날짜만 학습에 남긴다. 실제 첫/마지막 날짜와 embargo 세션 수를 tuning manifest에 기록하고, 검증 결과를 파라미터·유형·문턱 선택에 사용하지 않는다.
- zone-backtest 수집 범위는 최소 2014-01부터다. 계산기의 최근 5년 조회 범위와 혼동하지 말고, 백테스트의 과거 `as_of`에 필요한 전체 입력 prefix를 내려받아 불변 스냅샷으로 보존한다.
- Yahoo는 오늘 응답한 수정 이력을 줄 수 있으므로 과거 point-in-time OHLC가 확보되지 않으면 해당 백테스트는 `research_only`로 표시하고 엄격한 시점 재현을 주장하지 않는다. 수집 시점별 불변 응답 스냅샷과 SHA-256을 보존하고, 현재 응답으로 과거를 재실행한 결과와 당시 저장 자료 결과를 구분한다.
- 고정 코호트 안의 상장폐지·티커 변경·합병·가격 공백은 별도 집계하고 결측 종목을 임의 대체하지 않는다. 이 한계를 결과와 함께 공개한다.

### 이벤트 판정과 OHLC 순서

- 실제 구간의 첫 미래 터치는 기준일 다음 유효 세션부터 60세션 안에서 support `low<=upper`, resistance `high>=lower`로 판정한다. 터치 봉은 touch-rate에만 포함한다. 반등 성공/실패 이벤트 창은 터치 다음 세션부터 시작하고 그 터치 봉은 결과 판정에서 제외한다. 이는 당일 반등/이탈의 순서를 OHLC만으로 알 수 없기 때문이다.
- 터치 다음 세션 이후 첫 성공/실패를 평가한다. support 성공은 `high>=upper+1×고정 기준일 ATR`, 실패는 `close<=lower−0.5×고정 기준일 ATR`; resistance는 반대로 `low<=lower−1×ATR`, 실패는 `close>=upper+0.5×ATR`다. 한 봉에서 성공/실패가 모두 충족되면 실패로 처리한다. 먼저 발생한 조건으로 종료한다.
- 터치 없음은 `not_touched`; 60세션 내 결과 없음은 `touched_unresolved`; 터치 후 첫 평가 봉까지 자료가 없으면 `unresolved_data`로 별도 집계한다. 기준일 이후 60개 XNYS 봉이 아직 관찰되지 않은 최신 샘플은 검증 사건에서 제외하고 미완료 건수로 기록한다.
- inside는 기준일 직전까지의 가장 최근 구간 밖 종가로 방향을 정하며, 방향이 불명확하면 `direction_unknown`으로 제외·계수한다. inside는 기준일 종가가 이미 구간 안에 있으므로 기준일을 activation/touch 기준일로 기록하고, 첫 미래 세션부터 고정 ATR 성공·실패 장벽을 평가한다. support/resistance는 첫 미래 터치 봉을 touch rate에만 포함하고 그 다음 세션부터 결과 장벽을 평가한다. 두 방식의 분모와 touch 해석은 결과에서 분리해 공개한다. 한 봉에서 양쪽 장벽을 모두 통과하면 실패로 판정한다.
- 같은 봉에서 성공·실패가 모두 참이면 실패. O/H/L/C 중 불완전 행이 있으면 그 봉은 판정할 수 없고 데이터 불명으로 처리한다.

### 비교 기준

- 기존 제안의 독립 무작위 중심 baseline을 `random-unconditional`로 보존한다. 유형별 거리 방향·구간 폭 제한, 실제 구간 중첩 배제, ticker/as_of/유형/version 해시 seed를 적용한다.
- 별도로 `matched` baseline을 추가한다. 각 실제 구간과 같은 ticker, 기준일, zone type, 변동성 환경 및 60세션 평가 창을 사용한다. support/resistance 대조군은 linear price width/기준일 ATR 차이를 ±0.05 ATR, 현재가에서 가까운 경계까지의 `distance_atr` 차이를 ±0.25 ATR 범위에서 매칭한다. inside 대조군은 실제 `ln(upper/lower)` 폭과 같고 기준일 종가를 포함하며 `distance_atr=0`이다. 생성 seed 순서에서 최대 1,000회 뽑아 200개를 만든다. 표본·평가 날짜·구간 유형을 동일하게 묶어 비교한다. matched 구간은 실제 구간과 겹칠 수 있으므로 겹침을 제거하지 않고 개수·비율을 기록한다. 이 조건에서 중첩 금지는 폭·거리 매칭 자체와 충돌하며, 가까운 실제 구간만 사후 제외하면 새로운 선택 편향이 생기기 때문이다. 불가능한 거리/폭 또는 1,000회 안에 200개를 만들지 못한 실제 구간만 `unmatched`로 빼고 사유를 남긴다. 이 v1 caliper와 overlap 정책을 validation 전에 고정하고 matched baseline을 주 판정 비교로 쓴다.
- 각 실제 구간마다 200개 비교 구간을 생성하되 독립 사건 200개로 간주하지 않는다. `random-unconditional` seed는 `SHA-256(ticker|as_of|구간유형|baseline_version)`의 앞 8바이트이며 rank 순으로 생성한다. matched baseline 난수는 별도 versioned seed namespace를 사용한다. 재추출은 최대 1,000회이며 조건 불충족 건은 사유와 함께 비교에서 제외한다.
- 세 지표를 혼합하지 않는다: (1) 조건부 hit rate = touched 중 판정 완료 성공/완료, (2) 유효 적중률 = 전체 표본 중 성공/전체 eligible zones, (3) touch rate = touched/전체 eligible zones. `not_touched`, `touched_unresolved`, 데이터 불명·unmatched를 각각 공시한다. 주 효능 지표와 최종 통과 기준은 단계 3 전에 사전등록한다. 사후에 더 유리한 분모로 갈아타지 않는다.
- 무작위 반복은 독립 표본이 아니므로 기존의 단순 합산 lift와 블록 bootstrap만으로 유효 표본 수가 확보됐다고 간주하지 않는다. 종목을 군집 재표본한 뒤 전체 공통 기준일 축에서 종목별 시간 원형 block을 뽑는다. 날짜 자료가 없는 종목/날짜 조합은 0개 사건으로 유지해 시간 간격을 압축하지 않는다. matched pair는 각 재표본에서 같은 실제 사건과 짝을 유지한다. block 길이 3/6/12 민감도를 보고하며 각 설정에서 완전 시간 block 6개 미만이면 해당 CI는 `inconclusive`다. seed, block count, 유효 종목·기준일·사건 수를 기록한다.
- v1 최소 유효 표본은 matched 평가 사건 기준 ticker 10개, 서로 다른 `as_of` 50개, 중복 제거한 ticker·zone type·touch-date 터치 에피소드 100개다. 20세션 간격에서 50개 기준일은 약 4년의 검증 자료를 요구한다. 2026년 현재 고정 2024-11 시작 holdout은 50개에 미달하므로 결과는 `inconclusive`이며 `passed`를 출력할 수 없다. 기준일 간격을 사후 축소하지 않는다. 분모 0 bootstrap 반복이 1%를 넘거나 표본 gate/대조군 생성 조건을 충족하지 못하면 `inconclusive`다. 한 사건이 기준일 겹침 창으로 반복 포함되더라도 종목 군집과 시간 블록 재표본화를 적용하고, 실제 독립 에피소드 수는 별도로 공개한다.
- 검증 전 고정한 두 endpoint(support/resistance 통합, inside)에 각각 방향성 one-sided 유의수준 0.025를 적용한다. percentile two-sided 95% CI 하한>0 조건은 endpoint별 one-sided 0.025 검사와 같아 두 endpoint의 동시 거짓 통과 확률을 Bonferroni 상한 0.05로 제한한다. support/resistance 통과에는 low/high 변동성 tercile의 효과점 추정치가 각각 0보다 커야 하나, 이 하위그룹 부호 조건을 별도 유의성 주장으로 해석하지 않는다. inside는 별도 endpoint CI 하한>0을 요구한다. random-unconditional는 기술 비교이며 통과 상태를 부여하지 않는다. 2·3배 ETF, 사용자 지정 7종목, 토스 보유 추가분, 13F 추가 코호트는 별도 기술 통계이며 주 통과 판정에 합치지 않는다. 189/378/756 세션 반감기는 튜닝 구간 민감도 분석으로만 비교하고 v1을 검증 구간에서 바꾸지 않는다.

## 13F 동적 코호트 (4단계)

- 고정 sample v1 48종목과 13F 추가 종목은 manifest·집계·상태 객체의 서로 다른 cohort ID로 유지한다. 13F 결과는 보조 일반화 자료이며 고정 표본의 주요 통과 기준에 합치지 않는다.
- SEC bulk ZIP은 filing accepted timestamp를 싣지 않으므로 현재 refresh가 실제 관측한 입력보다 과거에 편입 가능했다고 가정하지 않는다. 후보의 첫 eligible 세션은 `max(dataset_downloaded_at, mapping_observed_at, accepted_at_if_available)` 이후의 다음 XNYS 세션이다. `accepted_at_if_available`가 없으면 filing date를 대용하지 않고 dataset observation time으로 늦춘다. 보고 분기 종료일은 공개일처럼 쓰지 않는다.
- 매 분기 point-in-time 코호트를 별도 생성한다. 발표 이후 시점에 해당 종목을 편입하되 전 발표 분기·기간으로 역적용하지 않는다. 과거 분기 성과를 보려면 해당 시점에 공개돼 있던 원본 filing archive만 사용한다. 현행 13F 회사 목록으로 과거 코호트를 재작성하지 않는다.
- 13F는 기관 롱 포지션의 지연 보고이며 전체 시장 보유 현황이 아니다. 생존·보고 선택·집계 규모 편향을 표기한다. 전체 filer 목록, 제출 지연, 누락/수정 filing, 기관별 AUM·보고 단위 차이를 manifest와 품질 지표로 남긴다.
- 동적 코호트는 최신 report period의 `13F-HR` holdings에서 share rows만 사용하고 `PUTCALL`이 있는 옵션과 `PRN` 원금 행을 제외한다. filings는 CIK/report period별로 정렬하고 restatement amendment는 대체, new-holdings-entry amendment는 추가한다. 모호한 amendment 상태의 filer는 제외한다. `VALUE`는 원본 단위 $1,000에서 USD로만 정규화하며 share amount와 합치지 않는다. 보고 accession별 VALUE를 CUSIP 단위로 집계해 상위 100 CUSIP만 mapping한 뒤 U.S. exchange의 정확한 Common Stock 결과를 ticker별로 합산해 최대 10 ticker를 고른다. 공유 재량·기관 보고 중복으로 이 합계가 unique beneficial ownership은 아님을 명시한다.
- CUSIP은 OpenFIGI 요청 중에만 사용하고 SEC 원문/매핑 response를 저장하지 않는다. local sample에는 CUSIP SHA-256, FIGI, 단일 매핑 여부와 observation time만 남긴다. 무인증 mapping은 `exchCode=US`, 결과 1개, `marketSector=Equity`, `securityType=Common Stock`, ticker/FIGI 존재 조건을 모두 통과해야 한다. 나머지는 `ambiguous`, `unmapped`, `ambiguous_security_type`로 남긴다. 현재 OpenFIGI mapping을 관측 timestamp 이전으로 소급하지 않는다.
- 단계 3의 `zone-sample refresh`는 기존 읽기 전용 Toss 어댑터에서 미국 ticker만 읽는다. 조회 시각이 없거나 계좌 조회가 실패하면 기존 표본을 바꾸지 않는다. 조회 시각과 현재 우선순위는 별도 `latest.json` 운영 포인터에 두고, 불변 sample hash에는 새 보유 ticker의 최초 확인 시각만 둔다. 같은 ticker 집합을 다시 읽으면 sample ID와 sample bytes는 그대로다. 한국 ticker는 표본 밖으로 제외한다.
- 단계 4는 `zone-sample refresh --source sec`로 별도 수행하며 Toss 인증/조회와 분리한다. SEC dataset ZIP과 OpenFIGI만 읽고 Yahoo/LLM/주문/Broker API는 호출하지 않는다. SEC archive/cache와 sample은 저장소 밖 개인 경로에 두고 원문 매핑 응답은 저장하지 않는다. 같은 SEC ZIP hash와 동일한 mapping result는 같은 불변 sample bytes/ID를 만들고 latest pointer에는 관측 시각과 eligibility session을 둔다. 주간 자동 실행은 CLI가 등록하지 않으며 사용자/운영자가 local scheduler를 구성한다.

## Tratto 연동과 드로잉

- 공식 README는 Tratto를 Yahoo Finance의 실제 페이지와 로컬 브라우저 확장을 잇는 MCP bridge로 설명하고 `get_chart_data`, `get_chart_summary`, `read_drawings`, `get_drawing_guide`, `open_chart`, `set_periodicity`, `set_range`, 사각형/선 그리기 및 관리 도구 이름을 열거한다. README는 개별 도구의 JSON Schema를 제공하지 않고 현재 이 실행 환경에도 Tratto MCP 서버가 연결되어 있지 않다. 그러므로 인자명·필수성·응답 타입·앵커 단위를 추측하지 않는다. 단계 2 시작 전에 설치된 버전의 MCP `tools/list` 원문 schema와 실제 합성 종목 응답을 검토·기록한다. 명세상 근거: [Tratto 공식 README](https://github.com/Taoo425/tratto).
- `chart-zones`는 최대 10 ticker, 기본 로컬 저장소 `~/.tradingagents/chart-zones/<ticker>/<as_of>-<snapshot_hash8>/`에 `zones.json`, `snapshot.csv`, 실패·체크 메타데이터를 쓴다. 심볼 실패는 다른 심볼 처리를 막지 않는다. 주봉 요청은 미지원으로 명시하고 일봉으로 대체하지 않는다.
- `check_windows`는 최근 20 유효 봉, 최근 배당락 전후 각 5 유효 봉(없으면 not_applicable), 표시되는 후보 중 가장 오래된 touch 날짜 전후 각 5 유효 봉이다. 겹치는 날짜는 합치고 각 원래 window ID를 보존한다. 실제 요청량을 manifest에 기록한다.
- Tratto 응답 CSV는 `chart-check` 입력만 허용하며 원문을 `chart_check.csv`에 저장한다. CLI는 run의 `snapshot.csv`를 기준 자료로 읽고 차트 입력은 메모리에서만 비교한다. 입력은 정확한 헤더 `date,o,h,l,c,v`를 요구한다. 각 window를 따로 조회한 원문 CSV 블록은 `check_windows`의 고정 순서로 빈 줄만 사이에 두어 연결하며 셀·행·숫자는 편집하지 않는다. 단일 CSV 블록이 전체 합집합 날짜를 담는 입력도 허용한다. 각 블록의 날짜·행 수는 해당 window 목록과 맞아야 하며 window 사이 겹치는 날짜는 각 원문 블록 안에서 반복될 수 있다. 블록 안 중복 날짜는 오류다. timezone-aware는 `--chart-timezone`으로 지정한 IANA 시간대(기본 America/New_York)로 변환, naive는 날짜 부분으로 정규화한다. `as_of` 이후 행은 검증에서 제외하고 window별로 개수·날짜를 기록한다.
- 각 OHLC 허용 오차는 `max(0.1%×abs(Yahoo 값), $0.01)`다. 통화가 USD가 아닌 종목은 통화별 최소 단위 정책을 schema에서 명시한다. 거래량은 비교하지 않는다. 상태는 `ok|mismatch|date_mismatch|insufficient|unknown`이며 데이터 일치만 뜻한다. ratio 중앙값은 0 또는 음수 Yahoo 기준가가 있으면 만들지 않는다. 분할·배당 기준 단서는 이유 코드와 비교 기간을 함께 남긴다.
- 응답 누락 범위는 한 번 set_range 확대 후 재요청한다. mismatch/date_mismatch는 get_chart_data를 한 번 더 실행해 새 원문을 저장하고 다시 확인한다. 모든 시도 결과와 재시도 action/count를 `chart_validation.json`에 보존한다. `insufficient`, `unknown`, 재검사 실패에서는 드로잉을 금한다. 수동 수치 수정, LLM 재계산도 금한다.
- 드로잉은 날짜·가격을 JSON 입력으로 직접 쓴다. `get_drawing_guide`의 palette, 식별자, anchor format을 실제 schema에서 읽은 뒤 support/resistance/inside의 색·선·사각형 의미를 references에 고정한다. 사각형은 최초 touch 극값일에서 마지막 검증 봉까지다. inside는 양방향 기준을 표시하는 중립 점선이다. 표시 전 `read_drawings`로 중복을 탐지하고, 표시 후 다시 읽어 drawing ID와 실제 start/end date/price anchor가 CLI 출력값과 일치하는지 검사한다. 다를 경우 `drawings.json`에 실패를 남기고 완료로 표시하지 않는다.
- 동일 기준일과 같은 라벨·구간은 중복 생성하지 않는다. 다른 기준일의 기존 `tc-` 드로잉은 삭제하거나 수정하지 않고 기록만 한다. `clear_drawings`, `remove_drawing`, `undo_drawing`, `delete_saved_drawing`은 사용자 명시 확인 없이는 호출하지 않는다. Tratto는 표시·읽기 전용 보조 수단이며 주문·거래 도구를 호출하지 않는다.
- chart-check 결과와 zone-backtest `effective_status`는 하나의 `validation` boolean으로 축약하지 않는다. 차트 `ok`더라도 통계 미검증이면 드로잉 보고에 미검증 경고를 유지한다. 검증 통과가 stale/pending이면 재평가 전 상태를 표시한다.

## 출력 문구와 증거

- `inside`는 현재 역할이 정해지지 않은 가격 범위이며 돌파 방향을 예측하지 않는다. 상·하단 trigger와 이탈 뒤 재진입 규칙을 출력한다.
- 날짜·가격이 있는 도구 출력은 기존 `collect_tool_evidence`를 통해 숫자 증거에 수집한다. Market Analyst는 날짜와 가격이 있는 `get_chart_zones` 결과만 인용하고, 종가 기준 분류와 계산 상수를 설명한다. 목표가·기대수익률로 부르지 않는다.
- 가격 basis를 “Yahoo split-adjusted, dividend-unadjusted OHLC”와 같이 명시한다. 통계 통과 및 stale/pending 문구는 상태 규칙대로 출력하고 “과거 자료의 무작위 baseline 대비 관찰 결과이며 미래 보장은 아님”을 포함한다. 계산 결과만 있고 evaluation이 없거나 inconclusive/failed면 “미검증으로 취급, 단독 매매 근거로 쓰지 말 것”을 포함한다.

## 검증 계획과 위험

- 구간 테스트는 합성 OHLCV만 사용한다. 동일 입력 byte reproducibility, 미래 행 변형 불변성, 확정 경계, 피벗 동점·경계 배정, 커널 질량·다봉 KDE, 겹침 분리, 폭 상한, 최소 터치, 반응창 차단, 관통 재진입, inside 상한, 결측과 안정 정렬을 검사한다.
- Yahoo mock은 `auto_adjust=False`, 요청 날짜/범위, 기업행동, 오류 기록, 티커 부분 실패 지속, 근거 수집, 호출 횟수 상한을 확인한다. 테스트는 실제 Yahoo/LLM/Toss를 호출하지 않는다.
- chart-check 테스트는 timezone, 누락·중복·추가 행, as_of 이후, 허용오차 경계, 조정 기준, 재시도 횟수와 실제 schema fixture를 검증한다. 드로잉 fixture는 schema 기반 anchor·ID를 검사한다. 라이브 브라우저 smoke는 사용자가 연결된 로컬 Tratto를 실제로 쓸 수 있을 때 별도 실행하고 증거를 남긴다.
- backtest fixture는 터치 봉 제외, same-bar 실패, no-touch/unresolved 구분, inside 방향, baseline 매칭/공통 지지영역, seed·bootstrap 재현, block 3/6/12, 군집 의존성, 최소 표본 미달, 단위별 결과와 실패 상태 보존을 확인한다.
- 13F fixture는 filing accepted timestamp, 다음 세션 eligibility, 늦은 filing, amendment, 단위/주식종류 분류, CUSIP 매핑 충돌, 미매핑 유지, 분기 간 추가 전용 샘플 포인터, 같은 입력 재현을 검사한다.
- 주요 미해결 위험: Yahoo의 사후 분할 조정·정정 이력으로 인한 point-in-time 부재, 일봉만으로 복원 불가능한 봉 내부 경로, 거래 사건·ticker·시간 의존성, 13F 45일 공개 지연 및 선택 편향, Tratto/Yahoo 페이지 DOM·MCP schema 변경, 긴 계획을 단계 간 범위가 밀어내는 위험. 각 위험은 위 gate와 보고 레이블로 노출한다.
