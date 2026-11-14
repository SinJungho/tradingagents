## ADDED Requirements

### Requirement: 워커 outbound 정책 내보내기

시스템 MUST 현재 실행 설정에서 확인할 수 있는 DNS 및 TCP outbound 목적지를 기계 판독 가능한 형식으로 내보내야 한다. 목적지에는 선택된 quick/deep LLM endpoint와 지원 데이터 API endpoint가 포함되어야 하며, 원시 URL, 사용자 정보, 쿼리 문자열, API 키를 출력해서는 안 된다. 동적 자격 증명 경로 또는 리다이렉트로 추가 대상이 필요할 수 있음을 표시해야 한다.

#### Scenario: 제한형 Orca 정책 작성

- **WHEN** 사용자가 `tradingagents network-policy --format json`을 실행할 때
- **THEN** 시스템은 DNS resolver 요구사항과 목적지 hostname·TCP port를 포함한 JSON을 출력하고, 정책 소유자가 실행 호스트임을 명시한다

#### Scenario: 사용자 지정 endpoint

- **WHEN** 선택된 제공자가 사용자 지정 endpoint를 사용할 때
- **THEN** 시스템은 URL 전체 대신 유효한 hostname과 port만 포함하며, endpoint를 안전하게 해석할 수 없으면 해당 tier를 확인 불가로 표시한다

#### Scenario: 로컬 endpoint

- **WHEN** endpoint가 localhost 또는 loopback 주소일 때
- **THEN** 시스템은 이를 외부 egress 허용 대상과 구분해 로컬 대상임을 표시한다

### Requirement: 실행 호스트 정책과 앱 진단 분리

시스템 MUST 정책 내보내기와 현재 프로세스의 실제 연결 진단을 구분해야 한다. 정책 내보내기는 네트워크를 변경했다고 주장해서는 안 되며, Orca 워커의 실제 적용 여부는 해당 워커에서 수행한 진단 결과로 확인해야 한다.

#### Scenario: 네트워크 제한이 있는 워커

- **WHEN** 워커에서 API 목적지의 DNS 또는 연결 검사가 실패할 때
- **THEN** 시스템은 오류 계층을 보고하고 실행 호스트의 DNS 및 필요한 목적지/포트 egress 정책을 확인하도록 안내한다

#### Scenario: 정책 적용 후 확인

- **WHEN** 관리자가 Orca 실행 호스트의 정책을 갱신한 뒤 워커에서 `tradingagents doctor`를 실행할 때
- **THEN** 시스템은 현재 워커에서 관찰한 연결 상태만 보고하고 다른 호스트의 네트워크 상태를 추정하지 않는다
