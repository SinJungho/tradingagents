# Tratto 도구 카탈로그

공식 README는 Tratto MCP 도구를 50개로 설명한다. 아래 이름은 README에 나온 카탈로그다. 설치된 패키지 버전은 다를 수 있으므로 실행 때 MCP tool list와 각 도구의 schema가 최종 기준이다.

| 그룹 | README의 도구 이름 | 용도 |
| --- | --- | --- |
| 읽기 | `get_chart_data`, `get_chart_summary`, `read_drawings`, `get_capabilities`, `list_indicators`, `get_corporate_events` | OHLC, 차트 상태, 드로잉, 엔진 기능, 지표 및 기업행동 확인 |
| 그리기 | `draw_support`, `draw_trendline`, `draw_ray`, `draw_line`, `draw_crossline`, `draw_arrow`, `draw_vertical`, `draw_channel`, `draw_rectangle`, `draw_ellipse`, `draw_callout`, `draw_raw` | Yahoo 차트에 선·도형·주석 표시 |
| 피보나치 | `draw_fib`, `draw_fib_arc`, `draw_fib_fan`, `draw_fib_projection`, `draw_fib_timezone` | Fibonacci 도구. zone 표시에는 쓰지 않고 지표 표시(4단계)에서 `draw_fib`만 쓴다. |
| 분석 도구 | `draw_pitchfork`, `draw_gann_fan`, `draw_gartley`, `draw_speed_arc`, `draw_speed_line`, `draw_time_cycle`, `draw_measurement`, `draw_volume_profile`, `draw_quadrant_lines`, `draw_tirone_levels`, `draw_average_line`, `draw_regression_line` | 기타 분석 도형. zone 계산에는 쓰지 않고 지표 표시(4단계)에서 `draw_volume_profile`만 쓴다. |
| 관리 | `remove_drawing`, `undo_drawing`, `clear_drawings`, `list_saved_drawings`, `delete_saved_drawing` | 드로잉 관리. 삭제 도구는 사용자 지시 없이는 호출 금지 |
| 차트 보기 | `open_chart`, `set_chart_style`, `set_periodicity`, `set_range`, `add_comparison`, `remove_comparison`, `toggle_corporate_events` | 종목·보기·범위·비교 종목·이벤트 표시 |
| 지표 | `add_indicator`, `remove_indicator` | Yahoo 차트 지표 추가·삭제 |
| 안내 | `get_drawing_guide` | 색·선·가독성 가이드 |

출처: [Tratto 공식 README](https://github.com/Taoo425/tratto). README는 도구 이름과 역할을 제공하지만 개별 MCP JSON Schema를 문서화하지 않는다.

