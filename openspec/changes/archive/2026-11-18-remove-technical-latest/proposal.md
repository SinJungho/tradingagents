# 최신 기술 분석 기능 제거

## Why
차트 분석과 드로잉은 Yahoo Finance + 차트 MCP 연동으로 별도 구현한다. Toss 일봉으로 지표·차트·보고서를 직접 계산하는 `chart_eval`과 `technical-latest` 명령은 더 이상 필요하지 않다.

## What Changes
- `tradingagents/chart_eval/`, `tradingagents technical-latest` 명령과 관련 테스트 9개를 제거한다.
- `latest-technical-analysis` capability의 모든 요구사항을 제거한다.
- `openspec/NEXT_STEPS.md`의 장기 기술 분석 항목을 갱신한다.

## Out of Scope
- 외부 차트 분석 결과를 가져오는 기능(별도 변경안).
- 이미 아카이브된 과거 변경안 기록.
