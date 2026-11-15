## ADDED Requirements

### Requirement: 머리말 시각 표기 통일

시스템 MUST Markdown 머리말의 기준 시각·정규장 폐장·생성 시각·다음 정규장 개장 시각을 미국 동부시간 `YYYY-MM-DD HH:MM ET` 형식으로 표시해야 하며, `evidence.json`의 시각 값은 시간대가 있는 ISO 형식으로 유지해야 한다.

#### Scenario: UTC로 저장된 생성 시각

- **WHEN** 생성 시각이 `2026-11-13T14:32:39+00:00`로 저장될 때
- **THEN** 머리말에는 `2026-11-13 09:32 ET`로 표시된다

### Requirement: 해당 없음 값 표기

시스템 MUST `none_found` 항목의 값 칸을 "해당 없음"으로 표시하고, "확인 불가"는 값이 없는 다른 상태 항목에만 써야 한다.

#### Scenario: 기사가 없는 심볼

- **WHEN** 한 심볼의 뉴스 항목이 `none_found`일 때
- **THEN** 그 항목의 값 칸은 "해당 없음"이다

### Requirement: 시장 폭 제외 종목 이름 표시

시스템 MUST 시장 폭 비고에 이력이 짧아 각 기간 분모에서 빠진 종목 이름을 기간별로 표시하고, 기간마다 10개를 넘으면 앞의 10개와 "외 N개"로 줄여야 한다.

#### Scenario: 이력 부족 종목

- **WHEN** 50일 구간에서 VYLR, 200일 구간에서 HONA·FDXF·VYLR이 이력 부족으로 빠질 때
- **THEN** 비고에 "50일 VYLR"과 "200일 HONA, FDXF, VYLR"이 표시된다
