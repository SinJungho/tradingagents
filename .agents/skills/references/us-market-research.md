# 미국 시황 공통 조사 기준

시장 보고서는 대상 거래일 20:00 ET, 종목은 정규장 마감과 실행 시각 중 이른 시각을 적용한다. 조기 폐장은 거래소 달력을 따른다. 비거래일 요청은 직전 거래일의 공통 시황을 쓴다. CLI 근거의 ID·출처·관측 및 공개 시각·표본을 확인하고, 과거 분석에는 해당 시점까지 확인된 자료를 사용한다. 빈티지 날짜와 실제 공개 시각을 구분한다.

## 평시와 주간 점검

- 지수·대표 업종 ETF·시장 폭, 달러지수, 2·5·10년 명목금리와 10년 실질금리를 비교한다.
- WTI·금·구리의 1·5·20거래일 변화에 연속선물 기준·계약월·롤 영향을 표시한다. BTC·ETH는 같은 마감 시각 기준 24시간·7일·30일을 비교한다.
- VIX·VIX9D와 SPX 풋·콜 거래량 비율의 집계 범위를 확인한다. ES·NQ 거래량·미결제약정은 계약월, 세션, 잠정·확정을 구분한다. 월간 정책금리 선물의 내재 월평균과 회의별 확률을 분리한다. [Cboe 옵션 통계](https://www.cboe.com/us/options/market_statistics/daily/) · [CME FedWatch 방법론](https://www.cmegroup.com/articles/2023/understanding-the-cme-group-fedwatch-tool-methodology.html)
- 주 마지막 거래일은 HY·IG OAS의 관측일을 맞추고, CFTC 레버리지펀드의 보고 대상 선물 포지션과 ICI ETF 순발행 추정의 집계 대상·기간을 기록한다. 업종 이익 전망 수정은 동일 표본·두 빈티지를 비교하며 가이던스는 기업 공시·IR을 확인한다. [CFTC TFF](https://publicreporting.cftc.gov/stories/s/r4w3-av2u) · [ICI 주간 ETF 순발행](https://www.ici.org/research/statistics/etfs/weekly-estimated-etf-net-issuance) · [SEC EDGAR](https://www.sec.gov/edgar/search/)

## 조사 시작 기준

- S&P 500 또는 Nasdaq Composite의 절대 일간 변화 2% 이상, VIX 상승 5포인트 이상, 같은 관측 기준의 10년 국채금리 절대 변동 10bp 이상을 기본값으로 쓴다. 조사 시작 이유와 근거 ID를 적는다. 값이 없으면 판정 미확인이다.
- CPI·PCE·고용·FOMC의 발표 시각과 실제치, 발표 전에 기록된 컨센서스, 이전 발표치와 당시 수정치를 같은 단위로 비교한다. 발표 원문·ALFRED 빈티지를 확인하고 발표 전후 동일 시간 창의 완료된 금리·달러·ES/NQ를 비교한다. [BLS 발표 보관](https://www.bls.gov/bls/news-release/) · [BEA](https://www.bea.gov/news) · [FOMC 자료](https://www.federalreserve.gov/monetarypolicy/materials/) · [ALFRED](https://alfred.stlouisfed.org/)
- 장기금리 급변 시 정책금리 기대, 국채 입찰, 기간 프리미엄 추정의 관측·공개 시점을 확인한다. [재무부 입찰](https://fiscaldata.treasury.gov/datasets/treasury-securities-auctions-data/treasury-securities-auctions-data-updated/) · [뉴욕 연은 기간 프리미엄](https://www.newyorkfed.org/research/data_indicators/term-premia-tabs)
- 주가 급변·신용 불안·근거 충돌 시 기업 공시·IR과 증권사 공개 원문을 비교한다. CTA·변동성 목표 펀드·딜러 감마·레버리지 ETF 재조정은 실제 집계, 증권사 고객 표본, 모형 추정으로 구분한다. 주간 포지션·감마·고객 표본으로 당일 매도 주체를 확정할 수 없다.
- 금융 스트레스가 의심되면 SLOOS의 대출 기준과 수요, 관측일을 맞춘 SOFR–IORB를 확인한다. 원화 성과는 USD/KRW와 자산의 시작·종료 관측 시각이 일치할 때 두 가격비를 곱해 계산한다. [SLOOS](https://www.federalreserve.gov/data/sloos.htm) · [SOFR 공표·수정 기준](https://www.newyorkfed.org/markets/reference-rates/additional-information-about-reference-rates) · [IORB](https://www.federalreserve.gov/monetarypolicy/reserve-balances.htm)

## 심층 조사와 인용

평시에는 공통 수집 결과를 쓴다. 급변, 중요한 근거 충돌 또는 사용자 심층 요청에서는 최대 세 명에게 금리·거시·신용, 옵션·선물·프로그램 수급, 기업 실적·증권사 원문을 나눈다. `gpt-6.2-luna`와 `xhigh` 조합을 사용할 수 있을 때 사용하며, 지원되지 않으면 담당 에이전트가 직접 조사한다. 작업자에게 분석 대상, 공개 근거와 기준 시각만 전달한다. 계좌·보유 자료는 공유하지 않는다.

각 작업자는 원문 URL, 관측·공개 시각, 핵심 관측, 집계·표본 및 방법의 한계, 반대 근거를 제출하고 코디네이터가 원문과 대조한다. 주장마다 근거 ID 또는 원문 링크와 판단 변경 조건을 붙인다. 발표 전 컨센서스와 증권사·프라임 브로커는 공개 원문을 검증할 수 있는 범위에서 보완한다. 인용 보도에는 매체와 원문 확인 여부를 표시한다. 조건이 없었던 `미실행`과 실행 후 값이 없는 `미확인`을 나누고, 후자는 공개 원문 부재·기준 시각 불일치·이용 조건·공급자 오류 등 사유를 적는다.
