# 검증 기록

네트워크 정책 JSON은 LLM 공급자와 선택한 데이터 공급자 체인에서 사용하는 목적지만 내보내도록 좁혔다. 도구별 재정의가 범주 설정을 덮어쓰며, default는 도구의 모든 사용 가능한 공급자를 포함한다. 설정 없이 직접 호출되는 Reddit·StockTwits와 환경에서 설정된 Toss·TypeSafe 목적지는 포함한다. ChatGPT 플랜 인증을 선택한 경우에는 auth.openai.com도 포함한다. Doctor는 종전처럼 모든 지원 API의 도달성을 진단한다.

- 집중 테스트: 32 passed.
- 전체 pytest: 1726 passed, 1 skipped, 24 warnings, 103 subtests passed. skip은 선택 의존성 langchain_aws 미설치.
- Ruff, CLI 도움말, git diff --check 통과.
- OpenSpec strict 검증 및 아카이브 완료.
- Codex 프로젝트 권한 파일(.codex/config.toml)을 제거해 프로젝트가 workspace-write 및 네트워크 접근을 덮어쓰지 않도록 했다.
- Kalshi 기본값은 별도 kalshi-prediction-market-provider 변경으로 관리하며 이번 변경에서 수정하지 않았다.
