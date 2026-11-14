# Proposal

## Why

현재 TradingAgents의 Portfolio Manager는 종목 하나에 대한 위험 토론을 요약하며, 사용자의 실제 보유와 주문을 조회하거나 계좌 전체 위험을 계산하지 않는다. 토스증권의 공식 조회 API와 기존 시장 분석 기능을 결합해, 계좌 정보를 안전하게 반영한 기간별 시나리오를 제공한다.

## What Changes

- 공식 토스 API의 계좌, 보유, 주문, 주문 상세와 매수 가능 금액 조회를 제한된 전용 어댑터로 추가한다.
- 한국·미국 종목, 통화, 시각, 수량과 데이터 범위를 보존하고 포트폴리오 및 주문 통계를 코드로 계산한다.
- 기존 분석 공급자와 LangGraph에 계좌 단위 분석 경로를 추가하고 단기·중기·장기 상승·기본·하락 시나리오를 제공한다.
- 합성 데이터 데모, 명시적 JSON 스키마, 한국어 Markdown 리포트, CLI 설정과 사용 문서를 추가한다.
- 실계좌 호출은 브로커 측 읽기 전용 권한을 사용자가 확인한 경우에만 명시적으로 허용한다. 애플리케이션 GET 제한을 브로커 권한으로 표현하지 않는다.
- 주문 생성·정정·취소, 조건주문, 자동매매와 자동 리밸런싱은 범위에서 제외한다.

## Capabilities

### New Capabilities

- `toss-account-read`: 공식 토스 OpenAPI를 통해 선택한 계좌의 보유·주문·주문 상세·현금성 조회 데이터를 안전하게 가져온다.
- `portfolio-scenario-analysis`: 정규화된 계좌 데이터를 계산하고 기존 분석 기능을 이용해 기간별 시나리오와 로컬 리포트를 제공한다.

### Modified Capabilities

없음. 기존 단일 종목 Portfolio Manager 계약은 바꾸지 않는다.

## Impact

- `tradingagents/portfolio/` 신규 패키지, LangGraph 연결, CLI와 reporting 경로, 테스트, `.env.example`, 사용 문서.
- 공식 토스 API `https://openapi.tossinvest.com`의 조회 경로만 사용하며 새 런타임 의존성은 가급적 추가하지 않는다.
- 외부 LLM에는 계좌 식별자를 제외한 분석 최소 필드가 전달될 수 있다. 금융 리포트와 캐시는 기본적으로 로컬 사용자 데이터 디렉터리에 둔다.
