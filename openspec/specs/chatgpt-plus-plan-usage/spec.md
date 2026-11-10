# chatgpt-plus-plan-usage Specification

## Purpose
ChatGPT Plus 사용자가 로컬 TradingAgents의 OpenAI 모델 호출에 ChatGPT 플랜 사용량을 승인하고 쓸 수 있도록 한다.

## Requirements

### Requirement: 로컬 OAuth 연결

시스템 MUST 사용자가 명시적으로 실행한 CLI 인증 명령으로 Sign in with ChatGPT를 시작하고, loopback callback, PKCE, state 및 nonce를 검증한다.

#### Scenario: ChatGPT 플랜 연결

- **WHEN** 사용자가 `tradingagents auth connect`를 실행하고 브라우저에서 사용량 권한을 승인한다
- **THEN** 시스템 MUST OAuth 응답의 ID 토큰 서명, issuer, client audience, 만료, nonce 및 `chatgpt.tokens.use.direct` 권한을 검증한다
- **AND** 시스템 MUST 토큰과 등록 정보를 사용자 전용 로컬 설정 파일에 원자적으로 저장하고 Unix에서 권한 `0600`을 적용한다

#### Scenario: 권한 미승인 또는 잘못된 callback

- **WHEN** 사용자가 권한을 거부하거나 callback state, client ID 또는 토큰 검증이 실패한다
- **THEN** 시스템 MUST 인증 정보를 저장하지 않고 이전 계정 연결을 덮어쓰지 않는다
- **AND** 오류는 authorization code, access token, refresh token 또는 원문 callback 값을 포함하지 않는다

### Requirement: ChatGPT 플랜 Responses 요청

시스템 MUST 명시적으로 ChatGPT 플랜 인증을 선택한 OpenAI 클라이언트만 OAuth bearer token으로 Responses API를 호출한다.

#### Scenario: 인증된 추론 요청

- **WHEN** 인증된 사용자가 TradingAgents 분석을 실행한다
- **THEN** 각 모델 요청은 `/v1/responses`로 `stream=true`와 `store=false`를 전송한다
- **AND** 시스템 MUST `response.completed` 이벤트를 받은 경우에만 요청을 성공으로 처리한다
- **AND** 시스템 MUST 일반 OpenAI API 키, Chat Completions 또는 비지원 매개변수로 요청하지 않는다

#### Scenario: ChatGPT 플랜 사용 한도 또는 인증 만료

- **WHEN** 토큰 갱신에 실패하거나 사용량 한도 오류가 발생한다
- **THEN** 시스템 MUST 요청을 재시도하거나 API 키 인증으로 자동 전환하지 않고 안전한 오류를 보여준다

### Requirement: 연결 상태 및 해제

시스템 MUST 연결 상태를 민감한 토큰 없이 보여주고 사용자가 로컬 자격 증명을 해제할 수 있게 한다.

#### Scenario: 연결 상태 확인과 로그아웃

- **WHEN** 사용자가 `tradingagents auth status` 또는 `tradingagents auth disconnect`를 실행한다
- **THEN** 상태에는 연결 여부와 계정 표시에 필요한 최소 정보만 노출한다
- **AND** 시스템 MUST 해제 시 가능한 경우 renewable session을 취소한 뒤 로컬 토큰을 지운다

### Requirement: API 키 경로와 데이터 경계 보존

시스템 MUST 기존 OpenAI API 키 경로를 기본값으로 유지하고 ChatGPT 플랜 인증은 명시적으로 선택한 경우에만 사용한다.

#### Scenario: 기존 API 키 설정

- **WHEN** ChatGPT 플랜 인증이 선택되지 않았다
- **THEN** OpenAI 클라이언트는 기존 `OPENAI_API_KEY` 인증 동작을 유지한다

#### Scenario: API 키 자동 폴백 금지

- **WHEN** ChatGPT 플랜 인증이 선택됐지만 연결이 없거나 요청이 실패한다
- **THEN** 시스템 MUST `OPENAI_API_KEY` 또는 다른 provider로 자동 전환하지 않는다
