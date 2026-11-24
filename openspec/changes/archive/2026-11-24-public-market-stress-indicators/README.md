# 구현·출처 검증 기록

## 구현

- `PublicMarketData`가 Cboe의 공개 VIX·VIX3M 일별 CSV에서 공통 관측일 종가와 비율을 계산한다. 같은 거래일의 직전 공통 비율과 비교해 역전 시작(1 초과), 지속, 1.0 아래 해소 상태를 기록한다.
- 종목 분석은 정규장 종가 전후 자료 경계와 별도로 당일 Cboe 종가를 사용하지 않고 직전 공통 거래일을 선택한다. 시장 보고서는 보고 대상 거래일 종가를 선택하며, 기대한 관측일이 없으면 `partial`로 표시한다.
- 시장 보고서는 매일 기존 FRED ICE BofA HY OAS 및 IG OAS 비교를 조회한다. 원수치 모델 마스킹과 로컬 검토 제한은 기존 동작을 유지한다.
- `AGENTS.md`, `market-report`, `stock-scenario`, 공통 시황 참조와 ETF 분석 프롬프트에 독점 지표의 공개 인용·미확인 규칙을 추가했다. BofA·Goldman 값을 자동 복제하거나 가짜 데이터로 채우는 수집기는 추가하지 않았다.
- NYSE 시장 폭의 무료·공식 일별 advances/declines 자동 입력을 확인하지 못해 Zweig 자동 계산은 구현하지 않았다. 유효한 입력과 산식이 있는 경우에만 외부 조사에서 계산하도록 했다.

## 출처 확인

| 출처 | 확인 결과 | 구현 처리 |
| --- | --- | --- |
| Cboe VIX history | 승인된 GET에서 HTTP 200, CSV 헤더 `DATE,OPEN,HIGH,LOW,CLOSE`; 첫 관측일 1990-01-02 | 일별 종가를 메모리에서 파싱하고 원본 파일은 저장하지 않음 |
| Cboe VIX3M history | 승인된 GET에서 HTTP 200, CSV 헤더 동일; 첫 관측일 2009-09-18; 공식 호스트에서 CDN 호스트로 리디렉션 | VIX와 일치하는 거래일에 한해 비율 계산 |
| FRED HY OAS | 웹 자료에서 ICE Data Indices 원출처·일별 종가·2026-04 이후 3년 이력 제한 확인. 직접 CSV GET은 시간 초과; 저장소의 FRED API 구현은 기존 경로 사용 | 기존 빈티지·로컬 전용 처리 유지 |
| BofA·Goldman | BofA 공식 안내에 FMS 및 독점 Bull & Bear 설명 확인; 공개 Research Only 약관에 접근 자격·기관 권한 제한. Goldman Panic은 공개 기사에서 트레이딩 데스크 수치를 인용하는 경로를 확인 | 공개된 기사 인용만 `secondary`로 사용. 원자료 미확인은 명시 |
| NYSE advances/declines | 확인한 NYSE 일반 경로 GET은 404. 공식 NYSE 안내는 과거 TAQ 상품을 안내하지만 무료 공개 자동 자료는 확인하지 못함 | 대용 breadth로 Zweig를 산출하지 않음 |
| CNN Fear & Greed | 공식 페이지에서 7요소 구성 및 동일 가중 합산을 확인; 직접 GET은 TLS 오류 | 자동 수집하지 않고 공개 원문을 확인하는 조사 지침만 반영 |

## 검증

- `ruff check` 변경 Python 파일: 통과
- `tradingagents --help`: 통과
- `openspec validate public-market-stress-indicators --strict`: 통과
- `npx --offline @fission-ai/openspec validate`는 npm 캐시에 패키지가 없어 실패했다. 캐시된 OpenSpec 실행 파일로 같은 strict 검증을 수행했다.
- 테스트는 이번 요청에 명시적으로 포함되지 않아 실행하지 않았다.

## 한계

Cboe CSV는 일별 관측 날짜를 제공하지만 분 단위 게시 시각과 파일 수정 이력을 제공하지 않는다. 시장 보고서의 수집 시각과 지수 관측일을 함께 보존하며, 역사적 게시 가능 시각을 소급 증명하지 않는다. BofA·Goldman·CNN 점수의 지속적 공개 피드 및 사용 권한, NYSE advances/declines 무료 자동 데이터 경로는 확인되지 않았다.
