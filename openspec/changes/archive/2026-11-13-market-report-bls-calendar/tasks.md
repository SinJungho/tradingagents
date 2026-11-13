# 작업

## 1. 출처 확인

- [x] 코디네이터 확인(2026-11-13, 실제 네트워크)을 근거로 기록한다. 워커는 외부 네트워크를 호출하지 않았다.

| 기관 | URL | HTTP 상태 | 형식 | 비고 |
| --- | --- | --- | --- | --- |
| BLS 일정 ICS | https://www.bls.gov/schedule/news_release/bls.ics | 연락처 없는 User-Agent 403, 연락처 User-Agent 200 | ICS, `TZID=US-Eastern`, 이벤트 313개(2025~2026) | `DTSTART;TZID=US-Eastern:YYYYMMDDTHHMMSS`, CRLF·줄 접기 가능 |
| DOL ETA 보도자료 | https://www.dol.gov/newsroom/releases/eta | 연락처 User-Agent로도 403 | HTML, 본문 접근 불가 | 주간 실업수당 시각 미확인 |

## 2. 요구사항

- [x] `다음 거래일 미국 발표 일정 선별`을 MODIFIED로 고쳐 BLS ICS 시각, FRED 이름 병합, BLS 없음·실패 상태, DOL 미수집을 시나리오로 나눈다.

## 3. 구현 및 테스트

- [x] `PublicMarketData.bls_calendar(day)`를 추가한다. SEC `_user_agent()`를 재사용하고 stdlib로 ICS를 파싱하며 선별 발표만 남긴다.
- [x] 다음 거래일 공식 일정 병합에 BLS를 추가하고, 없음은 `none_found`, 조회 실패는 `unavailable`로 표시한다.
- [x] 'BLS·DOL 공식 일정' 미수집 항목을 'DOL 주간 실업수당 일정'으로 바꾼다.
- [x] 합성 ICS로 동부시간 변환·서머타임 경계, 줄 접기, 선별 외 제외, FRED 이름 매칭, 403 실패, 일정 없음 상태를 테스트한다.
- [x] 관련 테스트: `tests/test_market_report.py` 63 passed.
- [x] 전체 테스트: 1826 passed, 2 skipped, 103 subtests passed.
- [x] Ruff: `ruff check .` 통과.
- [x] CLI: `tradingagents --help` 통과.
- [x] OpenSpec strict 검증 통과.
