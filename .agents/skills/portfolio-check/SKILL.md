---
name: portfolio-check
description: 토스 계좌 보유 현황을 읽기 전용으로 조회해 포트폴리오를 점검한다(일반 요약 또는 심층 분석). "내 포트폴리오 점검", "보유 주식 조회", "계좌 상세 종목 내역", "보유 종목 심층 분석", "portfolio live" 요청에 사용한다. 특정 종목 매매 시나리오는 stock-scenario를 쓴다.
---

# 포트폴리오 점검

`AGENTS.md`의 Portfolio check 흐름을 따른다. 브로커 접근은 조회 전용이며 주문 관련 명령은 실행하지 않는다.

## 1. 실행 조건 확인

- 사용자가 이번 대화에서 실계좌 조회를 명시적으로 허용했는지 확인한다. 허용이 없으면 `tradingagents portfolio demo`(합성 자료)로 처리하거나 실행 명령만 안내한다.
- 심층 분석(`--full-workflow`)은 사용자가 "심층", "Bull/Bear", "Trader·Risk 결정"처럼 요청했을 때만 쓴다. LLM 호출이 크게 늘어난다고 알린다.
- 계좌가 여러 개면 `--account-ordinal`을 묻는다. 그 외에는 다시 묻지 않는다.
- 필요한 환경변수 이름만 확인한다: `TOSS_CLIENT_ID`, `TOSS_CLIENT_SECRET`, `TOSS_BROKER_READ_ONLY_VERIFIED=I_ACKNOWLEDGE_READ_ONLY`. 값은 읽거나 출력하지 않는다. 설정이 의심되면 `api-doctor` skill로 넘긴다.

## 2. 실행

다른 명령과 묶지 않은 단독 명령으로 실행한다(Codex rules가 사용자 확인을 받는 형태).

```bash
tradingagents portfolio live                      # 일반 요약
tradingagents portfolio live --full-workflow      # 심층
tradingagents portfolio live --symbol TQQQ        # 특정 보유·관심 종목만 분석
```

주문 내역 기간이 필요하면 `--orders-from/--orders-to`(최대 90일)를 쓴다. 보고서는 `~/.tradingagents/portfolio/portfolio_live_<시각>.{json,md}`에 저장된다.

## 3. 보고

보고서 Markdown을 읽고 다음 순서로 정리한다.

1. 자료 기준 시각과 조회 시각, 누락·실패한 자료(미확인으로 표시, 0으로 채우지 않음)
2. 보유 요약: 통화별 평가액, 비중 상위, 손익률, 일간 손익
3. 위험 신호: 집중도, 변동성·기술 지표, 이전 스냅샷 대비 평가액 변화
4. 종목별 조건부 시나리오(심층이면 Trader·Risk·Portfolio Manager 결정 포함)

- 계좌 식별자, 원시 응답, 개별 거래 행은 답변에 옮기지 않는다.
- 계산 근거 없는 목표가·목표 수익률은 쓰지 않는다.
- 사용자가 "정확히 조회했는지" 확인을 원하면 종목별 수량·평균가·평가액 표를 보고서 그대로 보여준다.

자세한 옵션과 보고서 구조: `docs/portfolio-analysis.md`.
