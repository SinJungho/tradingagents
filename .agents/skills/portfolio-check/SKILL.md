---
name: portfolio-check
description: 토스 계좌 보유 현황을 읽기 전용으로 조회해 포트폴리오를 점검한다(일반 요약 또는 심층 분석). "내 포트폴리오 점검", "보유 주식 조회", "계좌 상세 종목 내역", "보유 종목 심층 분석", "portfolio live" 요청에 사용한다. 특정 종목 매매 시나리오는 stock-scenario를 쓴다.
---

# 포트폴리오 점검

## 실행 모델

일반 시나리오에는 `--model-preset standard`, 명시적 `--full-workflow`에는 `--model-preset deep`을 적용한다. 조회 전용은 `--no-scenarios`를 사용한다. [저장소 모델 설정](../../../AGENTS.md#리서치-모델-선택)을 따른다.

`AGENTS.md`의 Portfolio check 흐름을 따른다. 브로커 접근은 조회 전용이며 주문 관련 명령은 실행하지 않는다.

## 1. 실행 조건 확인

- 토스 실계좌 읽기 전용 조회(`portfolio live`)는 저장소 소유자가 사전 허용했다. 허용을 다시 묻지 않고 실행한다. 합성 자료가 필요한 개발 확인만 `tradingagents portfolio demo`를 쓴다.
- 심층 분석(`--full-workflow`)은 사용자가 "심층", "Bull/Bear", "Trader·Risk 결정"처럼 요청했을 때만 쓴다. LLM 호출이 크게 늘어난다고 알린다.
- 계좌가 여러 개면 `--account-ordinal`을 묻는다. 그 외에는 다시 묻지 않는다.
- 필요한 환경변수 이름만 확인한다: `TOSS_CLIENT_ID`, `TOSS_CLIENT_SECRET`, `TOSS_BROKER_READ_ONLY_VERIFIED=I_ACKNOWLEDGE_READ_ONLY`. 값은 읽거나 출력하지 않는다. 설정이 의심되면 `api-doctor` skill로 넘긴다.
- 설정은 실행 위치에서 위로 찾은 `.env`로 읽는다. Orca 워크트리에는 `.env`가 없을 수 있으므로 `tradingagents doctor`가 토스 변수를 `미설정`으로 보이면, 같은 저장소의 기본 체크아웃(`git worktree list` 첫 줄)으로 이동해 워크트리의 `.venv/bin/tradingagents`를 실행한다. `.env`를 복사하거나 열지 않는다.
- 비대화형 실행에서는 계좌가 하나여도 `--account-ordinal 1`이 필요하다. 목록에 둘 이상 나오면 사용자에게 묻는다.

## 2. 실행

다른 명령과 묶지 않은 단독 명령으로 실행한다.

```bash
tradingagents portfolio live --no-scenarios       # 보유 조회만(LLM 없음)
tradingagents portfolio live                      # 일반 요약과 시나리오
tradingagents portfolio live --full-workflow      # 심층
tradingagents portfolio live --symbol TQQQ        # 특정 보유·관심 종목만 분석
```

- "보유 종목 조회", "계좌 내역 확인"처럼 분석을 요청하지 않았으면 `--no-scenarios`로 LLM 없이 조회만 한다.

주문 내역 기간이 필요하면 `--orders-from/--orders-to`(최대 90일)를 쓴다. 보고서는 `~/.tradingagents/portfolio/portfolio_live_<시각>.{json,md}`에 저장된다.

## 3. 보고

보고서 Markdown을 읽고 다음 순서로 정리한다.

조회 전용이면 1~2번과 관련 자료 조회 실패를 정리한다. 일반·심층 점검은 위험과 시나리오까지 포함한다.

1. 자료 기준 시각과 조회 시각, 누락·실패한 자료(미확인으로 표시, 0으로 채우지 않음)
2. 보유 요약: 통화별 평가액, 비중 상위, 손익률, 일간 손익
3. 위험 신호: 집중도, 변동성·기술 지표, 이전 스냅샷 대비 평가액 변화
4. 종목별 조건부 시나리오: 단기(기본 1~20거래일)·중기(1~6개월)·장기(6~24개월) × 상승·기본·하락. 각 시나리오의 논리, 촉매, 관찰·검토·무효화 조건, 포트폴리오 영향을 옮긴다(심층이면 Trader·Risk·Portfolio Manager 결정 포함).
5. 실패와 미확인: 종목 조사·시나리오 종합 API 실패와 선택 자료(거시 지표, 예측시장 등) 실패를 보고서의 오류 범주·재시도 가능 여부·횟수 그대로 전한다. `계정 한도 초과`면 LLM 제공자 한도 소진이므로 같은 설정으로 재실행하지 않고 한도 해제 후 재실행 또는 다른 제공자 키 설정을 제안한다(`model-selection`). `분류되지 않은 API 오류`가 반복되면 `api-doctor`로 넘긴다.

- 계좌 식별자, 원시 응답, 개별 거래 행은 답변에 옮기지 않는다.
- 계산 근거 없는 목표가·목표 수익률은 쓰지 않는다.
- 보유 수량이나 평가액이 미확인이면 비중 조정 수치를 유보한다.
- 거래 표현은 실제 보유 상태에 맞춘다(보유: 추가·유지·축소·청산, 관심종목: 신규 진입).
- 사용자가 "정확히 조회했는지" 확인을 원하면 종목별 수량·평균가·평가액 표를 보고서 그대로 보여준다.

자세한 옵션과 보고서 구조: `docs/portfolio-analysis.md`.
