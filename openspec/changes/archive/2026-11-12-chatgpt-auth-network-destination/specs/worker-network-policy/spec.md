## MODIFIED Requirements

### Requirement: 워커 outbound 정책 내보내기
시스템 MUST 현재 실행 설정에 선택된 quick/deep LLM endpoint와 데이터 공급자 체인에서 실제 사용하는 DNS 및 TCP outbound 목적지를 기계 판독 가능한 형식으로 내보내야 한다. ChatGPT 플랜 인증이 선택된 경우 인증에 필요한 auth.openai.com도 포함해야 한다. 도구별 공급자 재정의는 범주 공급자 설정보다 우선해야 한다. default 공급자 설정은 해당 도구에서 사용할 수 있는 공급자 전체를 포함해야 한다. 원시 URL, 사용자 정보, 쿼리 문자열, API 키를 출력해서는 안 된다. 동적 자격 증명 경로 또는 리다이렉트로 추가 대상이 필요할 수 있음을 표시해야 한다.

#### Scenario: 플랜 인증 목적지
- **WHEN** openai_auth가 chatgpt_plan이거나 quick/deep 제공자가 chatgpt일 때
- **THEN** 정책은 auth.openai.com을 포함한다

#### Scenario: API 키 인증
- **WHEN** LLM 인증이 API 키를 사용할 때
- **THEN** 정책은 사용하지 않는 auth.openai.com을 포함하지 않는다

#### Scenario: 제한형 Orca 정책 작성
- **WHEN** 사용자가 tradingagents network-policy --format json을 실행할 때
- **THEN** 시스템은 DNS resolver 요구사항과 선택된 공급자 체인의 hostname·TCP port만 출력하고 정책 소유자가 실행 호스트임을 명시한다

#### Scenario: 도구별 공급자 재정의
- **WHEN** 데이터 도구에 범주 설정을 덮어쓰는 공급자 재정의가 있을 때
- **THEN** 시스템은 도구별 공급자 체인 목적지를 포함하고 선택되지 않은 대체 공급자 목적지는 제외한다

#### Scenario: 기본 공급자 체인
- **WHEN** 범주 또는 도구에 default가 설정되어 해당 도구의 사용 가능한 공급자 전체를 사용할 때
- **THEN** 정책은 그 도구의 모든 공급자 목적지를 포함한다

#### Scenario: 사용자 지정 endpoint
- **WHEN** 선택된 제공자가 사용자 지정 endpoint를 사용할 때
- **THEN** 시스템은 URL 전체 대신 유효한 hostname과 port만 포함하며 endpoint를 안전하게 해석할 수 없으면 해당 tier를 확인 불가로 표시한다

#### Scenario: 로컬 endpoint
- **WHEN** endpoint가 localhost 또는 loopback 주소일 때
- **THEN** 시스템은 이를 외부 egress 허용 대상과 구분해 로컬 대상으로 표시한다
