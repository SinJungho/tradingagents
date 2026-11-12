# Tasks

- [x] 1. MVP 범위 확정: 사용자 제공 미국 주식 티커 최대 10개, 현재 데이터, 기존 네 스타일 점수, 입력 순서 유지, 부분 결과와 출처·날짜·실패·건수 표시, LLM 후속 분석 없음.
- [x] 2. 기존 점수기와 데이터 공급자 헬퍼를 재사용하는 호출 가능한 `discover_stocks(tickers)` API를 구현한다. 입력을 공급자 호출 전에 검증하고 티커별 공급자 오류를 격리한다.
- [x] 3. `tradingagents discover --tickers NVDA,AAPL` CLI 명령과 입력 순서를 보존하는 팩터별 결과 출력을 구현한다.
- [x] 4. 합성 시계열·재무 자료와 패치된 공급자를 사용하는 집중 테스트를 추가한다. 결측 팩터의 `ABSTAIN`, 부분 결과, 잘못된 입력의 사전 거부, 티커별 실패 및 출력 건수를 검증한다.
- [x] 5. `./.venv/bin/python -m pytest -q`, `./.venv/bin/ruff check .`, `./.venv/bin/tradingagents --help`와 변경 strict validation을 실행하고 결과에 맞게 작업 상태를 갱신한다.
- [x] 6. 필수 검증 통과 후 변경을 아카이브하고 `npx --offline @fission-ai/openspec validate --specs --strict`로 아카이브된 스펙을 검증한다.
