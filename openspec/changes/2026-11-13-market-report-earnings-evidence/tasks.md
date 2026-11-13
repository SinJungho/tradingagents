# 1. 조사 관문

- [x] 기존 SEC EDGAR 구현에서 `cik_for`, `_user_agent`, `_fetch_json` 재사용 지점을 확인한다.
- [x] 공개 SEC submissions API와 Yahoo 실적 일정 URL에 GET을 시도하고 상태·형식·기준일 존재 여부를 기록한다.
- [x] 설치된 yfinance 구현의 `get_earnings_dates` 반환 열을 확인하고 합성값으로 계산 기준을 정리한다.
- [ ] 네트워크가 가능한 환경에서 SEC submissions 응답의 8-K `items` 및 보고 대상일 자료를 확인한다.
- [ ] 공식 SEC 출처를 검증한 뒤 proposal.md와 요구사항 spec을 작성하고 구현한다.

## 조사 결과

| URL | HTTP 상태 | 형식 | 기준일 `2026-11-12` 포함 여부 |
| --- | --- | --- | --- |
| `https://data.sec.gov/submissions/CIK0000320193.json` | 확인 불가: GET 시 DNS 오류 | 확인 불가 | 확인 불가 |
| `https://finance.yahoo.com/calendar/earnings?symbol=AAPL&offset=0&size=25` | 확인 불가: GET 시 DNS 오류 | 확인 불가 | 확인 불가 |

현재 실행 환경에서 두 공개 URL 모두 DNS 오류로 응답을 받지 못했다. SEC API는 공식 출처이고 저장소에 CIK 조회·User-Agent·JSON 요청 helper가 있지만, 이 실행에서 제출 JSON의 형식과 날짜별 Item 2.02 존재 여부를 검증하지 못했다. Yahoo도 실제 응답의 형식과 기준일 포함 여부를 확인하지 못했다. OpenSpec 지침의 조사 관문에 따라 코드와 ADDED 요구사항은 아직 작성하지 않는다.

설치된 yfinance의 `get_earnings_dates` 구현 문서에서 `EPS Estimate`, `Reported EPS`, `Surprise(%)` 열을 확인했다. 실제 Yahoo 응답으로 확인된 것은 아니다. 합성 예시에서 Reported EPS `1.25`, EPS Estimate `1.00`이면 `Surprise(%) = ((Reported EPS - EPS Estimate) / abs(EPS Estimate)) * 100 = 25.0%`로 계산할 수 있다. 어느 한 값이라도 없거나 유효한 숫자가 아니면 서프라이즈는 미계산으로 둔다. Yahoo 값은 2차 출처로 표시해야 한다.
