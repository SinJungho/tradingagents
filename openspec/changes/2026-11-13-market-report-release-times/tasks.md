# 작업

## 1. 공식 일정 출처 접근성 조사

- [x] `get_with_retry`와 같은 기본 requests 헤더로 공개 공식 URL에 GET 요청을 보냈다. 저장소 헬퍼는 사용자 지정 헤더를 보내지 않으며, 브라우저 위장이나 접근 제한 우회는 사용하지 않았다.
- [x] 이 실행 환경에서는 대상 호스트가 DNS 단계에서 연결되지 않아 HTTP 상태, 응답 형식, 일정 기준일, 발표 시각을 확인할 수 없었다. 따라서 일반 requests User-Agent 차단 여부와 이전 점검에서 언급된 BLS 403도 이번 조사 결과로 재확인하지 못했다.

| 기관 | URL | HTTP 상태 | 형식 | 기준일 / 시각 포함 |
| --- | --- | --- | --- | --- |
| BLS 일정 ICS | https://www.bls.gov/schedule/news_release/bls.ics | 확인 불가 (DNS 연결 오류, HTTP 응답 없음) | ICS 예상, 응답 확인 불가 | 날짜·시각 모두 확인 불가 |
| BLS 일정 HTML | https://www.bls.gov/schedule/news_release/ | 확인 불가 (DNS 연결 오류, HTTP 응답 없음) | HTML 예상, 응답 확인 불가 | 날짜·시각 모두 확인 불가 |
| Census 경제지표 | https://www.census.gov/economic-indicators/ | 확인 불가 (DNS 연결 오류, HTTP 응답 없음) | HTML 예상, 응답 확인 불가 | 날짜·시각 모두 확인 불가 |
| Census 경제지표 달력 | https://www.census.gov/economic-indicators/calendar-listview.html | 확인 불가 (DNS 연결 오류, HTTP 응답 없음) | HTML 예상, 응답 확인 불가 | 날짜·시각 모두 확인 불가 |
| DOL 주간 실업수당 청구 | https://oui.doleta.gov/unemploy/claims.asp | 확인 불가 (DNS 연결 오류, HTTP 응답 없음) | HTML 예상, 응답 확인 불가 | 날짜·시각 모두 확인 불가 |
| DOL 보도자료 목록 | https://www.dol.gov/newsroom/releases | 확인 불가 (DNS 연결 오류, HTTP 응답 없음) | HTML 예상, 응답 확인 불가 | 날짜·시각 모두 확인 불가 |

## 2. 요구사항

- [x] `다음 거래일 미국 발표 일정 선별`을 MODIFIED로 작성하고 공식 시각만 사용, FRED 중복 통합, 기관 일정 미확인 사유 표시를 명시한다.

## 3. 구현 및 검증

- [ ] BLS·Census·DOL 모두 접근성을 확인하지 못해 조사 관문에 따라 구현을 보류한다. 소스 코드와 테스트는 변경하지 않는다.
- [ ] 합성 ICS/HTML 파싱, 서머타임 변환, 403 결측, FRED·기관 일정 중복 제거 테스트는 구현 재개 시 수행한다.
- [ ] OpenSpec strict 검증: `npx --offline @fission-ai/openspec validate 2026-11-13-market-report-release-times --strict`가 오프라인 npm 캐시에 패키지가 없어 실행되지 않았다(ENOTCACHED). 사용자가 지정한 오프라인 조건을 유지했다.
