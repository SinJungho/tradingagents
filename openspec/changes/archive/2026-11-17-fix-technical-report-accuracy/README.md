# 검증 기록

## 확인 및 수정
- 대상: GOOGL 2026-11-13·2026-11-16 기술 분석 HTML/Markdown 및 SVG 15개씩.
- 상대강도 제목에 벤치마크 딕셔너리 전체를 출력하던 오류를 심볼로 수정.
- 순위별 AVWAP가 매번 바뀌는 앵커 시계열을 연결하던 문제를 최신 고정 앵커·확정 이후 시계열로 수정.
- MACD 막대와 선의 날짜 x좌표 불일치, 이동평균 7번째 범례의 화면 이탈 수정. 피보나치·수평선 등 기준선의 이름과 값을 보이는 범례에 추가.
- RSI에 가격 비교 패널 추가. 피벗 기준 판정과 종가 비교 패널의 차이를 명시.
- 선이 존재하면 더 가까운 확정 피벗을 무시하던 시나리오 선택 오류 수정. 차트에 같은 시나리오 경계 표시.
- 11월 16일 저항 후보: 319.51 → 291.59. 지지 후보 277.07 유지. 이는 자동 선택 후보이며 추세 전환 확정 수준이 아님.
- 이동평균 교차 시 종가 위치 조건 누락, 항상 지지에 가깝다고 하는 해석, 항상 깊은 되돌림이라고 하는 해석 수정.
- OBV를 실제 순매도량으로 오해할 수 있는 표현 및 MACD 양수 히스토그램만으로 지속 개선을 암시하는 표현 수정.

## 검증
- 합성 집중 테스트: 31 passed.
- 저장 OHLCV 별도 재계산: SMA 4개, 볼린저 상·하단, 거래량 비율, OBV 20일 변화, RS 기준값·63일 변화, MDD 전체·252일, MACD 히스토그램 등 13개 일치.
- 두 보고서 각각 SVG 연결 15개, XML 파싱 및 비정상 수치 문자열 없음 확인.
- ruff 전체 검사 통과, 설치 CLI --help 통과.
- 최초 샌드박스 전체 테스트: 2020 passed, 7 failed, 1 skipped, 103 subtests passed. 실패 7개는 인증 테스트의 로컬 포트 bind PermissionError.
- 제한 밖 인증 테스트 재확인: 49 passed.
- 최종 전체 테스트: 2027 passed, 1 skipped (langchain_aws 미설치), 103 subtests passed, 24 warnings. 기준선 범례 최종 보완 후 집중 테스트 31 passed 및 ruff 재통과.
- 브라우저 host unavailable로 실제 화면 렌더링 육안 확인은 수행하지 못함. XML 및 좌표 회귀 검사로 대체했으며 시각적 검증 완료로 간주하지 않음.
- 재생성은 _collect_pair를 실패하도록 대체한 상태에서 기존 정상 캐시만 사용. 실브로커·LLM·신규 가격 API 호출 없음.

## 해석 참고 출처
- https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/obv
- https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/macd

원자료 자체의 공급자 정확성 및 기술 지표의 미래 예측력은 이번 검증 범위에 포함하지 않음.
