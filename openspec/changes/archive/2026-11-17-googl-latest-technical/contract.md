# 공통 계약
기존 chart_eval.indicators.compute_indicators(bundle, benchmark), generate_candidates(bundle, rows, as_of)와 일봉 bundle 계약을 재사용한다. 기존 함수 반환은 호환성을 유지한다.
A 소유: tradingagents/chart_eval/latest_indicators.py 및 tests/test_latest_indicators.py (필요시 indicators.py의 호환 버그 수정 가능).
A 공개 함수 analyze_latest(bundle, benchmark=None) -> dict: rows(기존 형식), candidates(전체 .25 후보), selected_candidates(차트 표시용), sensitivity, gaps(해소 포함), moving_averages(기울기/최근교차), anchors(각 side의 고정 최신 피벗과 date/value 시계열), latest(마지막 row). 추가 키 허용. 후보 선택은 kind/side별 최대3, 기준가 ATR 거리→접점수 내림→접점범위 내림→ID. Fibonacci 5개 모두 유지. gap 전체 보존. 차트에 필요한 좌표는 기존 candidate 구조. 모든 날짜 ISO.
B 소유: tradingagents/chart_eval/latest_artifacts.py 및 tests/test_latest_artifacts.py.
B 공개 함수 write_latest_artifacts(run_dir, *, bundle, benchmark, analysis, summary) -> dict[path]: 종합/구조/보조 SVG 또는 PNG와 report.html 및 JSON/CSV. summary.report_markdown을 report.md 본문으로 사용(없으면 기본 설명). HTML은 보고서와 3차트 및 선 표를 포함. B는 A 함수 구현에 의존하지 말고 합성 계약을 만들어 테스트.
코디네이터 소유: latest_runner.py, data.py, runner.py, CLI, 통합 테스트, OpenSpec 및 실데이터 산출물. 공통 변경 필요시 메시지로 요청.
모든 worker는 합성 자료만 사용. .env/.env.bak·자격증명·계좌 원자료 접근 금지. 실브로커/실LLM/외부 HTTP 금지. 전체 테스트는 코디네이터가 통합 후 한 번 수행.

최근 캐시 연장 시 요청 시작일의 바를 포함하는 정상 Toss 번들만 재사용한다. 새 종료일의 한 페이지에서 겹치는 기존 날짜를 OHLCV exact match로 검증하고, 일치한 봉은 중복 추가하지 않는다. 충돌은 오류로 남기며 이력 종료나 다른 출처로 취급하지 않는다.
