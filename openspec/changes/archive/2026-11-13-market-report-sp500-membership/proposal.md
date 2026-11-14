# Proposal

## 문제

시장 보고서의 S&P 500 시장 폭은 Wikipedia 현재 구성 표를 사용해 출처가 2차 자료이고 구성 기준일이 확인되지 않는다. S&P DJI 전체 구성 자료는 구독 대상이며, iShares의 IVV CSV 경로는 상품 HTML을 반환해 사용할 수 없다.

## 변경 내용

- 무료 공개 SPDR SPY 일별 보유 종목 XLSX를 읽어 시장 폭의 날짜가 있는 ETF 보유 대용치로 사용한다.
- 보유 자료 기준일과 ETF 대용치 출처 종류를 evidence에 기록하고, 공식 S&P 500 지수 구성이 아님을 보고서 라벨과 주석에 표시한다.
- SPY 자료를 가져오거나 검증하지 못하면 기존 Wikipedia 현재 구성 경로로 대체하고 구성 기준일은 미확인으로 둔다.

## 범위 제외

`tradingagents discover --universe sp500` 출처, IWM 발굴 경로, 과거 시점 구성 복원, 유료 S&P DJI 자료, 주문·거래 기능은 변경하지 않는다.
