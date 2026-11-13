# 후속 작업 목록

최종 갱신: 2026-11-13

## 현재 상태

- 시장 보고서 자료 보강 4건을 Codex Worker로 구현해 병합·아카이브했다: 무역가중 달러 지수(`DTWEXBGS`), SPY 보유 종목 기반 시장 폭 표본과 구성 기준일, Census 경제 일정 발표 시각, SEC 8-K Item 2.02 실적 공시 확인과 Yahoo EPS 2차 출처.
- 현재 진행 중인 OpenSpec 변경안은 `2026-11-13-polymarket-network-verification` 하나다. E3 집 네트워크 검증만 환경 접근이 불가능해 열려 있다.
- 최근 검증: pytest 1,807 passed, 1 skipped, 103 subtests; Ruff 통과; OpenSpec strict 17개 통과.
- 실제 공개 자료 `market-report --no-llm`(2026-11-12 보고) 결과: 무역가중 달러 지수 2026-11-06 관측 표시, SPY 보유 종목 503개(기준일 2026-11-11)로 시장 폭 계산, 표본 7개 종목 대상일 8-K 2.02 없음 확인. 비가용·부분 항목 14건 때문에 "불완전 보고서"로 표시됐다.

## 우선순위

| 우선순위 | 후속 작업 | 근거 | 규모 | 사용자 결정 |
| --- | --- | --- | --- | --- |
| 1 | Russell 2000 발굴 출처 복구 | 2026-11-13 재현: `fetch_index_universe('russell2000')`가 `MarketUniverseError: Russell 2000 holdings are missing the Ticker/Name columns`로 실패. iShares IWM AJAX URL이 CSV 대신 상품 HTML을 반환한다. `discover --universe russell2000`와 이를 포함하는 선택이 영향받는다. | 중간 | 무료 공개 자료 우선 |
| 1 | 보고서 상태 규칙 정리 | `quality_warnings()`가 available 외 상태를 모두 경고로 센다. 정상 확인 결과 "없음"(실적 예정 7행, Census·BEA 일정 없음, 업종 뉴스 없음)과 신규 상장 종목의 이력 부족이 매일 경고가 된다. "조회 성공·결과 없음"과 "자료 결측"을 구분해야 한다. | 중간 | 불필요 |
| 2 | DXY 조회 실패 | 원인 확인: `PublicMarketData.ticker()`가 클래스 주식용으로 모든 `.`을 `-`로 바꿔 `DX-Y.NYB`를 `DX-Y-NYB`로 조회한다. provider 경로로 매번 HTTPError 재현. | 작음 | 불필요 |
| 3 | BLS·DOL 발표 시각 | BLS ICS·HTML 일정과 DOL 보도자료 페이지가 HTTP 403. CPI·고용·PPI·주간 실업수당 시각은 미확인(11-13 PPI 시각 없음). 우회 없는 다른 공개 경로 조사 필요. | 중간 | 우회 수단 없이 공개 경로만 |
| 3 | 실적 표본 확대 | 실적 공시 확인은 고정 7개 종목 표본이다. SPY 보유 비중 상위 종목으로 확대하면 SEC 조회 수가 늘어난다. | 중간 | 표본 크기 결정 필요 |
| 4 | Codex Worker 샌드박스 네트워크·npm 캐시 | Worker가 출처 확인과 `openspec validate`(ENOTCACHED)를 실행하지 못해 코디네이터가 대신 수행했다. | 작음 | 샌드박스 정책 조정 여부 |
| 4 | Worker 워크트리 Python 환경 | Orca 저장소 setup 스크립트가 비어 있어 워크트리에 `.venv`가 없다. 메인 venv 경로로 우회했다. | 작음 | 불필요 |
| 대기 | E3 집 네트워크에서 Polymarket 공개 GET 검증 | 활성 변경안의 마지막 미완료 작업. 집 네트워크 접근 불가. | 작음 | 환경이 가능해진 뒤 실행 필요 |
| 대기 | 시장 발굴 실제 실행 시간 계측 | 종목 발굴 재사용 평가는 합성 자료 기준이다. | 중간 | 공개 시세 접근 환경에서 측정 |

## 다음 시작점

Russell 2000 출처 복구와 보고서 상태 규칙 정리를 병렬로 진행한다. DXY 심볼 변환 버그도 독립적이라 함께 고친다. 각 기능 변경은 OpenSpec 변경안과 검증 기준을 먼저 작성한다.
