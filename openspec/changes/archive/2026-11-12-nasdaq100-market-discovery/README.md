# Nasdaq-100 유니버스 출처와 검증

## 출처 선택

실행할 때 [Nasdaq-100 구성 종목 공개 목록](https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies)을 요청해 티커 표, 페이지가 표시한 구성 기준일, 종목 수를 함께 검증한다. 이 출처는 공개·무인증이며 호출 때마다 새로 읽으므로 코드에 구성 종목을 고정하지 않는다. 2026-11-12 조사 시 목록은 2026-10-22 기준 101개 증권과 100개 회사를 명시했다.

Nasdaq의 [Global Index Watch 구성·가중치 페이지](https://indexes.nasdaq.com/Index/Weighting/NDX)는 자동화 API에 인증을 요구하고 전체 구성 자료는 로그인 후 제공한다. 따라서 공개 목록은 공식 Nasdaq 피드가 아닌 2차 자료다. 출력에 URL, 별도 구성 기준일, 이 출처 한계를 표시하고, 날짜·보안 종목 수·표가 서로 맞지 않으면 이전 자료를 대신 쓰지 않고 실패한다. 이 목록이 늦게 갱신되거나 형식이 바뀔 수 있으므로 결과의 구성 기준일을 점수 데이터 기준일과 혼동하지 않아야 한다.

## 실행 범위와 한계

- 유니버스 경로는 출처가 공개한 Nasdaq-100 티커만 평가한다. 지수 밖의 미국 주식까지 다뤘다고 주장하지 않는다.
- 기존 Yahoo Finance 및 SEC EDGAR 데이터 헬퍼를 각 구성 종목에 재사용하므로 종목별 공급자 실패와 부분 결과가 생길 수 있다. 전체 구성 결과는 `requested`, `attempted`, `returned`로 구분한다.
- 합성 점수, 종목 간 정렬, 투자 추천, 브로커 호출과 LLM 호출은 없다.
- 테스트는 합성 HTML·팩터 자료와 패치된 HTTP/점수 공급자를 사용한다. 실시간 구성 목록이나 종목 자료를 호출하는 평가는 수행하지 않았다.

## 검증

- 집중 테스트: 42 passed.
- 전체 테스트: 1737 passed, 1 skipped, 103 subtests passed. 최초 샌드박스 실행은 기존 ChatGPT 로그인 테스트의 loopback 바인딩 권한으로 실패했으며, loopback 접근 허용 후 전체 통과했다.
- Ruff 전체 검사: 통과.
- `tradingagents --help`: 통과.
- 변경안 strict 검증: 통과.
- 아카이브 후 specs strict 검증: 15 passed, 0 failed.
