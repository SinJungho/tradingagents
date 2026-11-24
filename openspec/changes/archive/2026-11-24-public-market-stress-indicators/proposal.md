# 공개 시장 스트레스 지표 추가

## Why

시장·거시 리서치에서 BofA 현금 비중과 Bull & Bear, Goldman Panic 같은 독점 수치를 직접 관측 가능한 것처럼 다루면 재현성이 떨어진다. 원자료 접근이 불가능한 지표는 신뢰할 수 있는 공개 인용을 확인하고, 원자료가 공개된 변동성 기간구조와 신용 스프레드는 출처·관측일을 보존해 직접 계산할 필요가 있다.

## What Changes

- Cboe 공개 VIX 및 VIX3M 일별 종가로 1개월/3개월 변동성 비율과 역전·해소 상태를 계산한다.
- 공개 원자료가 없는 BofA·Goldman 자체 지표는 검증된 공개 보도 인용만 사용하고, 확인되지 않으면 미확인으로 남긴다.
- 하이일드 OAS는 기존 FRED/ICE BofA 경로를 유지한다. Zweig Breadth Thrust는 NYSE 상승·하락 종목 원자료와 명시된 산식이 확보될 때만 산출한다.
- CNN Fear & Greed는 공개 지표로 출처·기준 시각을 확인해 보조 맥락으로 쓰며, 그 구성요소를 별도 원자료 지표와 혼동하지 않는다.

## Out of Scope

- BofA·Goldman 유료 리서치에 접근하거나 접근 제한을 우회하지 않는다.
- CNN·BofA·Goldman 점수를 비공식 대체식으로 재구성하지 않는다.
- 출처가 불명확한 시장 폭 대용치로 Zweig Breadth Thrust를 계산하지 않는다.
- 매매 신호, 목표가 또는 통계적 예측력 주장을 추가하지 않는다.

## 데이터 출처 점검

| 출처 | URL | HTTP 상태 | 형식 | 기준일·공개 시각 | 과거 범위·수정 | 이용·저장·한도 | 대용치 한계·판정 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Cboe VIX 일별 종가 | https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv | 200 (GET, 승인된 공개 네트워크 확인) | `text/csv`, `DATE,OPEN,HIGH,LOW,CLOSE` | 날짜별 종가, CSV 응답에 게시 시각 없음 | 1990-01-02부터 확인 | 이력 CSV 공개 경로. 자동 재배포·저장 권리는 확인되지 않아 원자료 파일을 저장하지 않고 요청 중 메모리에서만 처리 | 공식 지수. 사용: 현금 VIX 종가와 3개월 비율 계산 |
| Cboe VIX3M 일별 종가 | https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX3M_History.csv | 200 (GET, 승인된 공개 네트워크 확인, CDN 호스트로 리디렉션) | `text/csv`, `DATE,OPEN,HIGH,LOW,CLOSE` | 날짜별 종가, CSV 응답에 게시 시각 없음 | 2009-09-18부터 확인 | VIX와 동일한 제한을 적용. 당일 종가 공개 시각은 CSV만으로 증명하지 않음 | 공식 지수. 사용: 3개월 종가와 ratio 분모 |
| FRED ICE BofA US HY OAS | https://fred.stlouisfed.org/series/BAMLH0A0HYM2 | 웹 자료 확인, 직접 CSV GET은 제한 시간 초과 | FRED 시계열/API; 기존 구현은 FRED API | 일별 종가 관측, 빈티지 날짜와 분 단위 게시 시각은 구분 | 2026-04부터 FRED 시계열은 최근 3년만 포함 | 기존 API 키·빈티지 처리 유지. ICE 라이선스 자료이므로 원수치는 로컬 리서치 범위에 한정 | 공식 ICE 계열을 FRED가 인용. 사용: 기존 HY OAS 수집을 유지 |
| BofA FMS·Bull & Bear | https://business.bofa.com/en-us/content/global-research-about.html?wcmmode=disabled | 웹 검색으로 공식 안내 확인 | 월간 기관 설문 및 자체 리서치 지표 | 설문 기간·발표일을 각 원문 또는 보도에서 확인 | 설문 보고서 접근 및 재배포 조건은 계정별 | 일부 리서치 접근은 자격·기관 권한·계약 조건에 따름 | 공개 매체가 원수치를 명시 인용한 경우만 대용 증거로 사용. 미확인이면 사용 불가 |
| Goldman Panic Index | https://www.goldmansachs.com/what-we-do/research/ | 웹 검색으로 공식 리서치 포털 확인 | 자체 트레이딩/리서치 지표 | 공개 보도별 인용 시각·수치가 다를 수 있음 | 전체 시계열·산식 공개 여부 확인 불가 | 고객 리서치·트레이딩 자료의 접근 및 재배포 권한 확인 불가 | 공개 매체의 Goldman 직접 인용만 제한적으로 사용. 자체 계산 금지 |
| Zweig Breadth Thrust 입력 | https://www.nyse.com/market-data/historical/ | NYSE 페이지 GET 404; 검색에서 공식 TAQ/히스토리 데이터 상품 확인 | 역사적 TAQ는 상용 데이터 상품 | 거래일 단위 | 장기 이력은 상품별 제공 | 개인 무료 자동 공급 경로와 이용 조건을 확인하지 못함 | 무료·공식 일별 NYSE 상승/하락 원자료가 확인될 때만 계산. 현재 자동 수집은 사용 불가 |
| CNN Fear & Greed | https://www-stage-fastly.stellar.cnn.com/markets/fear-and-greed | 공식 웹 콘텐츠 검색 확인, 직접 GET은 TLS 오류 | 공개 웹 페이지 | 화면 기준 시각 필요 | 공개 차트 범위에 따름 | 자동 수집/API 및 재배포 조건 확인 불가 | 수동 확인 가능한 보조 맥락으로만 사용. 공식 원문/시각이 없으면 사용 불가 |

일반 샌드박스의 직접 GET은 FRED 도메인 허용 목록 차단으로 실패했다. 승인된 읽기 전용 GET에서도 FRED CSV는 제한 시간 초과, NYSE의 확인 URL은 404였다. Cboe CSV는 두 URL 모두 성공했고 VIX3M 요청이 `cdn-api.cboe.com`으로 리디렉션됐다. 이는 한 번의 접근성 점검이며 공급자의 지속 가용성이나 자동 이용 권한을 보증하지 않는다.
