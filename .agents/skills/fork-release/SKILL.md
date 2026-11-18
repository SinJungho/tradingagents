---
name: fork-release
description: 작업 브랜치의 커밋을 fork 저장소에만 푸시하고, fork 안의 main을 대상으로 PR을 만들고, 요청 시 병합한다. 원본(upstream)에는 아무것도 보내지 않는다. "push 해줘", "PR 만들어줘", "main에 반영해", "PR 병합해줘", "fork에만 올려" 요청에 사용한다.
---

# fork 저장소 반영

이 저장소는 fork다. `origin`은 사용자 fork(`SinJungho/tradingagents`), `upstream`은 원본(`TauricResearch/TradingAgents`)이다. 푸시·PR·병합은 사용자가 요청했을 때만 하고, 대상은 항상 `origin`이다.

## 1. 사전 확인

- `git remote -v`, `git config --get branch.<브랜치>.remote`로 푸시 대상이 `origin`인지 확인한다.
- `git status -sb`: 커밋되지 않은 변경이 없어야 한다. `results/`는 `quality-review.md`만 추적한다.
- 마지막 전체 검증(pytest·ruff·OpenSpec strict)이 통과한 상태인지 확인하고, 없으면 실행한다.
- 커밋 메시지는 `commit-helper` 규칙(간결한 한국어 `feat|fix|docs|chore:` 요약)과 저장소 attribution 규칙을 따른다.

## 2. 비밀값·민감 파일 점검

fork는 공개 저장소다. 올라갈 범위(`origin/<브랜치>..HEAD` 또는 `origin/main..HEAD`)에서:

- 추가된 줄에서 API 키·토큰·비밀번호 패턴(`sk-…`, `ghp_…`, `AKIA…`, `api_key=…` 등)을 찾는다. 테스트의 합성 값(`SYNTHETIC_…`)은 예외로 확인만 한다.
- 파일 목록에 `.env`, 키 파일, `results/`의 보고서 원본(`evidence.json`, `report.*`)이 없어야 한다. `.env.example`은 값이 아니라 주석·이름만 바뀌었는지 본다.
- 하나라도 걸리면 푸시하지 않고 보고한다.

## 3. 푸시

```bash
git push origin <브랜치>
```

`upstream`으로 푸시하지 않는다.

## 4. PR 생성

`gh`의 기본 저장소가 설정되지 않은 fork에서는 PR 기본 대상이 원본 저장소가 될 수 있으므로 반드시 명시한다.

```bash
gh pr create --repo SinJungho/tradingagents --base main --head <브랜치> --title "<제목>" --body-file <본문>
```

- 본문: 변경 요약(기능 단위), 검증 결과(pytest·ruff·OpenSpec 수치, 실제 자료 확인), 남은 항목. 저장소 attribution 규칙의 PR 문구를 끝에 붙인다.
- 생성 후 `gh pr view <번호> --repo SinJungho/tradingagents --json headRepositoryOwner,baseRefName,commits`로 head 소유자와 대상이 fork `main`인지 확인한다.

## 5. 병합 (사용자가 요청한 경우만)

```bash
gh pr merge <번호> --repo SinJungho/tradingagents --merge --match-head-commit "$(git rev-parse HEAD)"
```

- 병합 전 `mergeable`·`mergeStateStatus`(`CLEAN`)와 PR head가 로컬 HEAD와 같은지 확인한다. `--match-head-commit`에는 전체 SHA를 쓴다(짧은 SHA는 거부된다).
- merge commit으로 이력을 남기고 작업 브랜치는 지우지 않는다.
- 병합 뒤 `git fetch origin main && git merge-base --is-ancestor HEAD origin/main`으로 반영을 확인한다.

## 6. 기록

`openspec/NEXT_STEPS.md`의 브랜치·PR 상태를 고친다. 이 문서 커밋은 `main`에 없는 새 커밋이 되므로 다음 PR에 함께 올린다고 알린다.
