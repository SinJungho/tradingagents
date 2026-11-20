# 검증 기록

- 공식 별칭 출처: [Brookfield Corporation 주주 FAQ](https://bn.brookfield.com/share-information/faqs). 클래스 A 보통주 티커 BN을 확인했다. 브라우저 조회 결과는 정상 페이지였으나 HTTP 상태 코드는 도구에서 제공되지 않았다.
- 실제 SEC 공개 자료 확인: 2026-11-19 09:58 KST, CIK 1336528, 보고기간 2026-03-31·제출 2026-05-15. 상세 표의 첫 행이 `브룩필드 코퍼레이션 (BN)`으로 표시됐다.
- 합성 회귀 테스트에서 상세 표·신규·미보고 목록 모두 같은 별칭을 쓰고 미등록 발행사는 원문명을 유지하는 것을 확인했다.
- 한계: 등록된 별칭은 Brookfield Corporation 한 건이다. 다른 발행사 이름과 티커는 확인된 매핑이 추가될 때까지 SEC 원문명으로 남는다.
- 검증: 집중 테스트 11개 통과; 전체 pytest 1866 passed, 1 skipped; Ruff 전체 통과; CLI 도움말 통과; OpenSpec strict 검증 통과.
