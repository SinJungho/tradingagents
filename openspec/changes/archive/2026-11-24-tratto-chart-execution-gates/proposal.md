# Tratto 차트 실행 게이트

## Why

차트 드로잉 지침과 검증기는 이미 있지만, 에이전트가 Tratto MCP 대신 브라우저 레이아웃을 직접 수정하거나 필수 증거 없이 완료로 보고해도 하네스가 막지 못한다.

## What Changes

- Codex와 Claude hook에 차트 드로잉 실행 게이트를 추가한다.
- Tratto 조회와 데이터 검증 전 드로잉 호출 및 Yahoo 레이아웃 직접 수정을 차단한다.
- 요청된 라벨과 `chart-drawings-check` 증거가 없으면 완료 보고를 보류한다.
- `tratto-chart` 스킬에 연결 실패 시 중단·미완료 보고 절차를 명시한다.

## Out of Scope

- Tratto MCP 서버 구현·설치
- Yahoo Finance 차트 도구 자체의 수정
