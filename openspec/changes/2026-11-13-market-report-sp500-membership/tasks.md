# Tasks

## 1. 출처 조사 관문

- [x] S&P DJI 공개 자료 범위와 데이터 서비스 접근 조건을 확인한다.
- [ ] IVV 보유 종목 CSV의 현재 응답 형식, 보유 기준일, 주식 행 수를 HTTP GET으로 확인한다.

### 조사 결과

- S&P DJI의 [S&P 500 지수 페이지](https://www.spglobal.com/spdji/en/indices/equity/sp-500/)는 웹 검색으로 확인했을 때 상위 10개 구성 종목과 `Full Constituents List` 항목을 표시한다. 다만 이 워크트리에서 공개 URL에 직접 GET을 시도했을 때 HTTP 상태는 `000`이었으며, 전체 목록 버튼이 비로그인 상태에서 완전한 구성 자료를 제공하는지 확인하지 못했다. 검색 도구가 읽은 페이지에는 `As of Aug 31, 2026` 문구가 있었지만 캐시 화면의 표시라 현재 응답의 기준일로 간주하지 않는다.
- S&P DJI의 [API 데이터 안내](https://www.spglobal.com/spdji/en/landing/topic/api-data-solutions/)는 지수 종가 데이터에 구성 종목 자료를 포함한다고 설명하고, 데이터 패키지를 구독형으로 안내한다. API 접근에는 S&P DJI Data Services 계정과 인증 토큰이 필요하다고 명시한다. 따라서 자동 수집에 쓸 수 있는 무료 공식 전체 구성 파일은 확인하지 못했다.
- 요청된 [iShares IVV 보유 종목 CSV](https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf/1467271812596.ajax?fileType=csv&fileName=IVV_holdings&dataType=fund)는 GET 시도에서 HTTP `000`으로 연결되지 않았다. 응답 형식, `Fund Holdings as of` 날짜, 주식 행 수는 모두 확인 불가다.
- 조사 도구의 네트워크 제약 때문에 IVV 대용 출처가 무료 공개되고 예상 행 수를 충족하는지 입증하지 못했다. 지시된 출처 조사 관문에 따라 구현을 보류하고, 이 조사 기록만 커밋한다.

## 2. 구현 보류

- [ ] IVV CSV 파서와 S&P 500 시장 보고서 대용 구성 흐름을 구현한다.
- [ ] Wikipedia 대체 경로, 보고서 evidence 및 Markdown 구성 기준일을 검증한다.
- [ ] 관련 테스트, 전체 테스트, Ruff, OpenSpec strict 검증을 실행한다.
