# Tratto 브라우저 쓰기 경계

## Why

MCP 훅만 검사하면 에이전트가 차트 캔버스를 좌표 클릭해 Tratto 쓰기 절차를 우회할 수 있다.

## What Changes

- 차트 드로잉 요청 중 CUA를 통한 캔버스 좌표 클릭·드래그를 차단한다.
- 탭 전환과 접근성 트리·화면 읽기는 허용한다.

## Out of Scope

- 사용자가 직접 조작하는 브라우저 입력
- Yahoo Finance 표시 기능 변경
