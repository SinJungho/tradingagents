# SEC 재무 사실 404를 자료 없음으로 구분

## Why

2026-11-15 `discover --universe all` 실측의 종목 실패 93건 가운데 상당수는 SEC에 CIK는 있지만 XBRL 재무 사실(companyfacts)이 아직 없는 회사(AYA, BIOT 등 주로 신규 상장)였다. SEC는 이때 HTTP 404를 돌려주는데, `sec_edgar._fetch_json`은 모든 HTTP 오류를 `VendorUnavailableError`로 바꿔 정상적인 자료 없음이 "SEC EDGAR annual facts" 공급자 실패로 집계됐다. 일시 실패로 보고 2차 조회에서 같은 404를 다시 요청했고, 실패율도 부풀려졌다(같은 실행 로그의 SEC 404 110줄).

## What Changes

- `_fetch_json`이 HTTP 404에 `VendorUnavailableError`의 하위 예외 `EdgarNotFound`를 낸다. 다른 HTTP·연결 오류는 그대로 `VendorUnavailableError`다.
- 재무 사실을 읽는 `get_annual_facts`와 재무제표 조회가 `EdgarNotFound`를 `NoMarketDataError`(XBRL 재무 사실 없음)로 바꾼다. 발굴은 이를 실패가 아닌 자료 없음으로 처리해 해당 팩터를 보류하고 2차 조회하지 않는다.

- `get_with_retry`는 원본 응답을 떼어 낸 예외에 상태 코드를 `status_code`로 붙인다. `_fetch_json`은 `exc.response.status_code`만 읽어 실제 실행에서 상태를 한 번도 얻지 못했다(오류 문구가 늘 `(HTTPError)`). 두 형태를 모두 읽게 한다.

## Out of Scope

404 결과 캐시, 시장 보고서 submissions 404 처리 변경, SEC 재시도 정책 변경.
