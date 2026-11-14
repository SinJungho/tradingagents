# 작업

## 1. 공식 일정 출처 접근성 조사

- [x] 코디네이터 확인(2026-11-13) 결과를 반영한다. 워커 샌드박스는 네트워크가 없어 이전 GET 시도에서 DNS 오류가 났으며, 출처 상태는 아래 코디네이터의 네트워크 확인 결과를 사용한다.
- [x] 출처 접근 제한을 브라우저 위장 등으로 우회하지 않는다. 403 원인이 User-Agent 차단인지는 별도 확인되지 않았다.

| 기관 | URL | HTTP 상태 | 형식 | 기준일 / 시각 포함 |
| --- | --- | --- | --- | --- |
| BLS 일정 ICS | https://www.bls.gov/schedule/news_release/bls.ics | 403 | ICS URL, 본문 접근 불가 | 기준일·시각 확인 불가; 사용 불가 |
| BLS 일정 HTML | https://www.bls.gov/schedule/2026_sched.htm | 403 | HTML, 본문 접근 불가 | 기준일·시각 확인 불가; 사용 불가 |
| Census 2026 연간 달력 | https://www.census.gov/economic-indicators/calendar-listview-2026.html | 200 | text/html, `table#calendar`, 178행 | 2026-01-07~2026-12-28; 날짜와 시각 포함, `sorttable_customkey`는 `YYYYMMDDHHMM` 동부 현지 시각 |
| Census 연도 없는 달력 | https://www.census.gov/economic-indicators/calendar-listview.html | 상태 미기록 | HTML | 확인 당시 다음 해(2027)만 표시; 대상일 연도 URL을 사용 |
| DOL ETA 보도자료 | https://www.dol.gov/newsroom/releases/eta | 403 | HTML, 본문 접근 불가 | 기준일·시각 확인 불가; 사용 불가 |
| DOL 주간 UI 자료 | https://www.dol.gov/ui/data.pdf | 200 | PDF 주간 보고서 | 일정과 발표 시각 없음; 사용 불가 |

## 2. 요구사항

- [x] `다음 거래일 미국 발표 일정 선별`을 MODIFIED로 작성하고 공식 시각만 사용, FRED 중복 통합, 기관 일정 미확인 사유 표시를 명시한다.

## 3. 구현 및 테스트

- [x] Census 연간 달력만 구현한다. 요청일의 연도별 달력에서 선별 지표를 읽고 원본의 동부 현지 시각을 시간대로 변환한다.
- [x] FRED와 Census의 발표명이 일치하면 하나의 항목으로 합치고 양쪽 출처를 보존한다. BLS와 DOL은 확인된 일정 공백 사유를 표시한다.
- [x] 합성 HTML 파싱, 서머타임 경계, Census HTTP 오류 결측, FRED·Census 일정 중복 제거를 집중 테스트한다.
- [x] 관련 테스트: `tests/test_market_report.py` 33 passed.
- [x] 전체 테스트: 1791 passed, 2 skipped, 103 subtests passed. 샌드박스의 loopback 바인딩 제한으로 첫 실행의 인증 테스트 7개가 실패했으나, 허용된 loopback 환경에서 재실행해 전체 통과를 확인했다.
- [x] Ruff: `ruff check .` 통과.
- [x] CLI: `tradingagents --help` 통과.
- [ ] OpenSpec strict 검증: 샌드박스 미실행(오프라인 npm 캐시 ENOTCACHED); 코디네이터가 병합 때 검증한다.
