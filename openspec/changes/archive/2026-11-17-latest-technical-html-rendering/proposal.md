# 최신 기술 보고서의 HTML 렌더링 개선

## Why
현재 HTML 생성기는 Markdown을 줄 단위로 일부만 변환한다. 보고서 표와 강조·인라인 코드가 Markdown 기호 그대로 보여 HTML을 읽기 어렵다.

## What Changes
HTML 보고서에서 Markdown 블록과 인라인 서식을 의미 있는 HTML로 렌더링하고 화면 폭·표·차트에 맞는 가독성 스타일을 적용한다. Markdown 파일은 Markdown 형식 그대로 보존한다.

## Out of Scope
분석 내용·지표·차트 데이터와 SVG 표현은 변경하지 않는다. 새 렌더링 라이브러리를 추가하지 않는다.
