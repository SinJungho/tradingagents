# LLM tier defaults Specification

## Purpose

빠른 tier와 심층 tier의 기본 모델을 명시하고, 빠른 OpenAI tier에만 별도 reasoning effort 기본값을 적용한다.

## ADDED Requirements

### Requirement: 빠른·심층 모델 기본값

기본 설정 MUST 빠른 tier에 `gpt-6-luna`, 심층 tier에 `gpt-6.1-sol`을 지정해야 한다.

#### Scenario: 모델 기본값

- **WHEN** 환경 재정의 없이 기본 설정을 생성한다
- **THEN** 빠른 tier는 `gpt-6-luna`, 심층 tier는 `gpt-6.1-sol`로 설정된다

#### Scenario: 모델 환경 변수 재정의

- **WHEN** 사용자가 빠른 또는 심층 모델 환경 변수를 설정한다
- **THEN** 해당 tier는 지정된 모델을 사용하고 다른 tier의 기본값은 그대로 유지한다

### Requirement: 빠른 tier reasoning effort 기본값

시스템 MUST 전역 OpenAI reasoning effort를 따로 지정하지 않은 경우 빠른 OpenAI tier에 `xhigh`를 사용해야 하며, 이 기본값을 심층 tier에 전달해서는 안 된다.

#### Scenario: 빠른 tier의 xhigh 기본값

- **WHEN** OpenAI 모델을 tier client로 생성하고 전역 reasoning effort가 설정되지 않는다
- **THEN** 빠른 tier에는 `xhigh`를 전달하고 심층 tier는 공급자 기본값을 사용한다

#### Scenario: 전역 reasoning effort 재정의

- **WHEN** 사용자가 `TRADINGAGENTS_OPENAI_REASONING_EFFORT` 또는 실행 설정으로 전역 reasoning effort를 지정한다
- **THEN** 지정한 effort가 빠른 tier의 `xhigh` 기본값보다 우선한다
