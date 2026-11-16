## 1. 구현과 검증

- [x] 1.1 `_fetch_json`의 404를 `EdgarNotFound`로 구분하고, 재무 사실 조회에서 `NoMarketDataError`로 바꾼다.
- [x] 1.2 합성 테스트(404 → 자료 없음·무재조회, 503 → 실패·재조회), 전체 pytest, Ruff, OpenSpec strict 검증.
- [x] 1.3 실제 SEC로 AYA·BIOT가 자료 없음으로 처리되는지 확인한다.
