## 1. 정책 산출

- [x] 1.1 현재 실행 설정에서 안전한 LLM·데이터 endpoint 목적지를 수집한다
- [x] 1.2 `tradingagents network-policy --format json` 명령을 추가한다
- [x] 1.3 원시 URL·비밀값을 출력하지 않고 loopback 및 확인 불가 endpoint를 구분한다

## 2. 워커 안내

- [x] 2.1 api-doctor 지침에 Orca 실행 호스트 정책 적용과 워커 내 사후 진단 절차를 추가한다
- [x] 2.2 README에 제한형 egress 정책 내보내기 명령과 적용 범위를 설명한다

## 3. 검증 및 정리

- [x] 3.1 변경 파일의 정적 검사와 CLI 도움말을 확인한다
- [x] 3.2 OpenSpec 변경안과 capability spec을 strict 모드로 검증한다
