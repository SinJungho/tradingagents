# Repository guidance

- Keep broker access read-only in application code. Never add order placement, modification, cancellation, conditional-order, or automated trading calls.
- Keep real broker credentials, access tokens, account identifiers, and raw account responses out of prompts, logs, reports, and remote tracing. Use only synthetic values in fixtures.
- Use synthetic fixtures for portfolio tests. Tests must not call a live broker or LLM.
- Preserve unrelated user files and changes. Do not inspect or copy `.env` or `.env.bak` values.

## Investment research requests

요청한 결과로 리서치 경로를 고른다. 같은 유형에는 같은 기본값을 적용하고, 명령 옵션과 세부 절차는 해당 스킬을 따른다.

| Type | Trigger | Flow |
| --- | --- | --- |
| Market report | 미국장 마감·장후 정리 | `market-report` 스킬과 `tradingagents market-report`. 동부시간 20시 기준 직전 완료 거래일을 확인하고, 자료 전용 요청과 개발 검증에는 `--no-llm`을 쓴다. |
| Single-stock analysis | 종목 종합 분석 | `stock-scenario`의 `--ticker` 경로. 기술적 분석은 기존 Market Analyst 도구를 사용한다. |
| Investment scenario | 매수·보유·매도 또는 비중 판단 | `stock-scenario`의 `portfolio live --symbol <T>` 경로로 보유를 반영한다. 보유 JSON을 지정하면 `--portfolio`를 쓴다. |
| Stock discovery | 팩터 비교·후보 발굴 | `stock-discovery`의 `discover --tickers` 또는 `--universe`. 후속 종목 분석은 사용자가 선택한 후보에만 적용한다. |
| Portfolio check | 보유 조회·포트폴리오 점검 | `portfolio-check`에서 조회 전용은 `portfolio live --no-scenarios`, 일반 점검은 `portfolio live`, 명시적 심층 점검은 `--full-workflow`를 쓴다. |
| Chart analysis | 차트·기술적 분석 | `tratto-chart`. 미국 종목의 일봉 가격 구조·지지·저항은 `chart-zones --tickers <T> --json`, 5년 일봉·장기 및 최근 추세선은 OHLCV·전후 5봉 피벗 절차를 쓴다. |
| Chart verification and drawing | 대상 차트 검증·표시 | `tratto-chart`에서 가격 구간 대조는 `chart-check`, 표시는 해당 분석 경로에서 검증한 좌표를 쓴다. |
| Backtest | 그래프 판단·팩터 신호·차트 가격 구간의 과거 성과 평가 | `backtest-eval`에서 각각 `backtest`, `style-backtest`, `zone-backtest run --period validate`를 쓴다. |
| Disclosure snapshot | 13F 기관 보유·미국 하원 주식 보유 및 거래 공시 | `portfolio-disclosures`의 공식 SEC·하원 공시 조회 절차를 적용한다. |

새 데이터 출처 채택은 `data-source-check`, 반복적인 API·인증 실패는 `api-doctor`, 외부 프로젝트 비교는 `reference-research`를 적용한다.

- 차트 분석은 종목·봉 주기·기준 거래일·가격 조정 기준을 확인하고 가격 구조·추세·거래량에서 시작한다. 필요한 지표만 사용하며, 현재가를 포함하는 구간은 상단·하단 이탈 조건을 각각 설명한다.
- 차트 변경은 표시를 요청받은 범위에서만 수행한다. 실제 대상 탭과 기존 객체를 확인하고, 검증한 좌표와 같은 객체는 재사용한다. 삭제는 사용자가 명시한 대상에만 적용한다.
- 변경 전후 `read_drawings`와 실제 사용자 탭을 다시 열어 확인한 상태를 캡처와 `drawings.json`에 남긴다. 증거가 빠지면 확인된 단계까지만 보고한다. 차트 데이터 일치, 드로잉 확인, 통계적 예측력은 각각 보고한다.
- 미국장 답변은 판단과 핵심 근거 2~3개, 판단 변경 조건부터 제시한다. 시장 폭이 미확인이면 상승 확산 판단을, 보유 수량이나 평가액이 미확인이면 비중 조정 수치를 유보한다. 상세 근거는 기존 보고서에 연결한다. 골드만삭스 자료와 판교불패 영상은 당일 쟁점과 관련될 때 원자료와 대조한다.

