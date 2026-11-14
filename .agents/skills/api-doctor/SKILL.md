---
name: api-doctor
description: LLM·토스·데이터 API 호출 실패를 진단하고 조치한다. "API 호출이 안 돼", "doctor fail", "Orca 워커에서 인증 실패", "키 넣었는데 안 읽혀", "어느 환경변수에 넣어야 해", "rate limit", "timeout" 요청에 사용한다.
---

# API·인증 진단

## 1. 진단 실행

```bash
tradingagents network-policy --format json
tradingagents doctor
```

Codex의 새 워커 세션은 시작 hook을 Codex에서 한 번 신뢰한 뒤 `doctor`를 자동 실행한다. 신뢰되지 않은 hook은 Codex가 검토를 요구할 수 있다. 실패하면 필요한 경우 정책 JSON도 컨텍스트에 포함한다. 자동 진단이 생략됐거나 결과를 다시 확인할 때는 두 명령을 문제가 난 바로 그 프로세스(Orca 워커, 하위 에이전트 포함)에서 실행한다. `network-policy`는 현재 설정에 필요한 DNS resolver와 TCP 목적지를 비밀 없는 JSON으로 내보낸다. 이를 Orca 실행 호스트의 제한형 egress 정책에 적용한 뒤, 같은 워커에서 `doctor`를 다시 실행해 확인한다. 저장소 hook과 CLI는 실행 호스트의 방화벽·DNS 정책을 바꾸지 못한다. 부모 세션의 환경변수와 인증 파일이 워커에 그대로 있다고 가정하지 않는다.

## 2. 결과별 조치

| 진단 결과 | 확인할 것 |
| --- | --- |
| 환경변수 미설정 | 저장소 루트의 env 파일에 변수명이 있는지(`.env.example`의 이름과 대조). 값은 보지 않는다. 사용자에게 변수명과 넣을 위치만 안내한다. |
| ChatGPT 플랜 인증 없음 | `tradingagents login chatgpt`. 워커는 같은 사용자 홈의 인증을 재사용한다. |
| 호스트 도달 실패 | `network-policy` 결과에 맞춘 워커 호스트 DNS 및 목적지/포트 egress 정책, 프록시·VPN |
| HTTP 401/403 | 키 종류(API 키 vs 다른 제품 키), 플랜·권한, 허용 IP 등록 |
| HTTP 429 / timeout | 공급자 rate limit(rpm)에 맞춰 동시성·재시도·timeout 조정. 설정 변경은 OpenSpec 변경으로 진행 |

## 3. 보고 원칙

- 변수명, 설정 여부, 오류 분류, HTTP 상태, 재시도 가능 여부만 보고한다. 키·토큰·계좌 식별자·원시 응답은 출력하지 않는다.
- env 파일 값을 직접 읽지 않는다(hook이 차단한다). "읽어서 확인해" 요청에는 `doctor` 결과로 대신한다.
- 유료 호출이 발생할 수 있는 테스트(실제 모델 호출 등)는 사용자 허용 후 실행한다.
