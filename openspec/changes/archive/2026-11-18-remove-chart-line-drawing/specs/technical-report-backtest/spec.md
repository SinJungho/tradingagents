## REMOVED Requirements

### Requirement: 시점 고정 신호 재계산
**Reason**: 백테스트 대상 신호 대부분이 선 긋기(시나리오 경계, 피보나치, 구조선)이고 선 긋기가 외부 구현으로 이전되어 `technical-backtest`를 제거한다.
**Migration**: 없음. 기존 결과는 `results/technical-backtest/`에 남는다.

### Requirement: 사전 등록 사건과 채점
**Reason**: `technical-backtest` 제거.
**Migration**: 없음.

### Requirement: 예측력 판정 규칙
**Reason**: `technical-backtest` 제거. 일반 판정 기준은 backtest-eval 스킬에 있다.
**Migration**: backtest-eval 스킬을 따른다.

### Requirement: 결과 산출물
**Reason**: `technical-backtest` 제거.
**Migration**: 없음.
