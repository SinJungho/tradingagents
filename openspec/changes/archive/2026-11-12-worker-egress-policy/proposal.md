# 워커 egress 정책 내보내기

## Why

Orca 워커의 DNS 및 HTTPS egress 정책은 실행 호스트가 관리한다. 저장소 hook이나 애플리케이션 코드는 이를 허용할 수 없지만, 현재 워커 설정에서 필요한 목적지와 포트를 안전하게 산출해 관리자가 적용할 명세가 필요하다.

## What Changes

- 현재 quick/deep LLM endpoint와 지원 데이터 API endpoint를 기반으로 DNS 및 TCP 목적지 목록을 내보내는 `tradingagents network-policy` 명령을 추가한다.
- 원시 endpoint URL, 자격 증명, 쿼리 문자열은 출력하지 않는다.
- Orca/API 진단 지침에 정책 적용 책임이 실행 호스트에 있음을 명시하고, 적용 후 워커 내부에서 `tradingagents doctor`를 실행하도록 안내한다.

## Out of Scope

- Orca 서버·VM의 네트워크 ACL 또는 DNS resolver 설정을 저장소 코드가 직접 변경하는 것
- 네트워크 오류 시 권한 제한을 우회하거나 모든 외부 네트워크를 자동 허용하는 것
- API 키, 인증 상태 또는 계정 응답을 네트워크 정책 파일에 저장하는 것
