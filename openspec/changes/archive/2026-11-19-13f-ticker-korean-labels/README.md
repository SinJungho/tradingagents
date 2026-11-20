# 검증 기록

- OpenFIGI 출처 점검: 2026-11-19 키 없이 POST 200, `037833100`→`AAPL`, `11271J107`→`BN`. 2차 출처라 13F 주석에 공식 아님을 밝힌다.
- 실제 자료 확인(2026-11-19 13:42 KST): Berkshire·Pershing Square·Bridgewater·Duquesne 상세 표와 신규·미보고 목록이 `애플 (AAPL)`, `브룩필드 코퍼레이션 (BN)`, `RESTAURANT BRANDS INTL INC (QSR)`, `아마존 (AMZN) CALL` 형식으로 표시됐다.
- 한계: `CHUBB LIMITED`, `Seagate Technology Hldngs Pl`, `TEVA PHARMACEUTICAL INDS LTD`처럼 미국 거래소 티커가 하나로 확인되지 않은 CUSIP은 원문명으로 남는다.
- 검증: 집중 테스트 13개 통과, 전체 pytest 통과, Ruff 통과, CLI 도움말 통과, OpenSpec strict 검증 통과.
