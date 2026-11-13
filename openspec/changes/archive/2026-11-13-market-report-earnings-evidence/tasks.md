# 1. 조사

- [x] SEC EDGAR submissions와 Yahoo 실적 응답 스키마를 확인한다.
- [x] SEC 제출시각을 동부시간으로 변환해 대상일을 판정하는 근거를 기록한다.

## 조사 결과

| URL | HTTP 상태 | 형식 | 기준일·시각 확인 |
| --- | --- | --- | --- |
| `https://data.sec.gov/submissions/CIK0000320193.json` | 코디네이터 확인(2026-11-13): 200 | `application/json` | `acceptanceDateTime`(UTC), `filingDate`, `reportDate` 포함. 예시 8-K Item 2.02 접수시각 `2026-11-02T21:30:23.000Z`는 동부시간 2026-11-02 16:30이며 대상일 판정에 동부시간 사용 |
| `https://finance.yahoo.com/calendar/earnings?symbol=AAPL&offset=0&size=25` | 샌드박스 GET 미확인 | HTML 표를 읽는 로컬 yfinance 구현 확인 | `Reported EPS`, `EPS Estimate`, `Surprise(%)` 열 확인. 실적값은 2차 출처로 표시 |

SEC submissions는 `filings.recent`의 병렬 배열에서 `form == 8-K`, `items`에 `2.02`, 동부시간으로 변환한 `acceptanceDateTime` 날짜를 함께 확인한다. 접수 식별자는 accession 번호와 primary document를 사용해 EDGAR 문서 URL을 만든다. Yahoo의 합성값 Reported EPS `1.25`, EPS Estimate `1.00`이면 서프라이즈는 `((1.25 - 1.00) / abs(1.00)) * 100 = 25.0%`이다. 어느 값이든 없거나 숫자가 아니거나 예상 EPS가 0이면 서프라이즈는 계산하지 않는다.

# 2. 명세와 구현

- [x] `실적 발표 확인과 값 출처` 요구사항과 시나리오를 추가한다.
- [x] `PublicMarketData`에 `_once`를 사용하는 SEC submissions 조회 메서드를 추가한다.
- [x] 보고 대상일의 SEC 공식 공시 확인 및 Yahoo EPS 2차 출처 항목을 추가한다.
- [x] 서프라이즈 계산식과 미확인 가이던스를 표시하고 다음 거래일 예정 항목을 유지한다.
- [x] 대상일에 공시가 없는 정상 확인은 표본 요약으로 합치고 종목별 결측 행·가이던스 행은 만들지 않는다.
- [x] SEC 일부/전체 실패는 종목 목록이 포함된 요약 상태로 표시한다.

# 3. 검증

- [x] 합성 submissions JSON에서 Item 2.02, 동부시간 날짜 판정, 항목 없음과 SEC 실패를 검증한다.
- [x] 합성 Yahoo 행에서 일부 EPS 결측 시 서프라이즈 미계산을 검증한다.
- [x] 관련 테스트: 35 passed.
- [x] 전체 pytest: 1793 passed, 2 skipped, 24 warnings, 103 subtests passed.
- [x] `ruff check .`와 `tradingagents --help` 통과.
- [x] OpenSpec strict 검증은 샌드박스 미실행(오프라인 npm 캐시 없음)으로 보고한다.
