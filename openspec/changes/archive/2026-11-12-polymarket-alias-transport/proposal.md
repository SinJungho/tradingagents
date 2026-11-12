# Polymarket 선택형 별칭 연결
## Why
회사 네트워크에서 공식 호스트 연결이 실패할 때 별도 서버 없이 공개 검색 연결을 선택한다.
## What Changes
기본 direct와 선택형 cloudfront_alias 설정, 시스템 DNS canonical name 검증, TLS 검증 및 리다이렉트 거부를 추가한다. doctor와 네트워크 정책에 별칭 목적지를 구분한다. 기존 재시도와 회로 차단기를 유지한다.
## Out of Scope
주문, 인증 API, 고정 IP·별칭, 자동 경로 전환, 로컬 프록시는 추가하지 않는다.
