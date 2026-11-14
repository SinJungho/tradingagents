# ChatGPT Plus 플랜 사용 연결

## Why

NVIDIA Build의 OpenAI 호환 채팅 요청이 장시간 응답하지 않는 문제가 반복됐다. 사용자는 별도 API 과금 대신 ChatGPT Plus 사용량으로 TradingAgents의 분석 모델을 실행하고 싶다. OpenAI의 Sign in with ChatGPT는 로컬 오픈소스 앱이 사용자의 플랜 사용량을 Responses API 요청에 쓰는 흐름을 제공하지만, 현재 TradingAgents는 API 키를 전제로 비스트리밍 호출을 한다.

## What Changes

- 로컬 CLI에서 브라우저 OAuth 로그인, 계정 권한 검증, 토큰 갱신과 로그아웃을 지원한다.
- 명시적인 OpenAI 인증 모드에서만 저장된 ChatGPT 플랜 인증을 사용하고, Chat Completions가 아닌 Responses 스트리밍 요청을 보낸다.
- 요청은 `store=false`, `stream=true`, 재시도 없음으로 제한하고 플랜 사용량 한도와 계정별 모델 가용성을 안내한다.
- 기존 `OPENAI_API_KEY` 인증 경로는 유지하며, 플랜 인증 실패 시 유료 API 키 경로로 자동 전환하지 않는다.
- 인증 토큰은 저장소 밖 사용자 설정 경로에 권한 제한을 적용해 보관하고 로그나 프롬프트에 넣지 않는다.

## Capabilities

### New Capabilities

- `chatgpt-plus-plan-usage`: 로컬 TradingAgents가 사용자가 승인한 ChatGPT 플랜 사용량으로 모델 응답을 요청한다.

## Impact

- 영향 범위는 CLI 인증 명령, OpenAI LLM 클라이언트, 모델 목록 안내, 설정 문서와 mock 테스트다.
- OAuth 로그인과 실제 추론은 사용자가 CLI를 실행해 인증한 경우에만 일어난다. 저장소 테스트는 HTTP/LLM mock만 사용한다.
- Sign in with ChatGPT는 현재 Responses API 스트리밍, 계정별 모델, 공유 플랜 한도 및 일부 API 매개변수 제한을 따른다. OpenAI가 안내한 요구사항을 벗어나는 옵션은 이 모드에서 보내지 않는다.
- NVIDIA smoke, Toss 연결, 실제 보유 정보, 주문 처리 및 거래 실행은 범위에 포함하지 않는다.
