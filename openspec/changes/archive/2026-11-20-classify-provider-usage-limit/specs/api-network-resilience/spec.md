## ADDED Requirements

### Requirement: 공급자 오류 코드 기반 실패 분류

시스템 MUST 예외에 문자열 `code` 필드가 있으면 그 값으로 사용 한도와 요청 제한을 분류해야 한다. 사용 한도·할당량 코드는 `quota`(재시도 불가), 요청 제한 코드는 `rate_limit`으로 표시한다. 예외 메시지와 응답 본문은 읽거나 출력하지 않는다.

#### Scenario: 요금제 사용 한도 소진

- **WHEN** LLM 호출이 HTTP 상태 없이 `code=subscription_sharing_usage_limit_exceeded`인 오류로 실패할 때
- **THEN** 시스템은 `계정 한도 초과 (재시도 가능: 아니요)`로 표시하고 원시 메시지는 출력하지 않는다

#### Scenario: 알 수 없는 오류 코드

- **WHEN** 오류 코드가 사용 한도나 요청 제한 형식이 아닐 때
- **THEN** 시스템은 기존 상태 코드·예외 유형 분류를 그대로 따른다
