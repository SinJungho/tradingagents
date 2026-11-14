# 문서를 현재 동작에 맞춤

## Why

2026-11-13 변경 이후 사용자 문서가 이전 동작을 설명한다. `README.md`는 시장 폭을 "S&P 500 구성 표본"으로, 실적·발표 시각을 "확인 불가"로 쓰고, `AGENTS.md`·`stock-scenario` 스킬·하네스 명세는 iShares IWM 출처가 CSV 대신 HTML을 반환해 현재 실패하는 `--universe sp500,russell2000,smallcap`을 예시로 든다.

## What Changes

- 하네스 명세의 발굴 안내 예시를 `sp500,sp600,smallcap`으로 바꾸고, Russell 2000 구간이 현재 출처 실패로 표시될 수 있음을 안내하게 한다.
- `README.md` 발굴·시장 보고서 섹션, `AGENTS.md` 요청 표, `stock-scenario` 스킬을 현재 동작에 맞춘다.

## Out of Scope

코드 동작 변경, Russell 2000 대체 출처, 새 CLI 옵션.
