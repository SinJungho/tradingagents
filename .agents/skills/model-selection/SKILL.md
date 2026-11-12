---
name: model-selection
description: TradingAgents 심층·빠른 tier에 쓸 LLM을 벤치마크·비용·가용성 근거로 고르고 설정·검증한다. "어떤 모델이 가장 좋아?", "finance agent 벤치마크", "무료 API 있어?", "gpt-6.1-sol로 바꿔줘", "다른 모델들 테스트해줘", "NVIDIA/GLM/DeepSeek 써도 돼?" 요청에 사용한다.
---

# 모델 선정과 교체

## 1. 근거 수집

- 금융 에이전트 성능: Vals Finance Agent(https://www.vals.ai/benchmarks/finance_agent) 등 공시 검색·계산 도구를 쓰는 벤치마크를 우선한다. 측정일, harness, 점수, 토큰·시간 비용을 함께 기록한다.
- 비용·가용성: 공급자 공식 가격 페이지에서 무료 여부, 크레딧, rate limit(rpm), 지역 제한을 확인한다. 2차 자료만 있으면 "미확인"으로 표시한다.
- 사용자 플랜 경로: ChatGPT Plus/Pro 사용량으로 쓰는 `chatgpt` 제공자가 가능한지 먼저 본다(별도 API 과금 없음).
- 출처 URL을 모두 남긴다.

## 2. 추천 형식

| 후보 | 벤치마크(측정일) | 비용·한도 | 지연 | 적합 tier |

심층 tier(Research Manager·Portfolio Manager 등)는 정확도, 빠른 tier(분석가 도구 호출)는 속도·한도를 우선한다. 추천 1안과 차선안을 근거와 함께 제시한다.

## 3. 교체

- 기본값 변경은 OpenSpec 변경으로 진행한다(`openspec-change` skill). 대상: `tradingagents/default_config.py`, `tradingagents/llm_clients/model_catalog.py`, `.env.example` 주석, README 예시, 관련 테스트.
- 실행 시점 변경만 원하면 환경변수 이름을 안내한다: `TRADINGAGENTS_LLM_PROVIDER`, `TRADINGAGENTS_DEEP_THINK_LLM`, `TRADINGAGENTS_QUICK_THINK_LLM`.

## 4. 검증

1. `tradingagents doctor`로 인증·도달성 확인
2. 실제 모델 호출 smoke 테스트는 유료 여부를 알리고 사용자 허용 후 실행한다. 실패하면 오류 분류(인증, 한도, timeout, 모델명)를 보고하고 같은 호출을 무작정 반복하지 않는다.
3. 결과를 OpenSpec 변경 README에 기록한다.
