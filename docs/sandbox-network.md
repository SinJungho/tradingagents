# 프로젝트 샌드박스 네트워크

## 설정과 보장 범위

`tradingagents network-policy --format json|text`는 현재 선택된 공급자와 스킬의 목적지를 내보낸다. `--format codex-toml`은 `.codex/config.toml`에 검토 후 병합할 조각을 출력한다. 파일을 수정하지 않으며 미확인 대상이 있으면 종료 코드 2로 실패한다. 먼저 임시 파일에 출력하고 성공 여부를 확인한다. 실패한 출력을 활성 설정으로 리다이렉트하지 않는다.

Codex 0.170.0에서 `[features.network_proxy]`의 `enabled`, `domains`, `allow_upstream_proxy`, `allow_local_binding` 구문을 확인했다. `sandbox_workspace_write.network_access`와 제한형 프록시를 함께 사용한다. 파일 접근과 approval 설정은 조각에 포함하지 않는다. named permission profile을 쓰는 실행기는 해당 profile의 network 설정과 관리형 정책도 관리자가 확인해야 한다. 기존 설정의 상속된 allow/deny 항목은 병합 후 별도로 검토한다.

- 정확한 hostname만 허용한다. 동적 CloudFront 별칭은 DNS에서 확인한 값만 포함한다.
- 사설망 포괄 허용·상위 프록시 연결·임의 Unix socket 접근을 끈다. 로컬/IP 및 비표준 포트는 자동 생성 대상이 아니다.
- TOML은 호스트 단위 정책이며 JSON의 TCP 포트를 강제하는 방화벽 규칙이 아니다.
- 일반 샌드박스 명령에 적용된다. 승인된 전체 권한 상승, 웹 검색, 앱/MCP에는 동일한 보장을 주장하지 않는다.
- 미선택 LLM·패키지 저장소·GitHub는 자동 포함하지 않는다. 목록 밖 작업은 기존 개별 승인 절차를 유지한다.
- 기존 파일·LLM 실행·푸시·병합 승인 규칙을 유지한다. 전역 사용자 설정을 변경하지 않는다.

