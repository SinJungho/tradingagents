# 제공자 사용 한도 오류 분류

## Why

2026-11-19 `portfolio live --symbol TQQQ` 시나리오 생성이 두 번 `분류되지 않은 API 오류 (재시도 가능: 아니요)`로 끝났다. 실제 원인은 ChatGPT 요금제 사용 한도 소진이었고, 오류 객체의 구조화된 `code`(`subscription_sharing_usage_limit_exceeded`)에 드러나 있었다. 상태 코드와 예외 클래스만 보는 현재 분류는 이 경우를 놓친다.

## What Changes

- 실패 분류가 예외의 문자열 `code` 필드(공급자가 정한 기계용 오류 코드)도 확인한다. 메시지·응답 본문은 계속 읽지 않는다.
- 사용 한도·할당량 코드(`usage_limit`, `insufficient_quota` 포함)는 `quota`(계정 한도 초과, 재시도 불가), 요청 제한 코드(`rate_limit` 포함)는 `rate_limit`으로 분류한다.

## Out of Scope

- 한도 해제 시각 표시, 다른 제공자로의 자동 전환, 새 실패 범주 추가
