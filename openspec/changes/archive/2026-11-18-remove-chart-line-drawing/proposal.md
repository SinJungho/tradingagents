# 차트 선 긋기 기능 제거

## Why
차트 분석과 선 긋기를 Yahoo Finance와 차트 MCP 연동으로 별도 구현했다. 이 저장소의 선 긋기 코드는 중복이므로 제거한다.

## What Changes
- 선 후보 생성(수평·추세·기준선·갭·피보나치), 장기 구조선, 피보나치 다중 스윙 분석, 앵커드 VWAP, 지지·저항 경계와 조건부 시나리오, 차트의 선 표시·선 색, 126세션 구조 차트를 제거한다.
- 선 후보를 채점·토론하던 기존 `chart-eval` 실험(runner·scoring·discussion·artifacts, CLI `chart-eval`)과 그 OpenSpec 변경안 `chart-eval-prevalidation`을 제거한다. 이 실험은 2026-11-16 실제 실행(가격 사건 26,759건 채점, LLM 토론 81회)을 마쳤으나 비교 규칙을 사전에 고정하지 못해 우열을 계산하지 못한 채 종료한다.
- `technical-backtest` 명령과 `technical-report-backtest` 기능을 제거한다.
- 유지: Toss 일봉 수집(`--max-history`), 월봉·연봉 집계, 기준 단절 표시, 지표 계산, 캔들 차트, 판단 요약 페이지(결론, 핵심 수치, 주기별 추세, 다음 확인 시점, 자료 한계), `technical-latest`.
- 12개 순위 분석 중 선 관련 3개(피보나치, 수평 지지·저항, Anchored VWAP)를 제거해 9개로 줄인다.
- 복구용 백업: `results/_backup-line-drawing-removed-2026-11-18.tgz`(git 추적 대상 아님).

## Out of Scope
`results/` 산출물 삭제, `tradingagents backtest`·그래프·에이전트 변경, 선 긋기 외부 구현.
