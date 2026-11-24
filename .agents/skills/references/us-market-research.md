# 미국 시황 공통 조사 기준

시장 보고서는 대상 거래일 20:00 ET, 종목은 정규장 마감과 실행 시각 중 이른 시각을 적용한다. 조기 폐장은 거래소 달력을 따른다. 비거래일 요청은 직전 거래일의 공통 시황을 쓴다. CLI 근거의 ID·출처·관측 및 공개 시각·표본을 확인하고, 과거 분석에는 해당 시점까지 확인된 자료를 사용한다. 빈티지 날짜와 실제 공개 시각을 구분한다.

## 평시와 주간 점검

- 지수·대표 업종 ETF·시장 폭, 달러지수, 2·5·10년 명목금리와 5·10년 실질금리를 확인한다. 5년·10년 실질금리는 관측일이 일치할 때 비교한다.
- WTI·금·구리의 1·5·20거래일과 DXY의 1거래일 변화에는 최신 관측 봉과 같은 ET 시각에 종료한 과거 완료 봉을 쓴다. 해당 봉이 없으면 현재 가격과 관측 시각, 미확인 사유를 남긴다. 연속선물 기준·계약월·롤 영향을 표시한다. BTC·ETH는 같은 마감 시각 기준 24시간·7일·30일을 비교한다.
- VIX·VIX9D와 SPX 풋·콜 거래량 비율의 집계 범위를 확인한다. ES·NQ 거래량·미결제약정은 계약월, 세션, 잠정·확정을 구분한다. 월간 정책금리 선물의 내재 월평균과 회의별 확률을 분리한다. [Cboe 옵션 통계](https://www.cboe.com/us/options/market_statistics/daily/) · [CME FedWatch 방법론](https://www.cmegroup.com/articles/2023/understanding-the-cme-group-fedwatch-tool-methodology.html)
- 주 마지막 거래일과 종목 심층 분석은 HY·IG OAS의 시작·종료 관측일을 맞춘 1·5거래일 변화를 확인한다. 원수치와 변화는 로컬 시장 보고서에서 확인한다. 주간 점검은 CFTC 레버리지펀드의 보고 대상 선물 포지션과 ICI ETF 순발행 추정의 집계 대상·기간을 기록한다. 업종 이익 전망 수정은 동일 표본·두 빈티지를 비교하며 가이던스는 기업 공시·IR을 확인한다. [CFTC TFF](https://publicreporting.cftc.gov/stories/s/r4w3-av2u) · [ICI 주간 ETF 순발행](https://www.ici.org/research/statistics/etfs/weekly-estimated-etf-net-issuance) · [SEC EDGAR](https://www.sec.gov/edgar/search/)

미국 ETF 심층 보고서에는 원자재·BTC/ETH·HY/IG·달러·변동성·파생상품별 근거 ID, 관측일, 판단에 미친 영향과 누락 사유를 적는다. 종목 기준 이후 공개되어 20:00 ET 시장 보고서에 들어간 자료는 다음 장의 판단 조건으로 연결한다.

## 조사 시작 기준

- S&P 500 또는 Nasdaq Composite의 절대 일간 변화 2% 이상, VIX 상승 5포인트 이상, 같은 관측 기준의 10년 국채금리 절대 변동 10bp 이상을 기본값으로 쓴다. 조사 시작 이유와 근거 ID를 적는다. 값이 없으면 판정 미확인이다.
- CPI·PCE·고용·FOMC의 발표 시각과 실제치, 발표 전에 기록된 컨센서스, 이전 발표치와 당시 수정치를 같은 단위로 비교한다. 발표 원문·ALFRED 빈티지를 확인하고 발표 전후 동일 시간 창의 완료된 금리·달러·ES/NQ를 비교한다. [BLS 발표 보관](https://www.bls.gov/bls/news-release/) · [BEA](https://www.bea.gov/news) · [FOMC 자료](https://www.federalreserve.gov/monetarypolicy/materials/) · [ALFRED](https://alfred.stlouisfed.org/)
- 장기금리 급변 시 정책금리 기대, 국채 입찰, 기간 프리미엄 추정의 관측·공개 시점을 확인한다. [재무부 입찰](https://fiscaldata.treasury.gov/datasets/treasury-securities-auctions-data/treasury-securities-auctions-data-updated/) · [뉴욕 연은 기간 프리미엄](https://www.newyorkfed.org/research/data_indicators/term-premia-tabs)
- 주가 급변·신용 불안·근거 충돌 시 기업 공시·IR과 증권사 공개 원문을 비교한다. CTA·변동성 목표 펀드·딜러 감마·레버리지 ETF 재조정은 실제 집계, 증권사 고객 표본, 모형 추정으로 구분한다. 주간 포지션·감마·고객 표본으로 당일 매도 주체를 확정할 수 없다.
- 금융 스트레스가 의심되면 SLOOS의 대출 기준과 수요, 관측일을 맞춘 SOFR–IORB를 확인한다. 원화 성과는 USD/KRW와 자산의 시작·종료 관측 시각이 일치할 때 두 가격비를 곱해 계산한다. [SLOOS](https://www.federalreserve.gov/data/sloos.htm) · [SOFR 공표·수정 기준](https://www.newyorkfed.org/markets/reference-rates/additional-information-about-reference-rates) · [IORB](https://www.federalreserve.gov/monetarypolicy/reserve-balances.htm)

## 시장 심리·스트레스 지표

- 매일 Cboe의 [VIX 일별 종가](https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv)와 [VIX3M 종가](https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX3M_History.csv)를 같은 관측일로 맞춰 VIX/VIX3M을 계산한다. 1.0 초과는 1개월 기대 변동성이 3개월보다 높은 역전, 1.0 이하로 내려온 날은 역전 해소로 표시한다. Cboe CSV는 관측일만 주므로 게시 시각을 확인된 것처럼 쓰지 않는다. 종목 정규장 기준 시각보다 뒤에 형성되는 종가를 사용하지 않는다.
- HY 신용 스트레스는 기존 `BAMLH0A0HYM2` ICE BofA US High Yield OAS를 FRED 빈티지와 함께 사용한다. CNN Fear & Greed의 junk-bond-demand 요소와 같은 수치로 취급하지 않는다.
- BofA Global Fund Manager Survey 현금 비중과 BofA Bull & Bear, Goldman Panic은 공개 리서치 원자료 대신 공개 기사에서 해당 기관이 직접 인용된 경우에 한해 쓴다. 출처 기사, 게시 시각, 설문·지표 기준일, 수치, 표본이나 계산 범위를 기록하고 `secondary`로 분류한다. 기사마다 업데이트 수치가 다르면 각 시각을 병기하고 최신이라고 추정하지 않는다. 공개 인용을 찾지 못하면 미확인이다.
- CNN Fear & Greed는 CNN 원문에 표시된 값·조회 시각을 보조 맥락으로 기록한다. 공개 화면이 확인되지 않으면 값을 추정하지 않는다. CNN의 7개 구성요소는 서로 독립된 추가 근거로 중복 합산하지 않는다.
- Zweig Breadth Thrust는 NYSE advances/(advances+declines)의 10일 EMA가 0.40 미만에서 10거래일 안에 0.615 초과로 이동하는 통상 정의를 쓴다. 거래소 입력 자료·종목 범위·평균 방식이 확보된 경우에만 산출한다. SPY 보유 종목이나 S&P 표본의 일일 상승 비율로 대체하지 않는다. [StockCharts 설명](https://stockcharts.com/newsletter/archive/chartwatchers_1700899200.html)
- 이 지표들은 공포·포지셔닝·옵션 가격을 설명하는 보조 근거다. 단독 바닥 신호, 진입 시점 또는 통계적 예측력으로 단정하지 않는다.

## 심층 조사와 인용

평시에는 공통 수집 결과를 쓴다. 급변, 중요한 근거 충돌 또는 사용자 심층 요청에서는 최대 세 명에게 금리·거시·신용, 옵션·선물·프로그램 수급, 기업 실적·증권사 원문을 나눈다. `gpt-6.2-luna`와 `xhigh` 조합을 사용할 수 있을 때 사용하며, 지원되지 않으면 담당 에이전트가 직접 조사한다. 작업자에게 분석 대상, 공개 근거와 기준 시각만 전달한다. 계좌·보유 자료는 공유하지 않는다.

각 작업자는 원문 URL, 관측·공개 시각, 핵심 관측, 집계·표본 및 방법의 한계, 반대 근거를 제출하고 코디네이터가 원문과 대조한다. 주장마다 근거 ID 또는 원문 링크와 판단 변경 조건을 붙인다. 발표 전 컨센서스와 증권사·프라임 브로커는 공개 원문을 검증할 수 있는 범위에서 보완한다. 인용 보도에는 매체와 원문 확인 여부를 표시한다. 조건이 없었던 `미실행`과 실행 후 값이 없는 `미확인`을 나누고, 후자는 공개 원문 부재·기준 시각 불일치·이용 조건·공급자 오류 등 사유를 적는다.


## 완료 판정

- 보고서 작성 전에 적용할 일간·조건부 항목을 확정한다. 급변이 확인되면 시작 근거 ID와 추가 조사 항목을 기록한다. 기준값이 빠졌으면 판단을 미확인으로 남긴다.
- 적용 항목마다 결과, 출처, 관측 시각 또는 관측일을 대조한다. 자료가 없으면 조회한 출처와 미확인 사유를 기록한다. 조건에 해당하지 않는 조사와 적용되지만 미실행인 조사를 구분한다.
- 시나리오 생성이나 CLI 종료 성공만으로 완료 판정을 내리지 않는다. `market_research.coverage`에서 적용 항목의 누락을 확인하고, 자동 수집 범위 밖의 적용 항목은 공개 원문을 확인해 근거를 보완한다. 근거나 검증 상태가 비어 있거나 적용 항목에 미실행·미확인이 남아 있으면 부분 완료로 보고한다.
