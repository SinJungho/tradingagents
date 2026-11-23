# 출처 점검 및 검증 기록

2026-11-22 CLI에서 공개 자료를 확인했다. 기본 샌드박스에서는 일부 호스트가 프록시 오류 또는 터널 403을 반환했다. 별도 승인으로 확인한 응답은 기본 경로의 성공으로 세지 않았다. raw 응답과 연락처, API 키는 기록하지 않았다.

| 출처 | CLI 확인 | 관측·공개 시점과 과거 범위 | 이용·저장 조건 및 적용 |
| --- | --- | --- | --- |
| [Yahoo Finance / yfinance](https://ranaroussi.github.io/yfinance/reference/api/yfinance.Ticker.history.html) | 지수·VIX9D·WTI·금·구리 일봉 및 2026-11-20 5분 봉, ES·NQ·ZQ·DXY·TNX·USD/KRW 5분 봉 확인. 2020년 구리 일봉 성공, 2026년 8월 5분 봉 실패 | 5분 봉 시각은 시작 시각이라 완료 시각으로 변환. 일봉 공개의 초 단위 시각, 연속선물 계약월·롤과 당시 수정본 보관은 확인 불가 | 기존 개인용 연결을 재사용. 연속선물 가격 및 관측 구간 거래량 대용치. 미결제약정·잠정 여부·정식 결제와 구분 |
| [Cboe VIX 역사 자료](https://www.cboe.com/tradable_products/vix/vix_historical_data) · [SPX 옵션 통계](https://www.cboe.com/us/options/market_statistics/daily/) | VIX9D 일별 CSV 200. SPX/SPXW 직접 요청 403 | VIX9D CSV는 2011년부터 일자 기반이며 개별 값 공개 시각 없음. 옵션 통계의 SPX+SPXW 범위만 확인 | VIX9D는 기존 시세 경로 사용. SPX 풋/콜 비율은 직접 자동화 미확인 |
| [FRED 이용 조건](https://fred.stlouisfed.org/legal/) · [ALFRED 다운로드](https://alfred.stlouisfed.org/help/downloaddata) · [ICE OAS 이용 조건](https://fred.stlouisfed.org/series/BAMLH0A0HYM2#notes) | DGS5·DFII10 최신 CSV와 날짜 지정 ALFRED 역사 CSV 200. 기존 FRED에서 HY·IG OAS, SOFR·IORB 빈티지 응답 확인 | 빈티지는 날짜 단위. 일별 금리와 스프레드는 전일까지의 스냅샷. 최근 OAS 관측은 2026-11-19 | ICE 수치는 내부 검토용 시장 보고서에 둔다. 외부 모델 입력 및 종목·포트폴리오 상태에는 출처와 공개 범위만 전달한다 |
| [Bitstamp 공개 OHLC](https://www.bitstamp.net/api/) · [Coinbase 시세 약관](https://www.coinbase.com/legal/market_data) | Bitstamp BTC/USD·ETH/USD와 Coinbase BTC의 공개 응답 200. Bitstamp 2026년 8월 지정 5분 봉 검증 | 요청 시작·종료와 UTC epoch, 미완료 제외. 개별 봉 실제 공개 시각 미확인. 단일 거래소 표본 | 개인 사용 공개 Bitstamp API를 사용. 상업 사용은 별도 허가 조건. Coinbase의 모델 사용 제한 때문에 대체 |
| [CME 이용 조건](https://www.cmegroup.com/tools-information/cme-website-terms-of-use.html) · [FedWatch 방법론](https://www.cmegroup.com/articles/2023/understanding-the-cme-group-fedwatch-tool-methodology.html) | 공식 방법론·거래량/OI 안내 확인. 직접 자동 수집 권리·과거 별도 시점별 스냅샷 미확인 | 거래량·미결제약정·결제의 조회 시각과 잠정·확정은 별개 | CME 사이트 자동 수집·모델 이용 조건에 따라 수치 직접 연결 제외. Yahoo ZQ 가격의 내재 월평균만 표시 |
| [CFTC TFF futures only](https://publicreporting.cftc.gov/Commitments-of-Traders/TFF-Futures-Only/gpe5-46if) · [공개 일정](https://www.cftc.gov/MarketReports/CommitmentsofTraders/ReleaseSchedule/index.htm) | 승인된 단독 확인에서 Socrata JSON·일정 HTML 200. 이후 일정 요청 403 | 관측일은 통상 화요일, 공개일은 휴일 등에 따라 변동. 공식 공개 일정·시각을 대조. 역사 데이터의 수정 이력은 확인하지 못함 | 공개 보고치. 보고 대상 선물의 레버리지펀드 장·단 포지션, 해당일 거래자 구분 불가. 일정 요청 실패 시 날짜를 추정하지 않음 |
| [ICI 주간 ETF 순발행](https://www.ici.org/research/statistics/etfs/weekly-estimated-etf-net-issuance) | CLI 403. 공개 페이지에 주간 추정 보고서와 XLS 링크 | 게시 일자는 확인 가능하나 정확한 시각과 과거 배포본 보관 불확실 | 분류별 순발행 추정의 정의를 인용. 직접 연결 미확인 |
| [BLS](https://www.bls.gov/bls/news-release/) · [BEA](https://www.bea.gov/news/schedule/full) · [FOMC](https://www.federalreserve.gov/monetarypolicy/materials/) | BLS 아카이브 200(기존 연락처 User-Agent), BEA 일정·발표 HTML 200, Fed 발표 HTML 200 | 원문의 문서 날짜·엠바고 시각과 당시 수치만 사용. BEA 현재 일정은 과거 모든 발표의 부재를 입증하지 않음 | 공식 발표의 당시 수치와 확인된 수정치 인용. 시각이 검증된 발표 전 컨센서스는 원문 조사로 보완 |
| [뉴욕 연은 SOFR](https://www.newyorkfed.org/markets/reference-rates/additional-information-about-reference-rates) · [ACM 기간 프리미엄](https://www.newyorkfed.org/research/data_indicators/term-premia-tabs) | SOFR JSON 및 ACM HTML 200 | SOFR 다음 영업일 발표 및 당일 수정 시간차. ACM 현재 역사 모델 시계열은 당시 배포본 공개 시점 불명 | SOFR와 IORB는 같은 관측일의 안전한 FRED 빈티지로 비교. ACM은 원문 조사에서 당시 공개본이 확인되면 인용 |
| [SEC EDGAR](https://www.sec.gov/edgar/search/) · [연준 SLOOS](https://www.federalreserve.gov/data/sloos.htm) | 기존 SEC 접수 시각·항목 확인 경로 재사용 | SEC acceptanceDateTime 및 SLOOS 공개 날짜를 해당 시점과 대조 | 공식 자료. SEC 기업 표본과 공시 내용 범위를 구분. 업종 전망 수정과 기관별 수급 추정은 공개 원문이 있을 때만 보완 |
| [미 재무부 입찰 결과 API](https://fiscaldata.treasury.gov/datasets/treasury-securities-auctions-data/treasury-securities-auctions-data-updated/) · [연준 Kim–Wright](https://fred.stlouisfed.org/series/THREEFYTP10) | 구형 재무부 API 날짜 필터 JSON 200(2025-09-10 행 확인). Kim–Wright의 2026-11-19 빈티지에서 11-13 관측 확인 | API 결과의 시각이 없어 전일 이전 자료만 사용. 기간 프리미엄은 관측일·빈티지를 명시하는 모형 추정치 | 공식 입찰과 FRED 빈티지 사용. ACM과 Kim–Wright 방법 차이 표시 |

## 공개 자료 CLI 실행

- `market-report`를 `--no-llm`으로 실행해 `results/market-reports`에 저장했다.
- 대상 2026-11-20 20:00 ET. 2026-11-22 03:15 ET에 다음 개장 전 실행했다. 검증된 공개 GET을 위해 승인된 네트워크 실행을 사용했다. 동일 머신의 공급자 캐시는 초기화하지 않았다.
- 첫 실행 산출물 `results/market-reports/2026-11-20-acbc2a4bcfd04aea847104e3133f8985/{report.md,report.html,evidence.json}`
- 상태는 확인 206, 부분 확인 4, 해당 없음 8, 미확인 8로 불완전 보고서였다. 실제 LLM과 브로커 호출은 없었다.
- 가격·업종·SPY 대용치 시장 폭(분할 1종목 제외), FRED 명목·실질금리, WTI·금·구리의 세 구간, Bitstamp BTC·ETH의 세 구간을 확인했다. 목요일 OAS 양쪽, 연준 기간 프리미엄 추정, SLOOS, SOFR–IORB, 시각을 일치시킨 SPY 원화 성과도 확인했다. 주간·주식·금리·금융 스트레스 조사가 열렸고 대상 네 발표의 반응 조사는 미실행이었다.
- ES·NQ·ZQ는 연속선물 가격과 관측 구간 거래량을 확인했다. SPX 풋/콜, 미결제약정·계약월·잠정치, FedWatch 회의별 확률, ICI 및 공개 원문을 검증하지 못한 조사 항목은 사유와 함께 남겼다. 정규장 마감 이후 자료가 종목 경로에 섞이지 않는지는 합성 테스트에서 별도로 검증했다.
- 같은 대상일의 07:01 ET 재실행에서 재무부 11월 18일·19일 중장기 국채 입찰 결과를 확인했다. CFTC 일정 HTML의 중첩 제목을 처리하도록 수정하고 합성 테스트를 통과했다. 재실행 및 단독 재확인의 HTTP 403은 공급자 실패로 남겼다.
- 재실행 산출물 `results/market-reports/2026-11-20-06d5cf79a19e44398a90c9babedfb015/{report.md,report.html,evidence.json}`. 확인 196, 부분 확인 5, 해당 없음 7, 미확인 8.

## 개발 검증

- 집중 테스트 200건 통과. 금요일 암호자산 마감, 조기 폐장, 롤 정보가 없는 연속선물, 정정본 제외, 과거 빈티지, 체크포인트 재개, 심층 포트폴리오 스냅샷 공유, 평시·발표·급변·공급자 실패, 두 관점의 출력 검증을 포함한다.
- 전체 pytest에서 1,991건과 하위 검사 103건이 통과했다. `langchain_aws` 미설치로 Bedrock 테스트 한 건을 건너뛰었고 경고는 24건이다. 처음 실행에서 테스트에 주입된 SOCKS 프록시와 로컬 콜백 제한으로 일부가 실패했다. 테스트 프로세스에 한해 프록시 환경변수를 제외하고 로컬 콜백을 열어 재검증했다.
- 전체 Ruff, CLI 도움말, OpenSpec 변경안 strict 검증을 통과했다.
