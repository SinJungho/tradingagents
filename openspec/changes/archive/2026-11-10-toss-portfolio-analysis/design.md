# Design

## Context

저장소는 LangGraph의 종목별 분석 그래프, 데이터 공급자 라우팅, Typer CLI, Markdown 리포트, 로컬 SQLite 체크포인트를 갖고 있다. 현재 Portfolio Manager는 risk debate 문자열을 요약하는 단일 종목 단계로, 계좌 조회나 계좌 전체 계산은 하지 않는다. 따라서 새 기능은 기존 그래프를 유지하면서 독립된 계좌 분석 흐름을 추가한다.

## Decisions

1. **OpenSpec 사용**: 공식 CLI 1.16.1을 `.local-tools/openspec` 아래 프로젝트 범위로 설치했다. `openspec/`에 변경 제안·요구사항·설계·작업을 관리한다. Codex 설정 생성은 기존 `.agents` 디렉터리 권한 제한 때문에 불가능하므로 CLI로 계속 관리한다.
2. **공식 API 경계**: 기준 명세는 `https://openapi.tossinvest.com/openapi-docs/latest/openapi.json` (확인 시 v1.2.28)이다. 허용 대상은 `POST /oauth2/token`(인증 모듈 한정)과 계좌 목록, 보유, 주문 목록·상세, 매수 가능 금액의 공식 GET 경로다. 호스트·메서드·경로 allowlist, 리다이렉트 금지, 짧은 timeout, 횟수 제한 재시도 및 제한된 페이지 순회를 적용한다.
3. **읽기 전용 구분**: OpenAPI 문서에는 OAuth client-credentials와 빈 scope, API 허용 IP, 계좌 헤더는 있으나 브로커 UI의 키별 읽기 전용 권한 설정은 확인되지 않았다. 앱의 GET allowlist는 브로커 자격증명이 읽기 전용임을 보장하지 않는다. 사용자가 키 권한을 확인하기 전 실계좌 요청을 실행하지 않는 가드와 명시적 CLI 절차를 둔다.
4. **계좌 격리**: `accountSeq`는 어댑터에서만 사용하며 프롬프트·AgentState·로그·리포트에 포함하지 않는다. 신규 분석 경로는 기존 `TradingMemoryLog` 및 SQLite checkpointer를 사용하지 않는다. 계좌 데이터가 포함된 LangChain 요청은 외부 tracing을 비활성화한다.
5. **정규화/계산**: Decimal을 사용하고 KRW와 USD 결과를 우선 분리한다. 합산 비중에는 환율 값과 시각을 첨부한다. `buying-power`는 잔액으로 간주하지 않고 매수 가능 금액으로 표기한다. 손익 및 주문 통계는 공급자가 실제 반환한 필드만 기반으로 한다.
6. **종목/시나리오**: 한국 종목은 6자리 및 영문·숫자 코드, 미국 종목은 보존된 티커로 처리한다. 지원되는 기존 시장 데이터 공급자에 명시적 매핑이 없는 종목은 실패 상태로 남긴다. 기존 Market, News, Fundamentals Analyst와 데이터 도구를 최대 20 LangGraph 단계 안에서 종목별로 재사용하며, 토론·트레이더·리스크·최종 결정 노드는 실행하지 않는다. 보유종목과 관심종목 관계를 명시적으로 구분하고, 이후 포트폴리오 종합 노드가 설정된 기간별 시나리오를 생성한다.
7. **로컬 산출물과 데모**: 인증 없는 합성 데모를 제공하고, 리포트/민감 캐시는 사용자 홈의 TradingAgents 데이터 디렉터리에 둔다. JSON은 버전 관리된 스키마로 검증한다. API·LLM 자동 테스트는 모두 모의한다.

## Data Flow

```text
CLI (demo | live)
  -> Toss read-only adapter -> normalized in-memory snapshot
  -> deterministic portfolio/order calculations
  -> selected symbol analysis using existing providers
  -> portfolio scenario node (short / medium / long)
  -> JSON schema validation + local JSON/Markdown reports
```

계좌 식별자는 어댑터 경계 안에 남고, 시장 분석에 필요한 최소 포지션 사실만 시나리오 입력에 포함된다. 분석 상태는 계좌 식별자 기반 persistent memory/checkpoint에 기록하지 않는다.

## Data Contracts

- Account: API 내부 `accountSeq`와 계좌 유형. CLI는 선택한 계좌의 인덱스만 사용자가 고르게 하고 accountSeq를 출력하지 않는다.
- Holding: 원본 종목 코드, 한국/미국 시장, 거래소, 통화, Decimal 수량/원가/평가/손익, 기준 시각, 공급자 매핑 상태.
- Order: 상태, 주문 수량, 체결 수량, 통화, 체결 단가/시각. 식별자는 LLM에 보내지 않으며 원장 완전성을 주장하지 않는다.
- Cash-like value: `buying_power`로 분명히 이름 붙이고 KRW/USD와 API 조회 시각을 보존한다.
- Report: 조회 범위, 수집 시각, 스키마 버전, 통화별 계산, 기간별 3개 시나리오, 출처/시각, 누락·한계.

## Risks and Trade-offs

- 계좌 주문 API는 모든 주문 유형을 반환하지 않을 수 있어 완전한 과거 거래 내역을 약속하지 않는다.
- 외부 LLM으로 분석 최소 필드를 보낼 수 있으므로 사용 전 동의와 tracing 차단이 필요하다.
- API 키의 브로커 측 읽기 전용 범위가 공식 문서에서 확인되지 않아 실계좌 검증은 별도 권한 확인까지 보류한다.
- 주어진 종목 수만큼 분석 호출 비용이 늘어난다. 사용자가 설정한 분석 종목 수와 같은 실행 안의 수집 중복 제거로 제어한다.

## Verification

- 합성 응답과 모의 HTTP/LLM 테스트로 allowlist·계산·누락·출력 계약을 확인한다.
- 기존 pytest, Ruff, CI 방식의 import/CLI smoke check를 실행한다.
- 스키마 통과는 구조 검증으로만 기록하고 실제 LLM의 근거 정확도나 투자 성과와 구분한다.
