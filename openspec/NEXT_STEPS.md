# 후속 작업 목록

최종 갱신: 2026-11-14

## 현재 상태

- 브랜치 `work/local-improvements`를 fork(`SinJungho/tradingagents`)에 푸시했고 fork `main` 대상 PR #1이 열려 있다.
- 진행 중인 OpenSpec 변경안은 `2026-11-13-polymarket-network-verification` 하나이며 E3 집 네트워크 검증만 남았다.
- 최근 검증: pytest 1,840 passed, 1 skipped, 103 subtests; Ruff 통과; OpenSpec strict 17개 통과.
- 시장 보고서: 실제 LLM 재평가(Red 64, Blue 78; 이전 52, 73)의 지적을 고쳤다. 뉴스 50건 조회와 공급자 한도 표시, 금리 관측일 불일치 비고, DXY(ICE DXY) 라벨, 핵심 요약의 최대 변동 포함, 지수 이름 숫자의 해석 검사 제외. 기록: `results/market-reports/2026-11-12-a80efcde3994475289e8c78f4777e5ea/quality-review.md`.
- 재평가 후속(2026-11-13): 다음 정규장 개장 이후 생성 시 머리말 주의, DXY·WTI·금의 직전 거래일 대비 변화율, ETF 보유 변동·애널리스트 의견 틀 헤드라인 제외(제목은 요약 항목에 보존)와 기사 표 렌더링. 실제 실행에서 보고서가 2,292줄에서 1,124줄로 줄었다.
- 종목 발굴: 가격·SEC·분할 병렬 조회(작업 8개, SEC 초당 8회 공용 제한). 캐시가 빈 `discover --universe sp500`(503종목) 첫 실행이 718초에서 142초로 줄었고 신호 출력은 같다.
- 운영: `orca.yaml` setup이 워크트리마다 `.venv`를 만든다(시험 워크트리로 확인). `results/`는 품질 평가 기록만 추적한다.
- 결정 기록(2026-11-13): Russell 2000은 무료 대체 출처가 없어 실패 표시를 유지한다. 실적 공시 표본은 7개를 유지한다. Codex 샌드박스 외부 네트워크는 열지 않고 코디네이터가 출처를 확인한다.

## 사용자 작업

에이전트가 대신할 수 없거나 사용자 결정·환경이 필요한 일이다. 2026-11-14 기준.

| 순서 | 작업 | 이유와 방법 | 규모 |
| --- | --- | --- | --- |
| 1 | PR #1 검토·병합 | fork `main` 대상 PR #1(84커밋, 2026-11-14 확인 시 충돌 없음)이 열려 있다. https://github.com/SinJungho/tradingagents/pull/1 | 중간 |
| 2 | `SEC_EDGAR_USER_AGENT`에 실제 연락처 설정 | SEC·BLS 요청은 연락처가 든 User-Agent를 요구한다. 설정이 없으면 자리표시자 `contact@example.com`을 보낸다. `.env`에 `SEC_EDGAR_USER_AGENT="이름 이메일"` 형식으로 직접 넣는다(에이전트는 `.env`를 열람하지 않는다). | 작음 |
| 3 | Orca에서 `orca.yaml` setup 승인 | Orca는 setup 내용이 바뀌면 승인 전까지 건너뛴다. 다음 워크트리 생성 때 승인하거나 `--setup run`을 쓴다. | 작음 |
| 4 | 집 네트워크에서 E3 검증 요청 | 집 네트워크에 연결된 상태에서 에이전트에게 E3 진행을 요청한다. 에이전트가 `tradingagents doctor`와 Polymarket 공개 검색 GET(별칭·direct)을 실행해 상태·파싱·시각을 기록하고 변경안을 마무리한다. | 작음 |
| 5 | Russell 2000 출처 재확인 요청(가끔) | iShares IWM 보유 종목이 CSV로 돌아왔는지 에이전트에게 확인을 요청한다. 복구 전까지 `discover --universe russell2000`은 실패한다. | 작음 |

## 우선순위

| 우선순위 | 후속 작업 | 근거 | 규모 | 사용자 결정 |
| --- | --- | --- | --- | --- |
| 주기 확인 | Russell 2000 출처 | iShares IWM AJAX가 CSV 대신 HTML을 반환한다(2026-11-13 저녁 재확인도 동일). Vanguard·SSGA·FTSE Russell 무료 대체 없음. | 작음 | 유료 출처는 범위 밖 |
| 대기 | E3 집 네트워크 Polymarket 공개 GET 검증 | 활성 변경안의 마지막 미완료 작업. 집 네트워크 접근 불가. | 작음 | 환경이 가능해진 뒤 실행 |

## 다음 시작점

결정 없이 진행할 코드 작업은 남지 않았다. Russell 2000 출처는 주기적으로 재확인하고, E3는 집 네트워크 접근이 가능해지면 재개한다. 새 기능 변경은 OpenSpec 변경안과 검증 기준을 먼저 작성한다.
