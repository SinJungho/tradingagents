# Tasks

## 1. 출처 확인

- [x] 코디네이터 확인(2026-11-13): [IVV CSV](https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf/1467271812596.ajax?fileType=csv&fileName=IVV_holdings&dataType=fund)와 [IWM CSV](https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund)는 HTTP 200이지만 CSV 대신 약 2.3 MB 상품 HTML을 반환하며 페이지에서 CSV 링크를 찾지 못했다. 기존 IWM 발굴 경로는 이번 변경 범위에서 수정하지 않는다.
- [x] 코디네이터 확인(2026-11-13): S&P DJI 전체 구성 목록은 구독이 필요하여 범위 밖이다.
- [x] 코디네이터 확인(2026-11-13): [SPDR SPY 일별 보유 XLSX](https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx)는 HTTP 200, `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`를 반환한다. 2026-11-11 기준일의 표에서 헤더 뒤 Ticker가 있는 행은 504개다.

## 2. 구현

- [x] 표준 라이브러리 `zipfile`과 `xml.etree`로 SPY XLSX를 파싱하고 날짜·티커 수·티커 형식을 검증한다.
- [x] 시장 보고서 `universe()`에서 SPY 보유 자료를 먼저 사용하고 실패하면 기존 Wikipedia 현재 구성 경로로 대체한다.
- [x] 시장 폭 evidence와 Markdown에 SPY 대용치 종류, 공식 구성 아님 안내, 구성 기준일을 표시하고 Wikipedia 대체 시 기준일을 미확인으로 둔다.
- [x] SPY 파서, 범위 밖 행 수, 소스 대체, evidence·Markdown 기준일을 합성 자료 테스트로 확인한다.

## 3. 검증

- [x] 관련 테스트: 55 passed.
- [x] 전체 pytest: 1791 passed, 2 skipped, 103 subtests passed.
- [x] Ruff: `ruff check .` 통과.
- [ ] OpenSpec strict 검증 (샌드박스 미실행; 코디네이터 병합 시 실행)

전체 테스트의 두 skip은 Ruff가 checkout/PATH에 없어서 생긴 agent-hook skip, 선택 의존성 `langchain_aws`가 설치되지 않아 생긴 provider skip이다. OpenSpec CLI는 샌드박스 오프라인 npm 캐시에 없어 strict 검증을 실행하지 못했다 (`ENOTCACHED`).
