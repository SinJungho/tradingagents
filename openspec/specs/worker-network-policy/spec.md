# worker-network-policy Specification

## Purpose

Orca 워커가 필요한 DNS 및 TCP 목적지를 안전하게 내보내고, 실행 호스트의 egress 정책 적용과 앱 진단을 분리한다.

## Requirements

### Requirement: 새 워커 세션의 자동 API 사전 진단

Codex 워커 MUST 프로젝트 hook이 신뢰된 상태에서 새 세션이 시작될 때 현재 실행 환경에서 `tradingagents doctor`를 자동 실행하고 결과를 워커 컨텍스트에 제공해야 한다. 검사는 인증 없는 HEAD 요청만 사용하고 인증정보, 응답 본문 또는 사용자 정의 전체 URL을 노출해서는 안 된다. 검사 실패는 세션 시작을 차단해서는 안 된다.

#### Scenario: 새 Orca 워커 생성

- **WHEN** 프로젝트 hook을 신뢰한 상태로 새 Codex 워커 세션이 시작되고 CLI가 준비되어 있을 때
- **THEN** hook은 해당 워커에서 `tradingagents doctor`를 실행하고 현재 실행 환경의 결과를 세션 컨텍스트에 제공한다

#### Scenario: 네트워크 목적지에 도달하지 못함

- **WHEN** 자동 진단에서 DNS·연결·TLS 오류가 있을 때
- **THEN** hook은 제한형 `tradingagents network-policy --format json` 결과와 Orca 실행 호스트에 정책을 적용해야 한다는 안내를 제공하고 세션은 계속 시작한다

#### Scenario: 애플리케이션 환경 준비 전 세션 시작

- **WHEN** 새 세션 시작 시 CLI와 Python 모듈 실행 환경에서 모두 TradingAgents 의존성을 사용할 수 없을 때
- **THEN** hook은 진단을 완료할 수 없음을 알리고 수동 재실행 명령을 제공하며 세션 시작을 막지 않는다

#### Scenario: 기존 세션 재개 또는 압축 후 재개

- **WHEN** 세션 시작 원인이 startup이 아닌 resume, compact, clear 또는 fork일 때
- **THEN** 자동 네트워크 진단은 다시 실행하지 않는다

### Requirement: 실패 시 호스트 정책 내보내기

시스템 MUST 자동 진단에서 DNS·연결·TLS 도달 실패가 발견되면 현재 워커의 제한형 outbound 정책을 추가 정보로 제공해야 한다. hook은 운영체제 또는 Orca 실행 호스트의 네트워크 권한을 변경해서는 안 된다.

#### Scenario: 진단 실패 후 제한형 정책 제시

- **WHEN** `tradingagents doctor`가 네트워크 계층 도달 실패를 반환할 때
- **THEN** hook은 `tradingagents network-policy --format json`의 비밀 없는 결과를 제공하고 정책 변경 위치가 실행 호스트임을 표시한다

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

### Requirement: 실행 호스트 정책과 앱 진단 분리

시스템 MUST 정책 내보내기와 현재 프로세스의 실제 연결 진단을 구분해야 한다. 정책 내보내기는 네트워크를 변경했다고 주장해서는 안 되며, Orca 워커의 실제 적용 여부는 해당 워커에서 수행한 진단 결과로 확인해야 한다.

#### Scenario: 네트워크 제한이 있는 워커

- **WHEN** 워커에서 API 목적지의 DNS 또는 연결 검사가 실패할 때
- **THEN** 시스템은 오류 계층을 보고하고 실행 호스트의 DNS 및 필요한 목적지/포트 egress 정책을 확인하도록 안내한다

#### Scenario: 정책 적용 후 확인

- **WHEN** 관리자가 Orca 실행 호스트의 정책을 갱신한 뒤 워커에서 `tradingagents doctor`를 실행할 때
- **THEN** 시스템은 현재 워커에서 관찰한 연결 상태만 보고하고 다른 호스트의 네트워크 상태를 추정하지 않는다
