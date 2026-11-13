## 1. 명세와 구현

- [x] `근거와 한계 표시` 요구사항에 `none_found`와 상태별 판정 규칙을 명시한다.
- [x] 정상적 자료 부재 호출부를 `none_found`로 바꾸고, 조회 실패·미수집은 `unavailable`로 유지한다.
- [x] 다음 거래일 실적 표본 요약과 시장 폭 상태·제외 이유를 정리한다.
- [x] 품질 경고 및 Markdown 상태 집계를 갱신한다.

## 2. 합성 자료 검증

- [x] 정상적 자료 부재와 조회 실패의 상태·경고 차이를 검증한다.
- [x] 실적 요약의 available·partial·unavailable 및 시장 폭 판정을 검증한다.
- [x] Markdown에 '해당 없음' 집계가 표시되는지 검증한다.
- [x] 집중 pytest 검증을 실행한다.
- [x] 전체 pytest와 Ruff 검증을 실행한다(코디네이터 실행: 1812 passed, 2 skipped).
- [x] OpenSpec strict 검증을 실행한다(코디네이터 실행).
