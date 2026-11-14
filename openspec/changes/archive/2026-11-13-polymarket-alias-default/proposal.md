# Polymarket 기본 별칭 연결

## Why
별칭 연결을 매 실행마다 지정하지 않아도 Polymarket 공개 검색이 별칭 경로를 사용하도록 기본값을 바꾼다.

## What Changes
Polymarket 전송 설정이 없을 때 `cloudfront_alias`를 사용한다. `direct`는 명시 설정으로 선택할 수 있다. 진단과 네트워크 정책의 기본 경로도 같은 설정을 따른다. TLS 인증서 검증, 리다이렉트 거부, 실패 시 공식 경로로의 자동 전환 금지는 유지한다.

## Out of Scope
IP 또는 네트워크 자동 감지, 자동 경로 전환, 별칭 DNS 검증 규칙 변경은 포함하지 않는다.