공식 근거: [Codex configuration reference](https://developers.openai.com/codex/config-reference/), [network proxy 구현 문서](https://github.com/openai/codex/blob/main/codex-rs/network-proxy/README.md). 최신 문서와 설치 버전은 다를 수 있으므로 구문 읽기와 실제 실행 검증을 모두 수행한다.

## 목적지 출처

| 호스트 | 용도와 저장소 근거 |
|---|---|
| query1.finance.yahoo.com, query2.finance.yahoo.com | Yahoo 시세·뉴스, `dataflows/vendors/yahoo/` 및 yfinance |
| fc.yahoo.com, guce.yahoo.com, consent.yahoo.com, finance.yahoo.com | 설치된 yfinance `data.py`의 cookie·consent 요청 및 보고서 Yahoo 경로 |
| www.sec.gov, data.sec.gov, efts.sec.gov | SEC 원문·company facts·13F 검색, `vendors/sec_edgar.py`, `portfolio-disclosures/scripts/disclosures.py` |
| disclosures-clerk.house.gov | 하원 공시 원문, `portfolio-disclosures/scripts/disclosures.py` |
| api.openfigi.com | 13F CUSIP→티커 매핑(2차 출처), `portfolio-disclosures/scripts/disclosures.py` |
| apps.bea.gov, www.bea.gov, www.census.gov, www.bls.gov, www.federalreserve.gov | 경제 일정, `dataflows/market_report.py` |
| en.wikipedia.org, www.nasdaqtrader.com, www.ishares.com | 지수 구성·상장 목록, `stock_discovery.py` |
| www.reddit.com, api.stocktwits.com | 직접 사용하는 감성 자료, `dataflows/vendors/` |
| api.stlouisfed.org, www.alphavantage.co | 선택된 FRED·Alpha Vantage 체인 |
| gamma-api.polymarket.com 및 DNS로 확인한 정확한 CloudFront 별칭 | 선택된 Polymarket transport, `vendors/polymarket.py`; 별칭 미확인 시 생성 실패 |
| external-api.kalshi.com | Kalshi를 선택한 경우만 |
| openapi.tossinvest.com | Toss 설정이 있는 경우만, 조회 용도; 개발 검증은 인증 없는 HEAD만 |
| api.typesafe.ai 또는 검증된 설정 호스트 | TypeSafe가 설정된 경우만 |
| 선택한 quick/deep 제공자의 호스트 및 필요한 auth.openai.com | `runtime_diagnostics.py`, `llm_clients/`; 전체 URL·인증정보는 내보내지 않음 |

이 표는 코드상 목적지 조사이며 실제 접속/리다이렉트 검증 완료를 의미하지 않는다. 리다이렉트가 발생하면 확인된 추가 호스트만 반영한다. AWS credential chain 목적지는 동적이므로 별도 검토 전에는 TOML 생성을 거부한다.

## 적용 검증

1. JSON의 `unresolved`가 비어 있는지, 선택한 공급자와 호스트 용도가 맞는지 확인한다. TOML 조각을 검토하고 기존 프로젝트 설정에 해당 항목만 병합한다.
2. 신뢰된 프로젝트에서 새 Codex 세션을 시작한다. `doctor`의 프로젝트 파일 존재와 연결 결과를 확인한다. 파일 존재·훅 성공만으로 성공 판정하지 않는다.
3. 에이전트의 일반 명령으로 인증 없는 공개 HTTPS HEAD를 실행한다. 예: `curl -I --max-time 8 https://www.sec.gov`. 응답은 연결 증거이며 401/403/429는 인증·공급자 제한과 따로 해석한다.
4. 미허용 공개 목적지(예: example.com)에 동일한 요청을 보내고 런타임/프록시의 명시적 정책 거부를 기록한다. DNS 실패·timeout·일반 HTTP 403은 충분하지 않다.
5. 호스트 조사에서 확인한 공개 IP와 원래 호스트명으로 `curl --noproxy '*' --resolve example.com:443:<확인한-IP> -I --max-time 8 https://example.com`을 실행한다. 미허용 호스트와 허용 호스트를 각각 검사한다. DNS를 생략한 실패에도 OS 정책 거부 또는 적용된 정책 근거가 필요하다. 프록시 경로와 직접 경로를 모두 확인해야 한다.
6. 호스트에서 시작한 독립 Codex 세션과 Orca 기본 새 세션에서 각각 반복한다. 현재 에이전트 안의 중첩 `codex sandbox` 실행은 최종 검증에 사용하지 않는다. 기준 커밋의 새 워크트리 검증은 별도 커밋 요청 이후 수행한다. 미신뢰 프로젝트에서는 미적용/미검증으로 기록한다.

정책 무시·우회가 확인되면 **이번 시험 설정만 되돌리고 활성 배포를 중단**한다. 실제 정책 충돌이 확인된 경우에만 근거와 필요한 관리자 변경을 제시한다. 확인하지 못한 프로젝트 신뢰, permission profile, managed network 출처, 프록시 실행 지원은 미검증으로 기록한다. 네트워크만 무제한으로 켜는 대안을 사용하지 않는다. 승인된 개별 권한 상승 결과는 별도 실행으로 기록하며 샌드박스 통과로 계산하지 않는다.

자동 전달은 정책이 기준 커밋에 포함된 새 워크트리에 한한다. 기존 워크트리·이전 커밋 기준 워크트리는 갱신이 필요하다. 커밋·기준 브랜치 반영 전에는 전체 배포로 보고하지 않는다. 되돌릴 때는 이번에 병합한 네트워크 항목만 제거하고 기존 설정을 보존한다.

시험 적용은 배포 완료가 아니다. [2026-11-19 시험 기록](../openspec/changes/scoped-sandbox-network-access/README.md)에 환경별 관측, 설정 후보, 남은 검증을 기록한다.
