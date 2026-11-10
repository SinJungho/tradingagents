# glm-structured-output-smoke Specification

## Purpose
합성 입력으로 TradingAgents의 NVIDIA Build 연결을 확인하고, 빠른 분석 역할의 GLM-5.3-Flash와 심층 분석 역할의 DeepSeek V4.1 Flash가 기존 출력 형식과 도구 호출 경로를 처리하는지 검증한다.

## Requirements

### Requirement: 역할별 NVIDIA 모델 라우팅

시스템 MUST NVIDIA provider를 사용할 때 빠른 분석 역할은 `z-ai/glm-5.3-flash`, 심층 분석 역할은 `deepseek-ai/deepseek-v4.1-flash` 모델 ID를 사용해야 한다. Smoke MUST 합성 입력만 사용해야 한다.

#### Scenario: 역할별 모델 선택

- **WHEN** 빠른 분석 또는 심층 분석 smoke를 실행할 때
- **THEN** 각 역할에 지정된 모델 ID와 NVIDIA API endpoint를 사용한다
- **AND** 요청은 투자 사실 정확도나 수익성을 평가하는 데 사용하지 않는다

### Requirement: NVIDIA 모델별 capability 및 reasoning 호환성

시스템 MUST NVIDIA 모델 ID에 publisher 접두사가 있을 때 capability 판정을 접두사 뒤 모델 ID 기준으로 해야 한다. DeepSeek thinking 응답이 `reasoning_content`를 제공하면 이후 도구 요청에 해당 값을 보존해야 하며, DeepSeek와 GLM의 구조화 출력 바인딩은 지원되지 않는 named `tool_choice`를 보내지 않아야 한다.

#### Scenario: NVIDIA 접두 모델 ID capability 선택

- **WHEN** `deepseek-ai/deepseek-v4.1-flash` 또는 `z-ai/glm-5.3-flash`로 구조화 출력을 바인딩할 때
- **THEN** 각각 DeepSeek 또는 GLM capability를 선택하고 스키마를 도구로 전달한다
- **AND** 해당 모델이 거부하는 `tool_choice` 필드를 요청에 포함하지 않는다

#### Scenario: DeepSeek reasoning turn 이어가기

- **WHEN** NVIDIA endpoint가 DeepSeek assistant 응답에 `reasoning_content`를 반환하고 후속 도구 턴이 발생할 때
- **THEN** client는 그 값을 assistant 메시지에 보존하고 후속 요청에 포함한다
- **AND** reasoning 값이 없으면 임의로 만들거나 추정하지 않는다

### Requirement: 단일 요청, 로컬 rate limit과 출력 상한

시스템 MUST 실제 NVIDIA API smoke를 호출자가 계정의 청구 없는 개발·평가 사용 조건을 확인하고 `--confirm-no-charge`를 지정한 경우에만 수행해야 한다. 실행은 합성 입력, 최대 256 출력 토큰, HTTP 클라이언트 timeout 300초, 실행당 요청 1회, 이 로컬 smoke 경로에서 최대 분당 1회, 재시도 0회여야 한다. NVIDIA 계정 화면에 표시되는 `Up to 40 rpm`은 분당 요청 상한이며 응답 시간 보장이 아니다. 실제 요청 속도는 모델과 트래픽에 따라 달라질 수 있고, 로컬 상한은 공급자 한도나 계정의 잔여량을 의미하지 않는다. 확인 플래그가 없거나 계정 사용 조건이 불명확하면 실제 요청을 보내지 않아야 한다.

#### Scenario: 무료 평가 사용 조건 확인

- **WHEN** 계정에 청구 없는 평가 한도가 확인되고 `--confirm-no-charge`가 지정될 때
- **THEN** DeepSeek 심층 경로를 최대 한 번 호출한다
- **AND** 이번 실행에 이어 60초 안에 재실행하면 다음 호출을 보내지 않는다
- **AND** 자동 재시도 또는 자유 텍스트 폴백 요청을 보내지 않는다

#### Scenario: NVIDIA endpoint 응답 지연

- **WHEN** 합성 요청의 응답 데이터가 300초 안에 도착하지 않을 때
- **THEN** smoke는 안전한 timeout 오류를 보고하고 종료한다
- **AND** 요청을 재시도하거나 다른 endpoint로 폴백하지 않는다

#### Scenario: 출력 토큰 한도 초과

- **WHEN** `--max-tokens` 값이 256보다 클 때
- **THEN** 요청 전에 smoke를 거부하고 NVIDIA API를 호출하지 않는다

#### Scenario: 제한이 없는 NVIDIA 실행 모드

- **WHEN** `nvidia` provider를 `--single-call` 없이 실행할 때
- **THEN** client를 만들기 전에 실행을 거부한다

#### Scenario: 계정 한도 불명확 또는 유료 가능성

- **WHEN** 무상 한도를 확인할 수 없거나 요청이 유료로 전환될 수 있을 때
- **THEN** 실제 요청을 건너뛰고 mock 검증 결과와 미확인 조건을 보고한다

### Requirement: 자격 증명과 사용자 자료 보호

Smoke MUST `NVIDIA_API_KEY`의 존재만 확인할 수 있으며 키 값, `.env`, `.env.bak`, 토스 계좌, 실제 보유·주문 자료를 읽거나 출력해서는 안 된다.

#### Scenario: 키가 없음

- **WHEN** 현재 프로세스에 `NVIDIA_API_KEY`가 설정되지 않았을 때
- **THEN** API 요청 전에 smoke를 건너뛰고 키 값은 출력하지 않는다

### Requirement: Mock 기반 자동 검증

자동 테스트 MUST 합성 인증정보와 HTTP mock을 사용해야 하며 실제 LLM 또는 브로커를 호출해서는 안 된다.

#### Scenario: 요청 계약과 응답 파싱

- **WHEN** 자동 smoke 테스트를 실행할 때
- **THEN** 테스트는 provider, 역할별 모델 ID, 출력 상한, 요청 횟수, 구조화 출력 또는 도구 호출 필드와 합성 응답 파싱을 검증한다

#### Scenario: 실패 응답

- **WHEN** 요청 또는 응답 파싱에 실패할 때
- **THEN** 실패를 표시하고 재시도하지 않는다
- **AND** 키, 요청 헤더, 예외 메시지, 원시 응답 및 합성 프롬프트를 출력하지 않는다

### Requirement: 제한된 결과 해석

결과 보고 MUST 공급자가 제공한 토큰 사용량과 지연 시간만 기록해야 하며, smoke 통과나 Finance Agent 벤치마크 점수를 TradingAgents의 투자 분석 정확도 또는 수익성으로 표현해서는 안 된다.

#### Scenario: 사용량 정보 누락

- **WHEN** 응답에 사용량 또는 지연 정보가 없을 때
- **THEN** 해당 값을 제공되지 않았다고 보고하고 추정하지 않는다
