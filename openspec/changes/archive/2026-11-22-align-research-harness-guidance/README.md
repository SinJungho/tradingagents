# 합성 요청 검증

아래 요청과 도구 반환값을 가정해 AGENTS.md의 경로, 프로젝트 스킬의 절차, OpenSpec의 기대 결과를 대조했다. 차트 구현의 CLI 계약은 `chart-zones-tratto-integration`을 참조했다. 이 사례 검토에서 브라우저 탭을 변경하거나 실계좌·LLM을 호출하지 않았다.

| 합성 요청·관측 | 선택한 경로 | 판정 |
| --- | --- | --- |
| “QQQ 일봉 지지·저항 알려줘.” 종가 102, 구간 100~104 | `tratto-chart` → `chart-zones --tickers QQQ --json` | 계산 기준일·가격 기준과 구간 근거를 보고한다. 종가가 104를 넘는 조건과 100을 밑도는 조건을 각각 다루고 드로잉은 변경하지 않는다. |
| “QQQ 가격 구간을 검증하고 차트에 표시해줘.” CSV 대조 `ok`, 좌표·캡처·재열기 확인 | `chart-zones` → `chart-check` → Tratto 표시 | 실제 대상 탭의 종목·주기·기존 객체를 확인한다. 계산 좌표로 표시한 뒤 변경 전후 `read_drawings`와 재열기 결과를 `drawings.json` 및 캡처에 남기고 완료로 보고한다. |
| 같은 검증·표시 요청에서 OHLC가 다르고 재조회 후에도 `mismatch` | `chart-check` 재실행에서 중단 | 불일치와 미완료를 보고하고 드로잉은 추가하지 않는다. |
| 같은 구간 표시를 다시 요청. 기존 사각형의 날짜·가격 좌표가 같음 | `chart-check` → `read_drawings` | 이전 라벨이 달라도 기존 객체를 재사용한다. 새 객체를 만들거나 기존 객체를 삭제하지 않는다. |
| 표시 직후 좌표는 일치했지만 실제 탭을 다시 열자 사각형이 없음 | `read_drawings`와 재열기 캡처 대조 | 좌표 대조 성공과 표시 복원 실패를 기록하고 드로잉은 미완료로 보고한다. |
| `chart-check=ok`, 재열기 후 드로잉 확인, 백테스트 `inconclusive` | `tratto-chart` → 데이터·드로잉·통계 결과 확인 | 데이터 일치, 드로잉 확인, 통계적 예측력 미확인을 각각 보고한다. |
| “QQQ 5년 일봉의 장기·최근 추세선을 표시해줘.” | `tratto-chart` 5년 일봉 경로 | 거래일과 OHLCV 검증 후 전후 5봉 피벗에서 앵커를 산출한다. 대상 탭 재열기 확인 후 완료 판정한다. |
| “QQQ 차트에서 구간이 맞는지 확인해줘.” | `chart-zones` → `chart-check` | 데이터 대조 상태를 보고하고 드로잉은 변경하지 않는다. |
| “미국장 마감 자료만 보여줘.” 지수 상승, 시장 폭 `unavailable` | 동부시간 20시 기준 거래일 확인 → `market-report --no-llm` | 확인한 판단·근거와 변경 조건을 먼저 제시한다. 상승 확산 판단을 유보하고 보고서 경로를 연결한다. |
| “보유 종목만 조회해줘.” | `portfolio-check` → `portfolio live --no-scenarios` | 자료 기준 시각과 보유를 보고한다. 시나리오와 LLM 호출은 생략한다. |
| “QQQ 종합 분석해줘. 기술적 분석도 포함해줘.” | `stock-scenario` → `--ticker`와 Market Analyst | 종합 판단 경로를 사용한다. |
| “QQQ 비중을 늘릴까?” 평가액 미확인 또는 보유 JSON 지정 | `stock-scenario` → `portfolio live --symbol QQQ` 또는 지정 JSON의 `--portfolio` | 해당 보유 기준으로 판단하고 평가액 미확인 시 비중 조정 수치를 유보한다. |
| “두 종목의 팩터를 비교해줘.” | `stock-discovery` → `discover --tickers` | 결정론적 팩터 결과를 보고하고 선택한 후보에만 종목 분석을 적용한다. |
| “지지·저항 구간의 과거 예측력을 검증해줘.” | `backtest-eval` → `zone-backtest run --period validate` | 평가 상태와 표본 한계를 보고한다. |

## 실행 검증

- 훅·차트·구간 백테스트·출력 품질·미국장·포트폴리오 집중 테스트는 212개 통과했다.
- 전체 pytest는 로컬 콜백 바인딩을 허용한 실행에서 1,991개 통과, 1개 건너뜀(`langchain_aws` 부재), 경고 24개, 하위 테스트 103개 통과였다.
- Ruff, 설치된 CLI 도움말, OpenSpec 변경 strict 검증을 통과했다.
- 아카이브 후 OpenSpec 최종 명세 18개와 진행 중인 차트 구현 변경의 strict 검증을 통과했다.
