## ADDED Requirements

### Requirement: 시나리오 종합 기간 이름 정규화

시스템 MUST 시나리오 종합 응답의 기간 이름을 대소문자와 기간 설명 접미어에 관계없이 설정된 short, medium, long 기간에 대응시키고 설정 순서로 재배열해야 한다. 시스템 MUST 세 기간이 각각 정확히 한 번 대응되지 않는 응답은 거부해야 한다.

#### Scenario: 표기가 다른 기간 이름

- **WHEN** 종합 응답의 기간 이름이 "Short-term", "medium (1-6 months)", "LONG"처럼 표기되거나 순서가 다를 때
- **THEN** 시스템은 각 기간을 short, medium, long에 대응시켜 설정 순서로 보고서를 만든다

#### Scenario: 누락되거나 중복된 기간

- **WHEN** 종합 응답에 세 기간 중 하나가 없거나 같은 기간이 두 번 나올 때
- **THEN** 시스템은 응답을 거부하고 시나리오 실패로 기록한다
