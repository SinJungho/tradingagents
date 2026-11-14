# Polymarket 기본 예측시장 공급자

## Why

현재 운용에서 예측시장 자료는 Polymarket을 사용하지만, 기본 설정과 네트워크 정책 내보내기는 Kalshi를 선택하고 있다. 이 불일치로 하네스가 사용하지 않을 Kalshi 주소를 요구하고 실제 사용할 Polymarket 주소를 놓칠 수 있다.

## What Changes

- 기본 `prediction_markets` 공급자를 Polymarket으로 설정한다.
- Kalshi는 명시 설정으로 계속 선택할 수 있게 한다.
- README, OpenSpec 요구사항, 합성 라우팅·네트워크 정책 테스트를 새 기본값에 맞춘다.

## Out of Scope

- Kalshi 공급자 구현 제거 또는 API 동작 변경
- Polymarket 전송 모드와 TLS 검증 변경
- 공급자 간 자동 전환
