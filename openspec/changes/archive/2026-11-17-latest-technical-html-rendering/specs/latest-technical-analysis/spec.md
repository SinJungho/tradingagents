## ADDED Requirements

### Requirement: 보고서 형식에 맞는 렌더링
시스템은 Markdown 보고서를 `.md`에 Markdown으로 보존하고 `.html`에는 제목, 목록, 표, 링크, 강조 및 코드를 의미 있는 HTML로 렌더링하는 MUST 요구사항을 충족한다. HTML 본문의 원시 태그는 실행되지 않도록 이스케이프한다.

#### Scenario: Markdown 형식 렌더링
- **WHEN** 보고서에 Markdown 제목, 목록, 표, 굵은 글씨 및 인라인 코드가 포함된다
- **THEN** HTML은 각각 의미 있는 HTML 요소로 표시하고 `.md`는 Markdown 문법을 유지한다.

#### Scenario: 안전하지 않은 HTML 입력
- **WHEN** 보고서 본문에 원시 HTML 태그가 포함된다
- **THEN** HTML 보고서는 해당 태그를 실행 가능한 요소로 삽입하지 않는다.
