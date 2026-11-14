# NVIDIA Build 금융 에이전트 모델 smoke 검증

## Why

기존 GLM-5.3-Flash 실제 호출은 Z.ai에서 `APIConnectionError`로 끝나 응답을 받지 못했다. Z.ai Standard API의 공개 요금은 유료이며 계정별 무상 크레딧 적용 여부는 확인되지 않았다. 따라서 Z.ai 호출은 재시도하지 않는다.

금융 에이전트에 가까운 Vals Finance Agent v2.1(2026-11-05)에서는 공시 검색과 계산 도구를 쓰는 공통 harness 기준으로 DeepSeek V4.1 Flash가 65.43%, GLM-5.3-Flash가 60.59%를 기록했다. DeepSeek 호출은 더 많은 토큰과 시간이 들었으므로 두 모델을 각각 심층·빠른 역할에 배치하는 방안을 검증한다. NVIDIA Build의 로그인 계정 화면은 API rate limit을 `Up to 40 rpm`으로 표시한다. NVIDIA는 모델과 동시 사용자 수에 따라 실제 허용률이 달라질 수 있다고 안내하며, 해당 화면에는 일일 요청량이나 토큰 잔여량이 표시되지 않았다.

## What Changes

- NVIDIA OpenAI 호환 endpoint에서 심층 모델 `deepseek-ai/deepseek-v4.1-flash`, 빠른 모델 `z-ai/glm-5.3-flash`를 사용하도록 smoke 계획을 갱신한다.
- NVIDIA 모델 ID의 provider 접두사를 capability 판정에서 처리하고, NVIDIA가 DeepSeek의 `reasoning_content`를 반환하면 후속 도구 요청에 보존하도록 호환성 경로를 명시한다. NVIDIA 경유 DeepSeek의 실제 reasoning round-trip은 live 호출 전 mock으로 확인하며, 공급자별 차이는 제한 사항으로 기록한다.
- 자동 검증은 HTTP mock과 합성 입력만 사용해 provider, 모델 ID, 구조화 출력/도구 요청, 출력 상한, 파싱을 확인한다.
- 실호출 smoke에는 로컬 보호 상한을 둔다: 출력 최대 256 토큰, 한 번 실행당 요청 최대 1회, 실행 사이 최소 60초, 재시도와 폴백 없음. 이 로컬 제한은 NVIDIA 계정 한도나 일일 잔여량을 뜻하지 않는다.
- 실제 호출은 해당 NVIDIA 계정의 청구 없는 개발·평가 조건이 확인된 경우에만 합성 입력으로 최대 1회 수행한다. 계정의 모델별 실시간 제한이나 무상 잔여량을 확인할 수 없으면 호출을 건너뛴다.
- `.env`와 `.env.bak`을 읽거나 수정하지 않고, API 키·실계좌·실보유 정보는 사용하거나 출력하지 않는다.
- 이 작업은 요청 호환성과 형식만 검증하며 금융 분석의 사실 정확도, 투자 판단의 품질 또는 수익성을 검증하지 않는다.

## Capabilities

### Modified Capabilities

- `glm-structured-output-smoke`: GLM 빠른 역할과 DeepSeek 심층 역할을 NVIDIA Build의 합성 smoke 경로로 검증한다.

## Impact

- 영향 범위는 기존 smoke script, 관련 HTTP mock 테스트, NVIDIA 모델 ID/기능 매핑 및 OpenSpec 산출물이다.
- NVIDIA provider와 API 키 매핑은 이미 저장소에 있으므로 불필요한 프레임워크나 의존성을 추가하지 않는다.
- 계정의 무상 한도를 확인할 수 없으면 실제 요청은 건너뛰고 mock 검증 결과와 필요한 설정만 보고한다.
