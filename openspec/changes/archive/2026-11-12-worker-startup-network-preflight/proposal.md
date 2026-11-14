# 워커 시작 시 API 네트워크 사전 진단

## Why

Orca 워커가 시작된 뒤 사용자가 직접 진단 명령을 입력해야 네트워크 차단을 발견한다. 새 Codex 세션 시작 훅에서 현재 워커의 비인증 API 진단을 실행하면 최초 요청 전에 실패 계층과 실행 호스트 정책 조치를 알려줄 수 있다.

## What Changes

- Codex `SessionStart`의 새 세션 시작 시 현재 워커에서 `tradingagents doctor`를 자동 실행한다.
- 연결 실패가 있으면 제한형 네트워크 정책 JSON과 실행 호스트 적용 경로를 추가 컨텍스트로 제공한다.
- CLI가 아직 준비되지 않은 경우 세션을 막지 않고 진단 생략 이유를 표시한다.

## Out of Scope

- Orca 실행 호스트의 DNS·방화벽 정책을 hook이 직접 변경하는 것
- resume, compact, fork마다 반복 진단하는 것
- 실계좌 또는 실제 LLM 요청을 사전 진단에서 호출하는 것
