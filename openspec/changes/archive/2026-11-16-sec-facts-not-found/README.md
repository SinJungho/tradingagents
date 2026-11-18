# 검증 기록

- 합성 테스트는 `get_with_retry`가 실제로 던지는 형태(원본 응답 없음, `status_code` 속성)로 404·503을 흉내 낸다. 처음에는 `response` 속성 형태로 흉내 내 통과했지만 실제 SEC에서는 여전히 실패로 잡혀, 실제 예외 형태를 확인해 코드와 테스트를 함께 고쳤다.
- 실제 SEC(2026-11-16): AYA·BIOT는 CIK가 있으나 companyfacts가 404라 "US filer with no XBRL company facts" 자료 없음으로 처리되고, `discover_stocks(['AYA','BIOT'])`의 공급자 실패는 0건(value 보류). AAPL은 재무 사실 정상 조회.
- 전체 pytest 1,854 passed, 1 skipped. Ruff 통과.
- `all` 실패율 재측정은 Yahoo 요청 제한을 고려해 이번에 하지 않았다. 2026-11-15 측정의 같은 실행 로그에 SEC 404가 110줄 있었으므로 실패 93건 중 상당수가 자료 없음으로 바뀔 것으로 예상한다(미측정).
