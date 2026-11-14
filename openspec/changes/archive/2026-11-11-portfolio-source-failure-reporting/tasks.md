# Tasks

- [x] 1. 선택 자료 실패 기록
  - [x] 1.1 `dataflows/errors.py`에 실행 단위 실패 기록·회수 함수 추가
  - [x] 1.2 라우터의 선택 자료 대체·공급자 전체 불가 경로와 Polymarket 네트워크 실패에서 기록
  - [x] 1.3 `portfolio live`가 시나리오 단계의 기록을 `source_failures`에 메서드·범주·횟수로 추가
- [x] 2. 미분류 오류 유형 표시
  - [x] 2.1 `format_api_failure`가 `unknown` 범주에 예외 클래스 이름만 덧붙이도록 변경
- [x] 3. 검증
  - [x] 3.1 합성 예외로 기록·중복 집계·비밀 미노출·시나리오 실패 시 보존 테스트
  - [x] 3.2 집중 테스트, 전체 pytest, Ruff, CLI 도움말
