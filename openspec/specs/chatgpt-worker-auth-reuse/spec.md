# chatgpt-worker-auth-reuse Specification

## Purpose
제공자별 인증 저장소를 정확히 진단하고 동일 호스트·사용자의 로컬 워커가 기존 로그인을 안전하게 재사용하도록 보장한다.

## Requirements

### Requirement: 제공자별 인증 진단

시스템 MUST chatgpt 제공자를 chatgpt_auth 저장소로 진단하고 복구 명령으로 `tradingagents login chatgpt`를 안내해야 한다. openai_auth=chatgpt_plan은 기존 저장소와 `tradingagents auth connect`를 유지해야 한다. 진단은 네트워크 갱신 없이 로컬 저장 상태만 표시해야 한다.

#### Scenario: 다른 저장소가 비어 있음
- **WHEN** chatgpt 인증만 저장되어 있을 때
- **THEN** doctor는 해당 인증을 인식하고 다른 저장소 누락을 로그인 실패로 표시하지 않는다

#### Scenario: 인증 누락과 DNS 장애
- **WHEN** 인증이 없거나 DNS 연결에 실패할 때
- **THEN** 인증 저장 상태와 네트워크 실패를 분리하고 제공자에 맞는 로그인 명령을 표시한다

### Requirement: 동일 호스트 로그인 재사용

로컬 워커 MUST 동일 사용자 홈의 기존 인증을 재사용해야 한다. 갱신은 프로세스 잠금 후 파일 재조회와 원자적 저장을 유지해야 한다. 인증 거부는 같은 요청을 반복하지 않고 일시적 장애는 인증을 보존해야 한다.

#### Scenario: 워커 시작 및 재시작
- **WHEN** 동일 임시 홈에서 여러 합성 워커를 시작하거나 재시작할 때
- **THEN** 추가 로그인 없이 저장된 인증을 읽는다

#### Scenario: 동시 갱신
- **WHEN** 여러 프로세스가 만료 인증을 동시에 갱신할 때
- **THEN** 갱신 토큰을 한 번만 사용하고 나머지는 저장된 새 토큰을 읽는다

#### Scenario: 별도 홈과 오류 출력
- **WHEN** 별도 홈에 인증이 없거나 인증 서버가 비밀값이 포함된 오류를 반환할 때
- **THEN** 올바른 로그인 명령을 안내하고 비밀값과 원시 응답은 출력하지 않는다
