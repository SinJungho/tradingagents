# 프로젝트 네트워크 시험 기록

## 실행 조건
- 조사일: 2026-11-19 KST. Codex CLI 0.170.0, macOS, 현재 piranha 워크트리.
- 기존 미커밋 변경을 보존했다. 시험 전 `.codex/config.toml`은 없었다.
- 사용자 설정의 해당 프로젝트 trust_level은 trusted. 사용자 설정에 network_proxy와 명시적 network/permission 설정은 없었다. `/etc/codex/requirements.toml`, `/etc/codex/managed_config.toml`은 없었다. 이 결과는 클라우드·MDM 정책 부재를 증명하지 않는다.
- 현재 실행기의 managed permission은 network restricted이며 `.codex`는 읽기 전용이었다. 호스트 DNS 조회와 시험 설정 생성은 기존 개별 승인 심사를 거쳤다.

## 설정 우선순위 근거
- [공식 설정 안내](https://developers.openai.com/codex/config-basic/): CLI override > 신뢰된 프로젝트 > 선택 profile > 사용자 > 관리형 기본값 > 시스템 > 내장 기본값. 강제 requirements는 별도로 동작을 제한한다. 최신 안내와 설치 버전 차이를 고려한다.
- [0.170.0 설정 파서](https://github.com/openai/codex/blob/rust-v0.170.0/codex-rs/core/src/config/mod.rs): 명시적 permission profile이 전달되면 그 network bit를 사용한다. 프로젝트의 legacy workspace network 허용만으로 그 profile을 덮어쓰지 않는다.
- [0.170.0 네트워크 병합](https://github.com/openai/codex/blob/rust-v0.170.0/codex-rs/core/src/config/network_config.rs): feature enabled와 candidate profile network enabled가 모두 참일 때 `[features.network_proxy]` 설정을 반영한다. 이후 managed constraints를 적용한다.
- [0.170.0 프록시 안내](https://github.com/openai/codex/blob/rust-v0.170.0/codex-rs/network-proxy/README.md)는 named profile 예시를 제공한다. legacy 구문 지원 여부는 위 버전 소스로 별도 확인했다.
- Orca가 새 세션에 전달한 정확한 설정 출처와 관리형 정책 충돌 여부는 실행 결과 없이는 단정하지 않는다.

## 공개 목적지 조사 — 호스트 실행, 샌드박스 통과 아님
- 기존 `network-policy --format json`은 현재 샌드박스에서 Polymarket DNS 실패를 unresolved로 보고했다.
- 승인된 호스트 DNS 조회: gamma-api.polymarket.com → d29c69nd1a26c8.cloudfront.net. 공개 IPv4: 54.239.180.10, 54.239.180.122, 54.239.180.50, 54.239.180.9.
- 직접 연결 검사용: example.com → 104.20.23.154, 172.66.147.243; www.sec.gov → 23.49.147.172. 관측 시점 값이므로 재검증 때 다시 조회한다.
- 기존 CLI `network-policy --format codex-toml`로 24개 정확한 호스트 생성. 공급자·transport 변경 없음. 검토한 후보는 `trial-config.toml`에 보존한다.
- 인증·netrc·환경 프록시를 사용하지 않은 공개 HEAD 조사: House Clerk·BEA·Census·Federal Reserve·Nasdaq·Reddit는 HTTP 200. SEC·Wikipedia·StockTwits·BLS는 403, Yahoo finance/query는 429, cookie/consent는 404, OpenAI 루트는 421. 서비스 제한과 연결 증거를 구분한다.
- FRED 루트는 research.stlouisfed.org → www.stlouisfed.org로, iShares 루트는 www.blackrock.com으로 이동했다. 실제 FRED `/fred/series/observations`는 같은 호스트에서 400, 실제 IWM CSV 경로는 같은 호스트에서 200이었다. 루트 탐색용 별도 호스트는 API·CSV 동작에 필요함이 확인되지 않아 허용하지 않았다.
- Polymarket 직접 호스트 HEAD는 ConnectionError, 별칭 루트는 502였지만 별칭 `/markets`와 원래 Host 헤더는 200이었다. 데이터 품질 검증은 수행하지 않았다.
- HEAD 조사는 인증 후 흐름과 모든 미래 리다이렉트를 증명하지 않는다. 동적 별칭은 재생성 때 재확인한다.

## 시험 적용
- 검토한 후보를 `.codex/config.toml`에 독점 생성했다. 기존 파일이 있으면 실패하도록 처리했다.
- network_access와 제한형 proxy를 함께 설정하고 전역 설정·파일 권한·approval 설정은 바꾸지 않았다.
- 독립 Codex: 호스트에서 `codex exec --ephemeral`을 시작, sandbox/profile override 없음. 내부 검사에 권한 상승·중첩 sandbox 금지.
- Orca: `agent launch`의 기본 표면은 terminal, reason=user_default. 모델·권한·표면 override 없음. 시작 후 내부 검사에 같은 제한 적용.

## 검증 결과
| 항목 | 독립 Codex | Orca 기본 terminal 세션 |
|---|---|---|
| 프로젝트 설정 | network enabled, proxy 환경 변수 설정 확인 | network enabled, proxy 환경 변수 설정 확인 |
| 허용 House HTTPS | curl 0, HTTP 200 | curl 0, HTTP 200 |
| 미허용 example.com | 런타임의 명시적 allowlist 거부 | 런타임의 명시적 allowlist 거부 |
| 직접 연결, 공개 IP 고정 | 두 호스트 모두 curl 7 + socket connect EPERM | 두 호스트 모두 curl 7 + socket connect EPERM |

명시적 메시지: `Network access to "example.com" was blocked: domain is not on the allowlist for the current sandbox mode.` 승인 계획은 런타임 **또는** 프록시의 명시적 거부를 허용하므로 이 항목은 통과다. 프록시 내부 로그까지 확인한 것은 아니다. HTTP 403만을 차단 증거로 삼지 않았다.

## 저장소 검증
- 집중 테스트: 54 passed.
- 현재 세션 전체: 8 failed, 1865 passed, 1 skipped, 103 subtests passed. 실패 7개는 loopback bind의 EPERM, 나머지 SEC 간격 테스트는 즉시 집중 재실행에서 통과했다.
- 실패 항목 재실행: 7 failed, 1 passed. 모두 남은 실패는 bind EPERM.
- 기존 승인 심사를 통한 호스트 전체 합성 테스트: **1873 passed, 1 skipped, 24 warnings, 103 subtests passed** (69.50초). 실제 브로커·LLM 분석 호출 없음. skip은 선택 의존성 langchain_aws 부재.
- Ruff, CLI `--help`, OpenSpec strict 통과. 애플리케이션 코드는 이번 단계에서 추가 수정하지 않았다.


## 최종 판정과 남은 범위
- 두 환경 모두 허용 연결·런타임 명시적 거부·직접 IP 연결의 OS 거부를 재현했다. 프로젝트 설정 적용의 행동 증거가 확인되어 시험 설정을 유지한다. 정책 무시·우회는 관측되지 않아 rollback 조건은 발생하지 않았다.
- `curl --noproxy '*' --resolve` 실패만으로 결론을 내리지 않았다. 같은 공개 IP의 `socket.connect`를 일반 exec에서 추가 실행하여 두 환경 모두 errno 1 / EPERM을 확인했다. 독립 Codex의 errno 진단은 동일 프로젝트·설정으로 호스트에서 시작한 별도 새 세션에서 실행했다.
- OS 거부의 구체적인 내부 구성 요소와 클라우드/MDM 정책 출처까지 특정하지는 않았다. 확인된 충돌이 없으므로 관리자 설정 변경을 요구하지 않는다.
- 직접 연결 추가 진단은 `socket.socket().connect((ip, 443))`에 3초 timeout을 설정하고 OSError.errno만 기록했다. DNS 조회나 HTTP 인증 요청은 하지 않았다.
- 기존 현재 세션의 제한은 소급 변경되지 않는다. 새 세션에서 사용해야 한다.
- 커밋·푸시·병합은 하지 않았다. 기준 커밋 새 워크트리 재현 검증과 OpenSpec 아카이브는 별도 커밋 요청 이후 남아 있다. 전체 배포 완료로 표시하지 않는다.
- rollback이 필요하면 이번에 생성한 `.codex/config.toml`이 `trial-config.toml`과 동일한지 먼저 확인한 뒤 삭제한다. 이후 다른 설정이 추가됐으면 이번 네트워크 항목만 제거한다.
