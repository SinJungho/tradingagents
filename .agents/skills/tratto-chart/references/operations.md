# 구간 확인 및 차트 표시 절차

## 1. 결정론적 구간 생성

사용자가 선택한 종목(최대 10개)에 대해 실행한다.

```bash
tradingagents chart-zones --tickers AAPL,MSFT --json
```

결과에서 각 ticker의 `as_of`, `status`, `run_dir`, `snapshot_sha256`, `check_windows`, zone의 경계·touch points 및 통계 validation 상태를 읽는다. `status != ok`인 종목은 드로잉 대상에서 제외하고 실패 이유를 기록한다. CLI의 `run_dir`에 `zones.json`과 `snapshot.csv`가 있다. 이 skill은 `snapshot.csv`를 직접 열지 않는다.

분석 전용 요청은 계산 결과와 근거를 보고하는 것으로 마친다. 가격 구간 대조 요청은 2절까지, 표시 요청은 대조 결과가 `ok`일 때만 3절과 5절까지 진행한다.

## 2. Tratto 차트 준비 및 검증

종목마다 실제 MCP tool schema를 먼저 확인한 뒤 다음 작업을 수행한다.

Tratto 도구가 현재 세션에서 제공되지 않거나 연결이 실패하면, [MCP 서버 연결](#mcp-서버-연결)의 소유 세션 확인·현재 세션 연결 절차를 먼저 마친다. 연결을 복구할 수 없으면 쓰기를 멈춘다. Yahoo URL hash, base64 레이아웃, 브라우저 저장 상태를 직접 편집하거나 CUA 좌표 클릭·드래그·삭제키로 Tratto 쓰기를 대신하지 않는다. 데이터·탭을 읽은 범위와 연결 실패 단계를 기록하고 차트 변경은 미완료로 보고한다.

1. [MCP 서버 연결](#mcp-서버-연결)을 먼저 확인한다. 사용자 탭에서 대상 ticker를 확인해 재사용한다. 탐색이 필요하면 `open_chart`를 쓴다. `get_drawing_guide`와 `read_drawings`를 먼저 확인한다.
2. 실제 schema를 확인하고 `set_periodicity(interval=1, timeUnit="day")`로 일봉을 지정한다.
3. `set_range`로 `check_windows`의 가장 이른 날짜부터 최신 날짜까지 표시한다.
4. `get_chart_summary`로 ticker, 주기, 로딩 범위가 맞는지 확인한다. 범위 변경으로 주봉이 되면 일봉을 다시 지정하고 대조 대상 봉이 로딩됐는지 확인한다.
5. 각 check window에 대해 `get_chart_data`를 호출한다. `max_points`는 전달하지 않는다. 실제 응답 schema에서 CSV 본문을 확인한 뒤 각 `date,o,h,l,c,v` 블록을 원문 그대로 보존한다. 여러 window는 `check_windows` 순서로 빈 줄만 사이에 두고 연결한다. 겹치는 날짜도 window별 블록에 그대로 둔다. 날짜별 합치기, 중복 행 제거, 값 편집·반올림은 하지 않는다.
6. CLI 입력 CSV는 `<run_dir>/chart_check.csv`에 저장하고 다음을 실행한다.

```bash
tradingagents chart-check --run-dir <run_dir> --chart-csv <run_dir>/chart_check.csv --json
```

일봉 타임스탬프가 확인된 브라우저 현지 날짜로 직렬화됐으면 `--chart-timezone`에 그 IANA 시간대를 넘긴다. 서울 환경의 예는 `--chart-timezone Asia/Seoul`이다. CSV 원문을 그대로 전달한다.

날짜 범위가 부족하면 `set_range`를 넓히고 각 window를 한 번 다시 조회한다. `mismatch` 또는 `date_mismatch`면 `get_chart_data`를 한 번 더 호출해 CSV 블록을 새로 저장하고 `chart-check`를 재실행한다. CLI가 `chart_check.csv`를 별도 보존하고, `chart_validation.json`은 각 시도 결과와 횟수를 기록한다. 손으로 수치를 수정하지 않는다. 재시도 결과가 `ok`가 아니거나 `insufficient`/`unknown`이면 종목을 미완료 처리하고 드로잉하지 않는다.

## 3. 드로잉 및 앵커 확인

1. `get_drawing_guide`를 읽고, 현재 MCP schema에서 필요한 색상, 날짜, 가격, ID 필드 형식을 확인한다.
2. `read_drawings`로 대상 종목·주기의 기존 객체를 확인한다. 같은 종류와 날짜·가격 좌표에 요청된 스타일이 맞으면 재사용한다. 색·실선·연장 변경은 같은 역할의 이전 객체만 교체한다. 삭제는 명시된 대상에만 적용한다.
3. 출력된 날짜·가격을 그대로 사용한다. support는 낮은 계열 색, resistance는 높은 계열 색, inside는 중립색 점선으로 표시한다. 사각형의 날짜 범위는 첫 touch date부터 마지막 확인 봉까지다. inside에는 `break_above`와 `break_below`를 함께 표시하고 단일 invalidation을 만들지 않는다.
4. 각 드로잉에 `tc-<as_of>-<type>-<rank>` 형태의 label 식별자를 붙인다. 가격선에는 가격을 포함한 화면 표시 라벨도 연결한다. 식별자만 있거나 축의 가격 태그만 보이는 것은 화면 라벨을 붙인 것으로 간주하지 않는다. 실제 tool schema의 식별자/anchor 형식이 다르면 schema를 따르며 변환된 값과 결과를 기록한다. 모델은 좌표를 재계산하거나 반올림하지 않는다.
5. `read_drawings`를 다시 호출해 각 drawing ID와 실제 start/end date·price가 CLI 출력과 일치하는지 비교한다. 불일치면 완료로 표시하지 않고 `drawings.json`에 실패와 관찰값을 남긴다.
6. `<run_dir>/drawings.json`에 chart-check 결과, 시도 횟수, 표시한 zone labels, drawing IDs, anchor 비교 결과를 기록하고 [같은 탭에서 완료 여부를 검증한다](#5-완료-검증과-보고). `chart-drawings-check` 종료 코드가 0일 때만 완료로 보고한다.

역할별 색을 요청하면 현재 차트의 색을 조사해 팔레트를 정한다. 역할이 같은 수평선과 라벨 테두리는 같은 색으로 맞추고, 회복선·재시험 구간·분할 기준·추세선처럼 다른 역할에는 다른 색을 쓴다. 사용자 지정 색·모양과 기존 의미를 우선한다. “수평선과 추세선만”이라면 그 종류만 추가하고 이미 보존하기로 한 라벨은 유지한다.

### 시각적 정리와 라벨 배치

- 불필요한 객체는 현재 차트의 질문과 요청된 표시 역할에 기여하지 않는 박스·선·지표를 뜻한다. 변경 전 화면과 `read_drawings`, 저장본을 대조해 대상의 종류·가격·날짜·라벨을 특정한 뒤 요청된 범위에서만 정리한다. 요청된 기준 가격, 회복 기준, 장기 추세선과 연결 라벨은 보존한다.
- 수평 기준선, 회복선, 장기선 등 서로 다른 역할에는 서로 다른 색상 계열을 쓴다. 파랑과 하늘색처럼 색상 코드가 달라도 화면에서 비슷해 보이는 조합이나 같은 계열의 명도·채도 차이만으로 역할을 구분하는 조합은 피한다. 예를 들어 하늘색 지지선과 함께 표시하는 장기 추세선에는 자홍색처럼 한눈에 구분되는 색을 쓴다. 연결 라벨은 선과 같은 색으로 표시하고 가격을 문구에 적는다. 라벨이 겹치거나 선·축에 가려지거나 화면 오른쪽에서 잘리면 가격 앵커를 바꾸지 않고 차트 안쪽의 날짜로 옮긴다. 비슷한 높이에 라벨이 여러 개면 날짜를 엇갈리게 배치해 서로 가리지 않게 한다.
- 완료 전에 실제 화면에서 박스·보조선이 요청 범위 밖에 남았는지, 선과 라벨이 역할·가격에서 맞는지, 라벨이 모두 읽히는지 확인한다. 실제 차트를 다시 연 뒤 선이 교차하거나 가까이 붙은 곳에서도 역할별 색이 한눈에 구분되는지 캡처에서 확인한다. 유사하게 보이면 색을 바꾸고 다시 확인한다. 변경 전후 조회와 재열기 조회에서 요청된 객체만 한 벌씩 표시되는지 대조한다.

## 4. 보조 도구 선택

먼저 분석 질문과 시간축을 정한다. 일반적인 가격 구조 분석은 검증된 지지·저항, 추세선, 필요한 거래량부터 본다. 지표마다 **어떤 질문에 답하는지, 어떤 봉·기간·앵커를 쓰는지, 해석에 무엇을 더하는지** 확인한다. 같은 질문에 답하는 지표가 겹치면 해석에 직접 쓰는 것부터 표시한다. 전체 12개를 요청받으면 모두 검토하고 분석과 표시 결과를 항목별로 기록한다.

아래 기본값은 출발점이다. 출처는 투자자·트레이더가 쓰는 해석과 설정을 설명한다. 정리 후보 기준은 그 해석을 현재 Tratto 화면에 적용하는 운영 규칙이다. 신호의 성과를 주장할 때는 종목·기간별 표본 외 검증과 거래비용을 확인한다. 여러 설정 중 사후에 잘 맞는 조합을 골랐다면 그 선택이 성과에 미친 영향을 검토한다. [Sullivan·Timmermann·White의 기술적 매매 규칙 연구](https://eprints.lse.ac.uk/119144/1/dp303.pdf)

| 항목 | 사용 조건과 관찰 근거 | 표시 제외·삭제 후보 조건 |
| --- | --- | --- |
| 이동평균 | 가격과 평균선의 위치, 평균선의 기울기로 추세를 읽는다. 최근 가격에 민감한 기준이 필요하면 일봉 EMA 20·50 중 질문에 맞는 기간을, 장기 추세에는 일봉 SMA 200을 검토한다. [Fidelity EMA](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/ema/) · [Fidelity SMA](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/sma) | 분석 기간과 선의 기간이 어긋나거나 같은 추세를 설명하는 선이 겹치면 정리 후보다. 횡보 중 반복 교차는 추세 신호로 채택하지 않는다. |
| RSI 다이버전스 | 추세가 둔화되는지 확인할 때 RSI 14와 대응하는 확정 가격 피벗 두 개를 비교한다. 70·30은 참고 수준이며 강한 추세에서는 오래 머물 수 있다. 아래 앵커 규칙을 따른다. [Fidelity RSI 사용법](https://www.fidelity.com/viewpoints/active-investor/how-to-use-rsi) · [Fidelity 지표 함수 가이드](https://www.fidelity.com/products/atp/content/wsFuncRef_US.pdf) | 피벗이나 대응 RSI 값이 틀렸거나, 새로 확인된 피벗을 포함해 평가했을 때 기존 괴리가 해소됐거나, 해당 스윙 분석이 끝나면 그 선이 정리 후보다. 모멘텀 질문도 남지 않으면 RSI 패널을 함께 검토한다. |
| 거래량·OBV | 돌파·반등 봉의 Volume을 같은 주기·세션의 직전 통상 거래량과 비교한다. 예를 들어 직전 완료 20봉 평균을 쓸 수 있다. 여러 봉에 걸친 거래 참여를 볼 때는 OBV의 기울기와 가격의 고점·저점 변화를 비교한다. [Fidelity 거래량 활용](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/what-is-technical-analysis) · [Fidelity OBV](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/OBV) | 거래량 데이터가 누락되거나 세션 기준이 섞이면 해당 해석과 표시를 제외한다. 단일 돌파의 거래량 막대로 질문이 해결되면 OBV가 정리 후보다. |
| 피보나치 되돌림 | 확정된 스윙의 조정 깊이를 볼 때 해당 고점·저점에 `draw_fib`를 고정한다. 38.2%·50%·61.8% 등은 관찰 가격대다. 실제 가격 반응이나 검증된 구간과의 겹침을 확인한다. [Schwab 피보나치 되돌림](https://www.schwab.com/learn/story/using-fibonacci-retracement-levels-on-thinkorswim) | 앵커가 불명확하거나 스윙 시작점이 침범되어 계산 결과가 무효화되거나, 분석 대상 스윙이 바뀌면 정리 후보다. |
| 수평 지지·저항 | 반복 반응한 피벗의 가격대를 검증하고 `draw_rectangle`으로 표시한다. 경계는 장중 꼬리와 종가 이탈을 구분해 읽고, 역할 전환은 이탈 후 재접근에서의 반응을 확인한다. [Fidelity 가격 구조](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/what-is-technical-analysis) · [Fidelity 차트 교육 세션](https://media.fidelity.com/assets/Fidelity.com_VMS/754/947/TA_Session_1_Transcript.pdf) | 앵커·가격 기준이 틀렸거나 같은 날짜·좌표의 구간이 겹치면 정리 후보다. 돌파한 구간은 역할 전환을 평가한 뒤 현재 질문에 유효한지 판단한다. |
| MACD | 추세장 모멘텀의 강화·둔화나 변화를 볼 때 12·26·9 기준으로 MACD와 신호선 교차를 보고, 0선 위치 및 가격 추세와 함께 해석한다. [Fidelity MACD](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/macd) | 횡보 중 잦은 왕복 교차로 판단에 기여하지 않거나 RSI가 같은 모멘텀 질문을 이미 해결하면 정리 후보다. |
| ADX/DMI | 추세 추종과 박스권 중 어느 해석이 맞는지 볼 때 14봉 기준 ADX의 수준·기울기로 강도를, +DI와 −DI로 방향을 읽는다. 20 미만·25 초과는 통상적 참고 수준이며 그 사이는 맥락을 확인한다. [Fidelity ADX](https://www.fidelity.com/viewpoints/active-investor/average-directional-index-adx) · [Fidelity DMI](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/dmi) | 추세 강도 분류가 현재 판단에 쓰이지 않으면 정리 후보다. 낮은 ADX 자체는 박스권을 살피는 근거가 될 수 있다. |
| Anchored VWAP | 확정 스윙이나 실적 같은 사건 이후의 거래량 가중 평균가가 필요할 때 사용한다. 해당 봉과 선택 이유를 기록하고 가격이 이 기준을 회복·유지하는지 관찰한다. 아래 앵커 규칙을 따른다. [Brian Shannon의 적용 사례](https://alphatrends.net/archives/brian-shannon-highlights-key-5-day-sma-and-vwap-support-levels/) · [StockCharts AVWAP](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/anchored-vwap) | 사건 시각·앵커가 틀렸거나 그 사건이 현재 질문과 무관해졌거나 같은 앵커가 겹치면 정리 후보다. 평균가를 한 차례 넘었다는 이유만으로 정리하지 않는다. |
| 볼린저 밴드 | 변동성 수축·확장을 볼 때 20봉·2표준편차를 출발점으로 밴드 폭의 최근 변화와 종가의 위치를 읽는다. 추세에서는 가격이 한쪽 밴드를 따라갈 수 있다. [John Bollinger의 사용 규칙](https://www.bollingerbands.com/bollinger-band-rules) | 변동성 국면을 묻지 않거나 해당 질문이 ATR 수치로 해결되면 패널·오버레이가 정리 후보다. 밴드 접촉만으로 되돌림 신호를 채택하지 않는다. |
| ATR | 갭을 포함한 평소 변동 폭과 비교해 구간 폭, 이탈 거리 또는 위험 폭을 해석할 때 Wilder ATR 14를 쓴다. 가격 단위와 배수를 명시한다. [Fidelity ATR](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/atr) | 최신 ATR 몇 개의 값만 해석에 쓰면 차트 패널은 정리 후보다. 가격 변동의 방향을 판별하는 용도로 표시하지 않는다. |
| 거래량 프로파일 | 특정 박스권·스윙·사건 기간에서 거래가 집중된 가격대를 찾을 때 `draw_volume_profile`을 쓴다. 시작·종료일과 가격 구간 수를 명시하고 데이터 해상도와 세션 범위를 확인한다. 엔진이 값을 제공하면 거래량이 가장 많은 가격대(POC)와 가치 영역(VA)을 읽고, 확인하지 못한 수치나 엔진 계산 방식을 추정하지 않는다. [TradingView 거래량 프로파일 개념](https://www.tradingview.com/support/solutions/43000502040-volume-profile-indicators-basic-concepts/) · [TradingView 고정 범위 예시](https://www.tradingview.com/support/solutions/43000480324-fixed-range-volume-profile-indicator/) | 날짜 범위의 분석 근거가 없거나, 현재 질문이 가격 피벗 구간에 한정되거나, 같은 기간·구간 수 설정이 겹치거나, 캔들·가격 구간을 가리면 정리 후보다. |
| 상대강도 | 시장·섹터 대비 성과를 묻는 경우 같은 날짜와 가격 조정 기준으로 종목 종가 ÷ 벤치마크 종가의 방향을 본다. 전체 시장은 SPY, 업종은 비교 목적에 맞는 지수·ETF를 선택한다. 가격 구간 표시를 위해 절대 가격 축이 필요하면 별도 보기에서 비교한다. [StockCharts Price Relative](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/price-relative-relative-strength) | 벤치마크가 질문에 맞지 않거나 기준일이 맞지 않거나 상대 성과를 묻지 않으면 정리 후보다. 퍼센트 축이 가격 드로잉을 가리면 별도 보기로 옮기거나 표시를 제외한다. |

### 기존 표시와 삭제

1. `list_indicators`로 지표 이름·주기·입력값과 활성 상태를, `read_drawings`로 드로잉 종류·앵커·ID 또는 식별값을 확인한다. 현재 질문에 필요하고 설정과 좌표가 맞는 항목을 재사용한다. 자료나 도구 접근이 부족하면 적용하지 않은 이유를 남긴다. Yahoo 메뉴에서 사용할 수 있는 지표는 화면에서 같은 설정을 확인한 뒤 사용할 수 있다.
2. 정리 후보는 분석 결론에서 제외한다. 화면 정리를 요청받으면 사용 중인 보기에서 복구 가능한 숨김을 확인해 사용한다. 대상만 숨기고 원본을 보존하는 기능이 없으면 별도 보기나 결과 기록에 남긴다. 기존 표시가 화면에 남아 있으면 항목과 이유를 보고한다.
3. 실제 삭제는 사용자가 삭제를 명시한 범위에서만 수행한다. 지표는 활성 목록의 고유한 이름·설정, 비교 시리즈는 심볼, 드로잉은 종류와 앵커·ID 또는 식별값으로 대상을 대조한다. 같은 종류의 거래량 프로파일이 여러 개면 `type: volumeprofile`만으로 개별 대상을 고르지 않는다. 고유하게 지정할 방법이 확인되지 않으면 중단한다. 다른 날짜의 `tc-`나 수동 드로잉은 삭제 대상에 명시된 경우에만 포함한다. 삭제 후 같은 목록을 다시 읽고 화면과 저장 상태를 확인한다. 현재 드로잉 삭제 도구가 저장본까지 지우는 경우 그 동작도 삭제 범위에 포함되는지 확인한다.

### 중복 표시와 재로딩

- `read_drawings`, `list_saved_drawings`, 접근할 수 있는 Yahoo 레이아웃의 드로잉을 대조한다. 객체는 종류·d0·d1·v0·v1·text로 비교한다. 같은 종목·보기에 같은 가격과 의미인 라벨은 텍스트 인코딩을 풀어서 비교한다. 좌표가 달라도 이전 저장본과 최신 수동 배치인지 확인한다.
- 사용자가 삭제를 명시한 중복은 보존할 원본과 자동 복원 경로를 확인한 뒤 정리한다. 동일 객체는 Yahoo 레이아웃 또는 Tratto 저장본 중 한 곳에서만 자동 복원되게 한다. Yahoo에 올바른 원본이 저장돼 있음을 먼저 확인하면 `delete_saved_drawing`으로 지정된 Tratto 사본을 제거할 수 있다. 이 명령은 저장본에만 적용된다.
- `remove_drawing(type, price, price2|text)`는 일치하는 화면 사본과 확장 저장본도 함께 제거한다. 호출 전에 일치 항목과 보존할 원본을 확인하고, 사용자가 요청한 범위에서만 적용한다. 정리 후 같은 Yahoo 탭을 두 번 새로고침한다. 각각 차트와 자동 복원이 준비된 뒤 다시 읽어 원본이 한 벌이고 대상 밖 표시가 보존됐는지 확인한다.
- 같은 기울기의 연장선은 하나로 합칠 수 있다. 세션 수 기준 기울기로 끝점 값을 계산해 원래 앵커를 지나는지 확인한다.

### 화면 표시 범위와 라벨

- `set_range`로 약 1년을 넘기면 주봉으로 바뀐다. 즉시 `set_periodicity(interval=1, timeUnit="day")`로 되돌린다. 끝 날짜를 미래로 줘도 Yahoo는 마지막 봉 오른쪽 여백을 만들지 않는다.
- 마지막 확인 봉에 붙인 `draw_callout` 라벨은 오른쪽 끝에서 잘린다. 화면에 보여야 하면 구간 안쪽 날짜(약 10~15거래일 전)에 두고 가격은 바꾸지 않는다. 같은 분석의 종목들은 같은 날짜로 맞춘다.
- 미래 연장 요청은 기준 거래일과 목표 종료일을 먼저 확정하고, 화면 여백을 종료 좌표와 함께 확인한다. 날짜가 마지막 봉으로 스냅되는 도구는 미래 앵커의 저장·재조회가 검증된 경로로 바꾼다. Yahoo 네이티브 레이아웃을 적용할 수 있으면 `layout.setSpan.padding`으로 여백을 지정하고 실제 화면에서 끝점이 보이는지 확인한다. `orca computer drag`는 드로잉 앵커를 옮길 수 있으므로 사용하지 않는다. 대체 방법으로 여백을 만들 수 없으면 사용자에게 차트를 옮겨 달라고 요청한다.
- 캡처는 `orca computer list-windows`로 Yahoo 차트 창을 찾아 `get-app-state --window-id`로 한다. 사용자가 같은 창에서 다른 탭을 보고 있으면 탭을 바꾸기 전에 묻는다.
- 기존에 허용된 탭 전환은 다시 확인받지 않는다. 작업 전에 선택 탭을 기록하고, 승인된 범위에서 대상 탭을 확인한 뒤 원래 탭으로 복귀한다. 화면의 종목과 `get_chart_summary`·`read_drawings`의 종목이 다르면 쓰기를 멈추고 연결을 바로잡는다.

### MCP 서버 연결

Tratto 확장은 `ws://127.0.0.1:8787`에 한 서버만 연결한다. 차트 변경은 현재 작업 세션에서 수행한다.

1. 연결 오류나 포트 충돌이 나면 `lsof -nP -iTCP:8787 -sTCP:LISTEN` 등으로 리스너 PID를 찾는다. 프로세스가 Tratto인지, 어느 세션 소유인지, 해당 차트 작업이 진행 중인지 확인한다.
2. 다른 세션의 Tratto 작업이 진행 중이면 그 세션에 차트 작업 중단을 전달한다. 진행 중인 그리기·삭제 요청의 완료 또는 취소와 마지막 확인 상태를 파악한 뒤 그 세션의 Tratto 연결을 종료한다. 이미 작업을 마친 전용 Tratto 세션은 연결과 함께 정상 종료한다. 다른 작업도 수행하는 세션은 Tratto 연결만 종료한다. 소유가 확인되지 않은 프로세스에는 종료 신호를 보내지 않는다.
3. 포트가 해제됐는지 확인하고 현재 세션에서 MCP를 연결한다. 확장 연결과 응답을 확인한 뒤 `get_chart_summary`로 올바른 Yahoo Finance 종목·주기를 확인하고 `read_drawings`로 중단 당시 변경이 반영됐는지 대조한다. 미반영 항목만 이어서 처리한다. 포트를 넘기거나 복구하지 못한 경우 점유 세션 확인 결과와 실패한 단계를 남긴다.

### 앵커가 필요한 도구

- **피보나치** — 표준 경로에서는 `fib_retracement.status=ok`인 확정 스윙의 날짜·가격을 사용한다. 5년 분석 경로에서는 Python으로 확정하고 검증한 스윙 앵커만 사용한다. 스윙이 불명확하거나 무효화되면 생략 이유를 기록한다.
- **Anchored VWAP** — 분석 목적에 맞는 검증된 스윙 시작일 또는 실적 발표 후 첫 거래일을 선택한다. Yahoo 엔진이 지원하면 확인된 앵커를 넘긴다. 미지원이면 코드가 산출한 날짜별 `values`를 선으로 표시한다. 선분이 지나치게 많거나 렌더링을 방해하면 마지막 `value`만 수평선으로 표시하고 일봉 근사임을 밝힌다. 실적 앵커가 선택되면 발표 시각 확인 상태를 기록한다.
- **RSI 다이버전스** — 가격 고점이 높아지고 대응 RSI 고점이 낮아지면 약세, 가격 저점이 낮아지고 대응 RSI 저점이 높아지면 강세다. 확인된 경우에만 해당 봉의 원본 고가 또는 저가와 날짜를 사용해 `draw_trendline`으로 그리고, RSI 패널이 지원되면 같은 날짜를 잇는다. 실제 RSI 값을 확인할 수 없어 화면으로 판단했다면 그 한계를 밝힌다. 판정 근거가 부족하면 미확인으로 기록한다. 라벨은 `tc-<as_of>-rsidiv-model-<n>`을 사용하고 통계 검증 상태와 구분한다.

## 5. 완료 검증과 보고

드로잉의 근거와 반영 증거를 각각 기록한다.

1. **드로잉 근거.** 분석 종목·주기·가격 기준·기준일과 시간대를 명시한다. 지지·저항이나 추세선은 원본 봉의 날짜·가격, 피벗 또는 검증된 `chart-zones` 결과를 연결한다. 공개된 전략 가격은 원문과 확인 시점을 기록한다. 사용자가 지정한 좌표는 해당 요청을 근거로 삼는다. 연장선은 원래 앵커, 거래일 간격, 기울기, 계산한 끝점을 남긴다.
2. **좌표 대조.** 변경 전후 `read_drawings`로 대상별 예상값과 실제 종류·날짜·가격·라벨·스타일을 비교한다. 해당되는 경우 `list_saved_drawings`와 Yahoo 레이아웃도 대조한다. 요청 범위의 추가·교체·삭제가 모두 반영됐는지, 관련 없는 표시가 보존됐는지, 대상 객체와 라벨이 한 벌씩 있는지 확인한다.
3. **브라우저 확인.** 사용자 작업 대상인 실제 Yahoo Finance 탭을 다시 열어 종목·주기·표시 상태를 대조한다. `read_drawings`에서 요청한 좌표가 복원된 것을 확인하고 캡처한다. 가격 라벨과 요청한 끝점이 잘리지 않고 읽히는지 확인한다. 한 화면에 들어오지 않으면 필요한 화면을 나눠 캡처한다. 중복 수정은 위 재로딩 절차를 따른다. 도구 성공 응답, 독립 미리보기, 인계받은 작업자의 보고는 실제 사용자 탭 확인을 위한 참고로 쓴다. 대상 탭을 확인할 수 없거나 좌표·렌더링·복원이 불일치하면 확인된 범위와 누락 항목을 보고하고 미완료로 기록한다.
4. **결과 보존.** `drawings.json`에 대상과 기간, 항목별 근거와 출처, 예상·실제 좌표, 처리 유형과 이유, 분석 사용 여부, 화면 표시 여부, 중복 개수, 재로딩 후 상태, 확인 시각·시간대를 남긴다. 변경 전후 MCP 조회 원문과 최종 캡처의 경로도 기록한다. 기존 실행 폴더가 있으면 그곳에 저장하고, 단독 차트 편집이면 작업용 로컬 경로를 사용한다. 브라우저에서 확인한 변경과 남은 제약을 사용자에게 알리고 캡처와 좌표 검증 기록의 경로를 제공한다.

차트 데이터 일치(`chart_validation.status` 또는 5년 OHLCV 검증), 드로잉 확인(좌표·재열기 후 표시), 통계적 예측력을 각각 보고한다. `chart-zones`의 통계는 해당 평가의 `effective_status`로 확인한다. 평가가 없거나 통계가 `passed`가 아니거나 `pending`/`stale`이면 예측력 미확인으로 보고한다. 통과 상태는 평가한 계산 방식의 과거 비교 결과를 나타낸다.

### 추가·재사용 증거 검사

추가·재사용·교체·정리한 객체는 아래 형식으로 종목·대상 탭별 `drawings.json`에 남긴다. 세 번의 `read_drawings` 응답을 각각 저장하고, 같은 탭의 종목·주기와 확인 시각을 기록한다. 재열기 후 실제 탭에서 요청한 항목이 읽히거나 삭제 대상이 사라졌는지 확인하고 캡처한다.

```json
{
  "version": 1,
  "target": {"tab_id": "chart-tab-7", "ticker": "QQQ", "interval": "day", "as_of": "2026-11-20"},
  "data_validation": {"source": "chart-zones", "path": "zones/chart_validation.json"},
  "reads": {
    "before": {"tab_id": "chart-tab-7", "interval": "day", "path": "read-before.json", "observed_at": "2026-11-20T20:01:00-05:00"},
    "after": {"tab_id": "chart-tab-7", "interval": "day", "path": "read-after.json", "observed_at": "2026-11-20T20:02:00-05:00"},
    "reopened": {"tab_id": "chart-tab-7", "interval": "day", "path": "read-reopened.json", "observed_at": "2026-11-20T20:03:00-05:00"}
  },
  "items": [{
    "id": "recent-trend",
    "action": "add",
    "type": "segment",
    "requested_at": "2026-11-20T20:00:00-05:00",
    "anchors": [{"date": "2026-11-17", "price": "101.23"}, {"date": "2026-11-20", "price": "102.45"}],
    "reopened_screen": {"tab_id": "chart-tab-7", "visible": true, "capture_path": "reopened.png"}
  }]
}
```

- 경로는 모두 `drawings.json` 기준 상대 경로다. 개별 조회 파일에 Tratto `read_drawings` JSON-RPC 응답 또는 그 안의 `ok`·`data` 응답을 보존한다. 조회 시각은 시간대 오프셋을 포함하고 실제 수행 순서대로 기록한다. 요청 좌표와 `requested_at`은 변경 전 조회까지 기록한다.
- `chart-zones`는 같은 종목·기준일의 `chart-check`가 쓴 `chart_validation.json`을 쓴다. 5년 일봉 경로는 `source`를 `five-year-ohlcv`로 쓰고, 근거 JSON에 `ticker`, `as_of`, `sessions`, `ohlcv`를 남긴다. 각각 검증을 통과했을 때 `sessions`와 `ohlcv`를 `passed`로 기록하고 거래일·봉 수·누락·중복·OHLCV 검사 내역도 보존한다.
- 항목 ID는 파일 안에서 고유해야 한다. `add`는 변경 전 일치 객체 0개, `reuse`는 1개를 기대한다. 둘 다 변경 직후와 재열기 후 각각 1개여야 한다. Tratto 종류 `rectangle`·`segment`는 두 앵커, `horizontal`은 한 앵커를 기록한다. 저장된 ChartIQ `d0/v0`, `d1/v1`에 맞춰 거래일과 십진수 가격을 대조한다. 그림 ID가 달라도 좌표가 같으면 일치로 센다.
- 화면 확인은 작업자가 실제 탭을 다시 연 뒤 기록한다. CLI는 탭·표시 기록과 비어 있지 않은 캡처 파일을 확인한다.
- 스타일을 요청받았으면 항목에 `style`을 넣는다. 허용 키는 `color`, `pattern`, `line_width`, `text`, `border_color`, `background_color`다. `callout`과 `annotation`의 앵커는 한 개이며, `text`는 인코딩을 풀어 비교한다.
- `action: replace`는 `previous: {anchors, style}`로 교체할 객체를 지정한다. 좌표가 같으면 전후 스타일 차이로 구분한다. `action: remove`는 1→0→0과 `reopened_screen.visible: false`를 요구한다.
- `role_colors`는 역할명과 여섯 자리 RGB hex 색의 맵이다. 각 항목에 같은 `role`과 `style.color`를 쓰고, `callout`은 `style.border_color`도 맞춘다. CLI는 역할별 색 중복을 검사한다.
- 한 화면 봉 수를 요청받으면 `reopened_view`에 `tab_id`, `chart_timezone`, `summary_path`(재열기 후 요약 원문), 실제 화면의 `first_date`, `last_date`, `visible_bars`, 요청 `minimum_bars`를 보존한다. 끝 날짜는 오른쪽 여백을 빼고 마지막으로 보이는 실제 봉을 쓴다. 로드된 봉 수가 화면에 들어왔다는 근거는 화면에서 확인한다.

```bash
tradingagents chart-drawings-check --drawings path/to/drawings.json --json
```

종료 코드 `0`은 완료, `1`은 증거 부족·불일치, `2`는 입력 파일 읽기·해석 실패다. 출력의 공통 및 항목별 사유를 보고한다. 예측력은 별도 상태로 적는다.

Markdown 보고서는 기준 시각과 핵심 판단부터 적고, 색상 범례·가격·후보 수는 짧은 표로 보여준다. 화면, 좌표 검사, 계산 원문은 관련 문단 끝에 연결한다. 가독성 수정 대상이 저장된 보고서라면 그 파일을 수정한다.
