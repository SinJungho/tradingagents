## ADDED Requirements

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
