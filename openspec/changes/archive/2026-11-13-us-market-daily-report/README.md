# 작업 시작 기준

기준 커밋: 623a5b1. 시작 시 13개 tracked 파일 변경(897 추가/38 삭제)과 시장 발굴·Polymarket 아카이브, Yahoo screener 및 이 변경안이 이미 존재했다. 기존 변경은 보존한다. 커밋하지 않는다. 이전 검증 결과는 이번 작업의 검증으로 간주하지 않는다.

## 공개 출처와 제한

- Yahoo/yfinance: 지수·ETF 일별 Close와 Adj Close, 종목별 뉴스·실적 일정·장후 5분 봉. 무료 공개 접근, 지연/제한/빈 응답 가능. 일별 종가는 비수정, 수익률·시장 폭은 수정 종가; 5분 봉은 비수정. 선물 연속물은 롤 효과가 있어 주가지수와 다르다. https://ranaroussi.github.io/yfinance/reference/api/yfinance.Ticker.history.html
- NYSE 거래일은 exchange_calendars XNYS 사용. 정규장 실제 폐장과 보고서 20시 경계는 별개. https://www.nyse.com/markets/hours-calendars
- S&P 500 구성은 기존 Wikipedia 2차 출처, 현재 구성의 표본이며 과거 구성 복원 아님.
- FRED: 무료 키 필요. 빈티지 날짜를 고정하고 관측일/빈도/단위를 보존한다. 날짜 단위 빈티지는 발표 시각을 보장하지 않아 당일 빈티지는 전일까지 보수적으로 제한한다. https://fred.stlouisfed.org/docs/api/fred/series_observations.html
- FRED 공개 발표 일정은 releases/dates의 include_release_dates_with_no_data 사용. 정확한 시각·당시 알려진 일정의 빈티지는 보장되지 않으며 조회 시점의 예정 정보로 별도 표시한다. https://fred.stlouisfed.org/docs/api/fred/releases_dates.html
- 기업 실적과 장후 반응은 고정 대형주 표본만 조회한다. Yahoo의 현재 응답에서 발표 당시 값/가이던스의 공개 시각을 검증할 수 없으면 수치 근거로 쓰지 않는다. 기업 IR 링크·뉴스만 확인된 범위에서 연결한다. 전체 시장 순위가 아니다.
- 경제·실적 일정은 조회 당시 예정 정보이며 확정 전망이 아니다. 정책 일정·가이던스의 검증 가능한 구조화 자료가 없으면 확인 불가로 남긴다.

## 별도 미실행 평가

실LLM 품질 평가는 실제 보고서 생성 요청 시 수행한다. 집 네트워크 검증은 해당 환경 접근이 없어 미완료다.

## 추가 출처 확인

- Fed 공식 월별 일정 페이지에서 행사·일자·동부시간을 파싱한다. 월별 링크는 공식 색인에서 선택하며 마크업 변경·시각 미확인·일정 미확인을 분리한다. 조회 시점 일정으로 표시하며 과거 공지 시점을 주장하지 않는다. https://www.federalreserve.gov/newsevents/calendar.htm
- BLS 직접 iCalendar는 현재 환경에서 HTTP 403. FRED 일정의 제공 범위와 Fed 공식 일정으로 보완하지만 BLS 전체 제공을 주장하지 않는다. https://www.bls.gov/schedule/news_release/bls.ics
- 기업 가이던스·실적 발표 당시 숫자의 완전한 무료 구조화 피드는 확보하지 못했다. Yahoo의 현재 EPS나 예상치를 과거 발표 당시 값으로 간주하지 않고 명시적 공백으로 보존한다. 현재 기업 표본은 7개 대형주이며 전체 실적 발표 기업 목록이 아니다.

## 공개 자료 점검

2026-11-13T02:05:05.544297+00:00 기준 Yahoo S&P 500 일별 299행·ES 장중/장후 238행·뉴스 12건 응답을 확인했다. FRED DGS10 관측·메타데이터와 다음 거래일 일정 37건 응답을 확인했다(일정에는 미국 외 발표도 포함). 전체 시장 수집이나 실제 LLM 보고서 품질 평가로 간주하지 않는다.

2026-11-13T02:13:37.182913+00:00 기준 공식 Fed 11월 페이지에서 다음 거래일 행사 2건과 시각 2건을 확인했다. 응답 원문과 인증정보는 보존하지 않았다.

## 검증기

hook의 `npx --offline @fission-ai/openspec validate <change> --strict`와 같은 패키지·명령을 사용한다. 최초 기본 npm 캐시는 ENOTCACHED였고 샌드박스 DNS도 실패했다. `/tmp/market-report-npm` 캐시에 패키지를 설치한 뒤 `npm_config_cache=/tmp/market-report-npm`을 지정해 동일 strict 검증을 수행했다. 이는 문서 검증 실패와 별개다. 문서 검사에서 발견한 하네스 시나리오 누락은 기존 시나리오를 보존해 수정했다.

## 후속 실제 평가

- [x] 실제 LLM 보고서 생성과 Red/Blue Team 독립 품질 평가 완료. 결과는 `results/market-reports/2026-11-12-02bdca35497f438f9f0e8a167de58247/quality-review.md`에 기록했다.
- [ ] 집 네트워크 Polymarket 검증. 별도 활성 변경안 `2026-11-13-polymarket-network-verification`에서 관리한다.

## 최종 자동 검증

집중 테스트 147 passed. 전체 pytest 1784 passed, 1 skipped, 24 warnings, 103 subtests passed (24.39초). skip은 선택 의존성 langchain_aws 미설치. Ruff 전체 통과, 설치된 CLI 도움말 확인, OpenSpec strict 변경안 검증 통과.

최초 전체 실행의 7개 인증 테스트 실패는 샌드박스 loopback 바인딩 제한이었으며 가짜 서버만 허용한 재실행으로 통과했다. 신규 공급자 모듈의 계층 검사 실패는 dataflows로 이동해 해결했다. 실브로커·실LLM 호출 및 커밋은 하지 않았다.

아카이브 후 최종 명세 strict 검증: 16 passed, 0 failed. 이후 종료 hook용 기본 npm 캐시에도 동일 검증기를 준비했다. 활성 변경안은 집 네트워크 검증 미완료 1건만 남겼다.

기본 캐시의 동일 offline strict 명령은 캐시 접근을 허용한 실행에서 통과했다. 샌드박스 안의 기본 캐시 접근은 여전히 ENOTCACHED로 표시되므로, 샌드박스 검증에는 위 /tmp 캐시를 사용한다. 문서 strict 검증과 캐시 접근 제한은 별개다.
