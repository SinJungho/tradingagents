---
name: tratto-chart
description: 미국 종목의 차트·기술적 분석, 일봉 지지·저항, 5년 OHLCV·피벗·추세선을 분석한다. 사용자가 차트 검증·표시를 요청하면 Yahoo Finance의 Tratto에서 chart-check 및 read_drawings로 검증한다.
---

# Tratto 차트 운영

- 미국 종목의 일봉 가격 구조·지지·저항은 `tradingagents chart-zones --tickers <T> --json`으로 시작한다. 계산에는 [chart-zones v1 계약](references/chart-zone-params.md)을 적용한다. 가격 구간의 차트 대조나 표시 요청은 [운영 절차](references/operations.md)를 따른다.
- 최근 5년 OHLCV, 전후 5봉 피벗, 장기·최근 추세선 분석 요청은 [5년 일봉 분석](references/five-year-ohlcv.md)을 따른다. 검증된 Tratto 원자료에서 Python으로 구간과 추세선 앵커를 계산한다.
- 보조 도구 12개는 [사용·정리 기준](references/operations.md#4-보조-도구-선택)에 따라 고른다. 기존 항목도 현재 질문과 설정을 검토한 뒤 재사용하고 정리 후보와 실제 화면 상태를 기록한다. 표시 범위는 분석 범위와 별도로 정한다.
- Tratto가 필요한 경로는 사용 중인 Yahoo Finance 탭과 [MCP 연결 소유 세션](references/operations.md#mcp-서버-연결)을 확인한다. 포트를 쓰는 이전 Tratto 작업을 정리한 뒤 현재 세션에서 연결한다. [도구 카탈로그](references/tool-catalog.md)를 실제 MCP schema와 대조하고, 대상 차트에서 `get_drawing_guide`와 `read_drawings`를 먼저 확인한다.
- 종목·봉 주기·기준 거래일·가격 조정 기준을 확인한다. 가격 구조·추세·거래량을 먼저 보고 질문에 필요한 보조지표만 고른다. 검증된 데이터에서 경계와 앵커를 계산하고, 현재가를 포함하는 구간은 상단·하단 이탈 조건을 각각 설명한다.
- 분석만 요청받으면 계산 근거와 결과를 보고한다. 검증만 요청받으면 데이터 대조 결과까지 보고한다. 드로잉 변경은 표시 작업을 요청받은 범위에서 수행한다.

## 안전 규칙

- Tratto 설정, 계좌, 주문은 다루지 않는다. 브로커 조회나 주문 도구를 호출하지 않는다.
- 드로잉·지표·비교 시리즈의 삭제는 사용자가 삭제를 명시한 범위에서만 수행한다. 다른 날짜의 `tc-`와 수동 드로잉도 명시된 대상만 삭제한다. 대상 차트에서 같은 종류와 날짜·가격 좌표의 객체는 재사용한다.
- 해당 경로의 데이터 검증을 통과하고 날짜·가격 앵커를 확인한 뒤 그린다. [드로잉 완료 기준과 증거](references/operations.md#5-완료-검증과-보고)에 따라 실제 사용자 탭의 캡처, 변경 전후 MCP 조회, 가격·날짜를 뒷받침하는 원자료 또는 계산 근거를 모두 남긴다. 다시 열어도 표시가 유지되는지 확인한 결과만 완료로 보고한다.
- 추가·재사용한 구간과 추세선은 [버전 1 기록 형식](references/operations.md#추가재사용-증거-검사)으로 보존하고 `tradingagents chart-drawings-check --drawings <drawings.json> --json`으로 완료 증거를 검사한다.
- 화면 드로잉 수가 저장본보다 많거나 라벨이 잘리면 [중복 표시와 재로딩](references/operations.md#중복-표시와-재로딩)과 [화면 표시 범위와 라벨](references/operations.md#화면-표시-범위와-라벨)을 따른다. 차트를 마우스로 끌지 않는다.
- `snapshot.csv`는 CLI 검증 입력으로만 사용한다. Tratto 원문 CSV는 보존하고 Python 분석에는 별도 작업 사본을 사용한다.
