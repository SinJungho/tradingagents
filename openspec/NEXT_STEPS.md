# 후속 작업 목록

최종 갱신: 2026-11-13 (저녁)

## 현재 상태

- 브랜치 `work/local-improvements`: fork(`SinJungho/tradingagents`)에 푸시했고 fork `main` 대상 PR #1(69커밋)이 열려 있다. 그 뒤 로컬 커밋(가격 이력 병렬 조회와 문서)은 아직 푸시하지 않았다.
- 진행 중인 OpenSpec 변경안은 `2026-11-13-polymarket-network-verification` 하나이며 E3 집 네트워크 검증만 남았다.
- 최근 검증: pytest 1,831 passed, 1 skipped, 103 subtests; Ruff 통과; OpenSpec strict 17개 통과.
- 시장 보고서: 무역가중 달러 지수, SPY 보유 종목 시장 폭과 구성 기준일, BLS·Census·BEA·Fed 발표 시각, SEC 8-K Item 2.02 실적 확인, "해당 없음"(`none_found`) 상태, 수집 범위 고정 안내, DXY 심볼·FRED 선별 발표명 수정. 실제 `market-report --no-llm`(2026-11-12) 결과 "수집 범위 내 보고서".
- 종목 발굴: 가격·분할 이력 병렬 조회(작업 8개). 실제 `discover --universe sp500`(503종목)이 첫 실행 718초에서 가격을 새로 받는 조건 89초로 줄었고 신호 출력은 같다. 구간 실패는 원인 문구를 표시한다.
- 결정 기록(2026-11-13): Russell 2000은 무료 대체 출처가 없어 실패 표시를 유지한다. 실적 공시 표본은 7개를 유지한다. Codex 샌드박스 외부 네트워크는 열지 않고 코디네이터가 출처를 확인한다.

## 우선순위

| 우선순위 | 후속 작업 | 근거 | 규모 | 사용자 결정 |
| --- | --- | --- | --- | --- |
| 1 | 로컬 커밋 푸시 | 원격보다 앞선 로컬 커밋이 있다. 푸시하면 열린 PR #1에 포함된다. | 작음 | 푸시 여부 |
| 2 | SEC 조회 속도 제한과 병렬화 | SEC 디스크 캐시(24시간)가 없는 첫 실행에서 SEC 단계가 순차 약 200초로 가장 큰 남은 단계다(2026-11-13 실측). `sec_edgar.py`에 요청 속도 제한이 없어 SEC 권장(초당 10회 이하)을 지키는 공용 제한기를 먼저 둬야 병렬화할 수 있다. | 중간 | 불필요 |
| 3 | 실제 LLM 보고서 재평가 | 마지막 품질 평가(`results/market-reports/2026-11-12-02bdca35497f438f9f0e8a167de58247/quality-review.md`)는 "해당 없음" 상태, SEC 8-K, 발표 시각, SPY 시장 폭 도입 전 결과다. 서술이 새 근거를 정확히 인용하고 "해당 없음"을 결측으로 오해하지 않는지 확인한다. | 중간 | 실제 LLM 호출 승인 |
| 4 | `results/` 관리 | 보고서·측정 산출물이 추적되지 않은 채 남는다. 아카이브 README가 참조하는 품질 평가 기록을 커밋할지 정한 뒤 `.gitignore`에 추가한다. | 작음 | 품질 평가 기록 커밋 여부 |
| 5 | Worker 환경 설정 | Orca 저장소 setup 스크립트에 `uv venv -q .venv && uv pip install -q --python .venv/bin/python -e '.[dev]'`를 넣으면 워크트리별 venv가 생긴다(임시 워크트리에서 약 2초·전체 pytest 통과 확인). Orca 앱 설정에서만 바꿀 수 있다. 샌드박스 OpenSpec 실행법은 `openspec-change` 스킬 7절에 있다. | 작음 | Orca 앱 설정 반영 여부 |
| 주기 확인 | Russell 2000 출처 | iShares IWM AJAX가 CSV 대신 HTML을 반환한다(2026-11-13 저녁 재확인도 동일). Vanguard·SSGA·FTSE Russell 무료 대체 없음. | 작음 | 유료 출처는 범위 밖 |
| 대기 | E3 집 네트워크 Polymarket 공개 GET 검증 | 활성 변경안의 마지막 미완료 작업. 집 네트워크 접근 불가. | 작음 | 환경이 가능해진 뒤 실행 |

## 다음 시작점

로컬 커밋 푸시 여부를 정한 뒤, 결정 없이 진행할 수 있는 SEC 공용 요청 속도 제한과 병렬화를 OpenSpec 변경안부터 시작한다. 실제 LLM 재평가와 `results/` 관리는 사용자 결정 후 진행한다.
