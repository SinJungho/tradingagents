---
name: openspec-change
description: 기능 추가·동작 변경을 OpenSpec 변경안 작성부터 구현, 검증, 아카이브, 커밋까지 진행한다. "이 기능 구현해", "계획 제안해", "해당 작업들 진행해", "OpenSpec으로 진행", "goal 계획대로 진행" 요청에 사용한다.
---

# OpenSpec 변경 진행

`AGENTS.md`의 OpenSpec·Verification 규칙을 따른다. 산출물 언어와 형식은 `openspec/config.yaml`(한국어, 구조 헤딩과 SHALL/MUST는 영어).

## 1. 계획

- `openspec/specs/`에서 관련 capability를 찾고, `openspec/changes/`에 진행 중인 변경이 있는지 확인한다.
- 범위가 크면 계획을 먼저 제시하고 사용자 확인을 받는다. 결정이 필요한 갈림길(데이터 공급자, 유료 여부 등)만 질문한다.

## 2. 변경안 작성 (`openspec/changes/<kebab-name>/`)

- `proposal.md`: `# 제목`, `## Why`, `## What Changes`, `## Out of Scope`
- `specs/<capability>/spec.md`: `## ADDED|MODIFIED Requirements` → `### Requirement:` (MUST/SHALL 포함) → `#### Scenario:` (`- **WHEN**` / `- **THEN**`)
- `tasks.md`: 체크박스 작업 목록
- 검증: `npx --offline @fission-ai/openspec validate <name> --strict` (오프라인 캐시가 없으면 `--yes`)

## 3. 구현

- 기존 코드의 헬퍼와 패턴을 먼저 찾아 재사용한다. 브로커는 조회 전용, 테스트는 합성 자료만 쓰고 실브로커·실LLM을 호출하지 않는다.
- 작업할 때마다 `tasks.md` 체크 상태를 실제와 맞춘다. 범위를 벗어나는 일은 변경안을 고치거나 후속 작업으로 남긴다.

## 4. 검증

1. 바뀐 동작의 집중 테스트
2. `./.venv/bin/python -m pytest -q`
3. `./.venv/bin/ruff check .`
4. `./.venv/bin/tradingagents --help`

실행 결과(통과 수, skip 수)를 그대로 보고한다. 실데이터 평가가 필요한 변경은 결과와 한계를 변경 폴더의 `README.md`에 남긴다.

## 5. 아카이브

```bash
npx --offline @fission-ai/openspec archive <name> --yes
```

아카이브가 만든 `openspec/specs/<capability>/spec.md`의 `## Purpose` 아래 "TBD - created by archiving change" 문구를 한 문장 목적으로 바꾼다(종료 hook이 검사한다). 이후 `validate --specs --strict`.

## 6. 커밋 (사용자가 요청한 경우)

- 변경 하나당 커밋 하나. 한 파일에 여러 변경이 섞이면 해당 hunk만 나눠 staging한다.
- 메시지는 `feat|fix|docs|chore: 간결한 한국어 요약` + 본문 + 저장소 attribution 규칙.
- 커밋을 여러 개 만들었으면 임시 worktree에서 커밋마다 전체 테스트를 돌려 중간 커밋도 통과하는지 확인한다.

## 7. Orca Worker로 나눠 진행할 때 (사용자가 요청한 경우)

- Worker 워크트리는 커밋에서 갈라지므로 미커밋 변경은 전달되지 않는다. 시작 전에 기준 커밋을 만든다(사용자 승인 필요).
- 같은 파일·같은 spec 요구사항을 두 Worker가 고치지 않게 나눈다. 겹치면 하나를 병합한 뒤 다음 Worker를 시작한다.
- 워크트리 Python 환경: Orca 저장소 setup 스크립트에 `uv venv -q .venv && uv pip install -q --python .venv/bin/python -e '.[dev]'`를 넣으면 워크트리마다 자체 `.venv`가 생긴다(2026-11-13 확인: uv 캐시로 약 2초, 전체 pytest 통과). setup 스크립트가 없으면 메인 저장소의 `.venv/bin/python -m pytest`를 워크트리 루트에서 실행하고, 먼저 `import tradingagents`가 워크트리 경로를 가리키는지 확인하게 한다.
- Codex 샌드박스에서는 `npx --offline @fission-ai/openspec`이 ENOTCACHED로 실패한다. 이미 받아 둔 패키지를 `node ~/.npm/_npx/*/node_modules/@fission-ai/openspec/bin/openspec.js validate <name> --strict`로 직접 실행하면 된다(샌드박스에서 확인). 아카이브는 코디네이터가 병합 때 실행한다.
- Codex 샌드박스에는 외부 네트워크가 없다. 출처의 HTTP 상태·형식·기준일은 코디네이터가 확인해 spec에 넣는다.
- strict 검증은 요구사항 본문 500자 초과 경고도 실패로 처리한다. spec에 미리 적는다.
- 병합마다 전체 검증(실패 시 즉시 중단되게 `set -o pipefail`) → 아카이브 → `orchestration worker-stop` → `orca worktree rm --worktree path:<경로> --delete-branch` 순서로 정리한다.
