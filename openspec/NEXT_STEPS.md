# 후속 작업 목록

최종 갱신: 2026-11-13

## 현재 상태

- 시장 보고서 보강을 Orca Worker로 나눠 병합·아카이브했다: 무역가중 달러 지수, SPY 보유 종목 시장 폭과 구성 기준일, Census·BLS 발표 시각, SEC 8-K Item 2.02 실적 공시 확인, "해당 없음"(`none_found`) 상태 구분. DXY 심볼 변환 버그와 Russell 2000 HTML 응답 오류 문구도 고쳤다.
- 현재 진행 중인 OpenSpec 변경안은 `2026-11-13-polymarket-network-verification` 하나다. E3 집 네트워크 검증만 환경 접근이 불가능해 열려 있다.
- 최근 검증: pytest 1,829 passed, 1 skipped, 103 subtests; Ruff 통과; OpenSpec strict 17개 통과.
- 실제 공개 자료 `market-report --no-llm`(2026-11-12 보고): "수집 범위 내 보고서". DXY 103.20, 11-13 PPI 08:30(BLS) 표시. 주간 실업수당 발표 시각 미수집은 머리말 고정 안내로 옮겨 품질 경고에서 뺐다.
- 통합 테스트 후속 수정(2026-11-13): `discover` 단독 구간 실패 시 원인 문구를 표시하고, 매일 날짜가 잡히는 FRED 'FOMC Press Release'(일간 목표금리 시계열)를 다음 거래일 일정에서 뺐다.
- 결정 기록(2026-11-13): Russell 2000은 무료 대체 출처가 없어 실패 표시를 유지한다. 실적 공시 표본은 7개를 유지한다.

## 우선순위

| 우선순위 | 후속 작업 | 근거 | 규모 | 사용자 결정 |
| --- | --- | --- | --- | --- |
| 1 | Russell 2000 출처 재확인 | iShares IWM AJAX가 CSV 대신 HTML을 반환한다(Vanguard·SSGA·FTSE Russell 무료 대체 없음). iShares 응답이 복구되는지 주기적으로 확인한다. | 작음 | 유료 출처는 범위 밖 |
| 2 | Worker 환경 | Orca 저장소 setup 스크립트가 비어 있어 워크트리에 `.venv`가 없고(앱 설정에서만 변경 가능), Codex 샌드박스에는 네트워크·npm 캐시가 없다. 현재 우회 절차는 `openspec-change` 스킬 7절에 기록했다. | 작음 | 앱 설정·샌드박스 정책 변경 여부 |
| 3 | FRED 선별 목록의 미일치 이름 | 2026-11-13 확인: `FRED_US_RELEASES` 중 beige book, durable goods, fomc meeting minutes, industrial production and capacity utilization, new home sales는 FRED 발표명과 일치하지 않아 한 번도 선별되지 않는다. 실제 FRED 발표명으로 고칠지, 기관 공식 일정(Fed·Census)에 맡기고 뺄지 정리 필요. durable goods·new home sales는 Census 일정으로 수집되는 것을 확인했고, beige book·fomc meeting minutes·industrial production이 Fed 공식 일정 경로에 잡히는지는 미확인이다. | 작음 | 불필요 |
| 대기 | E3 집 네트워크에서 Polymarket 공개 GET 검증 | 활성 변경안의 마지막 미완료 작업. 집 네트워크 접근 불가. | 작음 | 환경이 가능해진 뒤 실행 필요 |
| 대기 | 시장 발굴 실제 실행 시간 계측 | 종목 발굴 재사용 평가는 합성 자료 기준이다. | 중간 | 공개 시세 접근 환경에서 측정 |

## 다음 시작점

남은 코드 작업은 FRED 선별 목록의 미일치 이름 정리(작음)뿐이다. iShares 응답 복구 여부를 주기적으로 확인하고, Worker 환경 설정 변경 여부를 결정한다. 기능 변경은 OpenSpec 변경안과 검증 기준을 먼저 작성한다.