- Do not ask for what the repo, config, or conversation already answers. Ask only for a missing input that changes the result (ticker, date, holdings).
- Read-only Toss account reads with `tradingagents portfolio live` (including its default LLM analysis) are pre-authorized by the repo owner; do not ask again. Run other real LLM analysis (`--ticker`, `backtest`, `market-report`) only when the user explicitly asks; otherwise give the command to run.
- Never report an unimplemented feature as executed. Feature work starts with an OpenSpec change.
- Do not state target prices or returns without a computed basis. Report data as-of times and gaps as unknown, not zero.
- These rules govern the coding agent only; they do not make the app run analyses on its own.

## OpenSpec

- Before implementing a feature or behavior change, inspect `openspec/` and create or update the relevant OpenSpec change with its proposal, requirements/scenarios, and tasks.
## 리서치 모델 선택

새 세션에서도 아래 실행 기본값을 적용한다. 사용자가 모델·추론 수준을 직접 지정하거나 기존 설정으로 재현을 요청하면 해당 설정을 우선하고 프리셋을 생략한다. 프리셋은 공급자를 바꾸지 않으며 GPT tier에만 적용한다.

| 작업 | 실행 설정 |
| --- | --- |
| 종목 종합 분석 | 첫 인자를 `--ticker`로 유지하고 `--model-preset standard` 추가 |
| 보유 반영 시나리오·일반 포트폴리오 점검 | `portfolio live --model-preset standard` |
| 명시적 심층 포트폴리오 점검 | `portfolio live --full-workflow --model-preset deep` |
| 미국장 보고서 해석 | `market-report --model-preset standard`. 상충하는 근거의 심층 검토를 요청하면 `deep` |
| 종목 탐색·차트 계산·보유 및 공시 조회·자료 전용 보고서·팩터 및 가격 구간 백테스트 | 기존 계산·조회 전용 경로 |
| 전체 그래프 백테스트 | 평가 대상 실행과 같은 모델·추론 설정 |

`standard`는 quick GPT-6 Luna, deep GPT-6.1 Sol, 공통 `medium`이다. `deep`은 quick GPT-6.2 Sol, deep GPT-6.1 Sol, 공통 `high`다. 현재 공급자에서 해당 모델을 쓸 수 없으면 확인된 모델로 사용자 지정 설정을 적용하고 실제 사용값을 보고한다. 기존 LLM 실행 승인 절차를 따른다.

차트 드로잉·기술적 해석은 Codex 작업을 시작할 때 모델을 지정할 수 있으면 GPT-6.2 Sol `medium`을 기본으로 사용한다. 복합 드로잉과 상충하는 추세 검토는 `high`를 선택할 수 있다. 이미 시작된 세션에서는 현재 모델로 작업하며, 스킬 호출로 세션 모델이 전환됐다고 보고하지 않는다.

- Keep implementation and task status aligned with the approved OpenSpec scope; validate the change and archive it when complete.
- Follow `openspec/config.yaml` for artifact language and formatting conventions.

## Agent skills

- Repeated workflows live in `.agents/skills/` (Codex reads it directly and `.claude/skills` is a symlink for Claude Code). This includes the research skills above and `model-selection`, `openspec-change`, `next-steps`, and `fork-release`. Update a skill when its workflow changes, and keep the rules above authoritative.

## Agent hooks

- `.claude/settings.json` (Claude Code) and `.codex/hooks.json` plus `.codex/rules/` (Codex) enforce the `.env` ban, live-run confirmation, ruff on edited Python, and OpenSpec checks at stop. New Codex sessions also run the API network preflight. Both call `.claude/hooks/guard.py`; change behavior there and keep `tests/test_agent_hooks.py` passing.

## Verification

- Run focused tests for changed behavior, then `./.venv/bin/python -m pytest -q`.
- Run `./.venv/bin/ruff check .`.
- Check the installed CLI with `./.venv/bin/tradingagents --help` or the equivalent module entry point.
