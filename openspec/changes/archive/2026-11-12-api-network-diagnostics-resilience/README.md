# 조사 결과와 범위

## 호출 호스트 인벤토리

| 제공자/경로 | 호스트 | 호출 위치 |
| --- | --- | --- |
| Yahoo Finance 가격·시장·기초 정보 | `query2.finance.yahoo.com` | `tradingagents/dataflows/vendors/yahoo/` (yfinance) |
| Yahoo Finance 뉴스 | `query1.finance.yahoo.com` | `tradingagents/dataflows/vendors/yahoo/news.py` (yfinance) |
| Alpha Vantage | `www.alphavantage.co` | `tradingagents/dataflows/vendors/alpha_vantage/common.py` |
| FRED | `api.stlouisfed.org` | `tradingagents/dataflows/vendors/fred.py` |
| SEC 티커 | `www.sec.gov` | `tradingagents/dataflows/vendors/sec_edgar.py` |
| SEC company facts | `data.sec.gov` | `tradingagents/dataflows/vendors/sec_edgar.py` |
| Toss 계좌 조회 | `openapi.tossinvest.com` | `tradingagents/portfolio/toss.py` |
| Reddit RSS | `www.reddit.com` | `tradingagents/dataflows/vendors/reddit.py` |
| StockTwits | `api.stocktwits.com` | `tradingagents/dataflows/vendors/stocktwits.py` |
| Polymarket | `gamma-api.polymarket.com` | `tradingagents/dataflows/vendors/polymarket.py` |
| Kalshi | `external-api.kalshi.com` | `tradingagents/dataflows/vendors/kalshi.py` |
| TypeSafe 게시물 필터 | 기본 `api.typesafe.ai`, 또는 사용자 endpoint | `tradingagents/agents/post_screen.py` |
| ChatGPT 로그인 | `auth.openai.com` | `tradingagents/llm_clients/chatgpt_auth.py`, `tradingagents/chatgpt_plan_auth.py` |
| LLM API | OpenAI, Anthropic, Google, xAI, DeepSeek, Qwen, Z.AI/GLM, MiniMax, OpenRouter, Mistral, Moonshot, Groq, NVIDIA, Bedrock, Azure, Ollama 또는 사용자 endpoint | `tradingagents/llm_clients/`, 기본 URL은 `tradingagents/runtime_diagnostics.py`와 `tradingagents/llm_clients/openai_client.py` |

`tradingagents doctor`는 위 공개 데이터 호스트에 인증 없이 HEAD 요청을 보냅니다. TypeSafe는 키가 설정된 경우에만 점검하고, LLM은 현재 quick/deep 설정에 선택된 endpoint만 점검합니다. 사용자 지정 endpoint의 전체 URL은 출력하지 않습니다.

## 환경 측정

같은 12개 공개 호스트에 대해 DNS 조회를 각각 3회 하고, 인증 없는 HTTPS HEAD로 경로를 확인했습니다. DNS 성공 횟수와 범주만 기록했으며 API 키나 응답 본문은 사용하지 않았습니다.

| 실행 환경 | DNS 결과 | HTTPS 결과 |
| --- | --- | --- |
| 제한된 작업공간 프로세스 | 12개 모두 `0/3` | 모두 DNS 오류 |
| 샌드박스 밖의 로컬 프로세스 | 12개 모두 `3/3` | 11개 도달 가능, Polymarket은 연결 오류 |

이 측정은 작업공간의 DNS/아웃바운드 제한을 원인으로 지목합니다. Polymarket은 DNS가 정상인 로컬 프로세스에서도 연결 단계에서 별도 실패했습니다. 이는 인증·HTTP 상태 문제가 아니며 공급자 또는 경로별 확인 대상입니다.

저장소 변경만으로 관리형 샌드박스의 DNS 리졸버 연결이나 아웃바운드 정책을 바꿀 수는 없습니다. 상승 권한 진단은 한 번의 비교 측정에만 사용됐고 앱 프로세스의 네트워크 권한을 바꾸지 않습니다. 샌드박스 안에서 실행되는 호출은 해당 환경의 네트워크 정책이 허용될 때까지 실패합니다. 로컬 Mac에서 API를 사용할 때는 네트워크가 허용된 일반 터미널에서 실행하거나, 워커 실행 환경의 관리자 설정에서 DNS 및 HTTPS egress를 허용해야 합니다.

## 구현 범위와 한계

- 공유 requests GET과 Reddit/StockTwits의 멱등 조회는 DNS·연결·timeout·제공자 5xx만 최대 3회 요청합니다. Yahoo 조회는 기존 rate-limit 재시도를 유지하고 일시적 전송 오류를 최대 2회 시도합니다.
- Toss는 별도 read-only 클라이언트의 기존 제한 재시도를 유지합니다. POST 인증·LLM 요청, 사용자 정의 SDK 내부 재시도, 그리고 환경 네트워크 정책은 바꾸지 않습니다.
- 재시도는 영구적인 DNS 차단을 해결하지 않습니다. 그 경우 로그의 제공자·호스트·범주·시도 수로 환경 정책을 확인할 수 있게 합니다.


## 검증 결과

- 변경 관련 집중 테스트: 197 passed, 8 subtests passed.
- 전체 pytest: 1696 passed, 1 skipped, 24 warnings, 103 subtests passed. 전체 테스트는 외부 네트워크를 막고 loopback만 허용하며, 샌드박스가 loopback bind도 제한해 마지막 검증은 loopback bind가 가능한 실행으로 수행했습니다.
- `ruff check .`: 통과.
- `tradingagents --help`: 통과.
- OpenSpec strict 검증: 통과.

OpenAI Agents API의 호스팅 샌드박스는 `network.access`를 환경 설정으로 관리하고 템플릿 정책은 재정의로 더 넓힐 수 없습니다. 자동 검토도 네트워크 제한을 해제하지 않습니다. 이 문서는 해당 API 환경에 대한 공식 설명이며, 현재 로컬 Codex 실행의 네트워크 설정을 변경하는 방법이라고 단정하지 않습니다: [호스팅 샌드박스 네트워크 설정](https://developers.openai.com/api/docs/guides/agents-api/environments/openai-hosted), [자동 검토와 네트워크 제한](https://developers.openai.com/api/docs/guides/agents-api/sessions/approvals).
