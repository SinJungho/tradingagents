# Polymarket 환경별 연결 검증

## Why

별칭 기본 경로의 현재 환경 결과와 집 네트워크 결과를 구분해야 한다.

## What Changes

공개 GET의 상태·JSON 파싱·시각을 환경별로 기록하고 명시적 경로 선택 절차를 보존한다.

## Out of Scope

IP 자동 분기, 숨은 경로 전환, TLS 검증 해제, 리다이렉트 허용.
