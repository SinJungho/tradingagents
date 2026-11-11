# LLM tier 기본 모델 조정

## Why

기본 심층 모델을 Finance Agent 벤치마크에서 더 높은 점수를 기록한 `gpt-6.1-sol`로 바꾸고, 빠른 tier는 `gpt-6-luna`와 `xhigh` reasoning effort 조합으로 사용한다.

## What Changes

- 빠른 tier 기본 모델은 `gpt-6-luna`, 빠른 tier OpenAI reasoning effort는 `xhigh`로 설정한다.
- 심층 tier 기본 모델은 `gpt-6.1-sol`로 설정한다.
- 기존 `TRADINGAGENTS_OPENAI_REASONING_EFFORT` 설정은 지정된 경우 두 tier의 기본 reasoning effort보다 우선한다.
- 기본 설정, CLI 모델 선택 목록, 안내 문서와 mock 테스트를 함께 갱신한다.

## Capabilities

### New Capabilities

- `llm-tier-defaults`: TradingAgents의 빠른·심층 모델과 tier별 reasoning effort 기본값을 정한다.

## Impact

- 영향 범위는 기본 설정, tier client 설정 전달, OpenAI 모델 목록, 문서와 설정 테스트다.
- API 키, 인증, 브로커 접근과 포트폴리오 조회 동작은 변경하지 않는다.
