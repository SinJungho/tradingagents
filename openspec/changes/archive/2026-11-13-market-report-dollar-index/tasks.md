# 작업 항목

## 1. 출처 확인과 명세

- [x] FRED `DTWEXBGS` 공개 페이지에 API 키 없이 GET 요청을 보내 상태·콘텐츠 형식·관측일·갱신일·다음 발표일 필드를 확인한다.
- [x] FRED 시계열 메타데이터와 Federal Reserve H.10 발표 주기를 확인하고, 관측 빈도와 공개 주기를 구분한다.
- [x] `거시경제와 시장 변수` 요구사항을 수정하고 DXY와 무역가중 지표의 독립 표시 시나리오를 추가한다.

조사 기록:

| URL | 상태·형식 | 확인 내용 |
| --- | --- | --- |
| https://fred.stlouisfed.org/series/DTWEXBGS | GET 200, `text/html; charset=UTF-8` | 관측일·갱신 시각·다음 발표일 필드 존재; 페이지상 일별 관측, 최신 관측 2026-11-06, 갱신 2026-11-09 3:16 PM CST, 다음 발표 2026-11-16 |
| https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTWEXBGS | 코디네이터 확인 2026-11-13: GET 200, `application/csv` | 최신 관측일·값 2026-11-06·121.8803 |
| https://www.federalreserve.gov/releases/h10/ | 워크스페이스 직접 GET 403, `text/plain; charset=UTF-8`; 공식 페이지 내용은 브라우저 조회로 확인 | 페이지 갱신일 2026-11-09; 직전 영업 주 일별 지수를 월요일 오후 4:15에 공개하며 월요일이 연방 공휴일이면 다음 영업일에 공개 |

조회일 기준 관측 지연은 7일이며, FRED 일별 빈도의 기존 `max_age=10`일 판정 안에 든다.

## 2. 구현과 검증

- [x] 기존 `macro()` 경로에 `DTWEXBGS`를 추가한다.
- [x] 합성 응답으로 값·단위·빈티지, DXY 실패 시 독립 표시, 라벨 분리, 주간 발표 지연과 `max_age` 판정을 확인한다.
- [x] 관련 테스트, 전체 pytest, Ruff 및 CLI 도움말을 실행한다.
- [ ] OpenSpec strict 검증을 실행한다. 오프라인 npm 캐시에 패키지가 없어 `샌드박스 미실행`; 코디네이터가 병합 때 실행한다.
- [x] 변경안을 아카이브하지 않고 한국어 커밋 메시지로 커밋한다.

검증 기록: 관련 테스트 31개 통과, 전체 pytest 1789개 통과·2개 건너뜀, Ruff 및 CLI 도움말 통과.
