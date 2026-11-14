# 검증 기록

## 구현 범위
Polymarket 공개 검색의 direct/cloudfront_alias 연결을 추가했다. 기존 공급자 선택과 독립적이며 기본값은 direct이다. 시스템 resolver의 AI_CANONNAME 결과만 사용하고 고정 IP·별칭은 저장하지 않는다. 별칭 URL이 requests의 TLS SNI 및 인증서 검증 호스트가 되고 HTTP Host만 공식 호스트를 유지한다. 3xx는 비재시도 실패이며 TLS 검증은 두 모드 모두 켜져 있다.

## 무인증 공개 검색 실측

2026-11-12 07:16 UTC, 사용자가 지정한 현재 회사 Wi-Fi 환경이라고 간주한 워커에서 public-search GET을 실행했다. 브로커·LLM·로그인·인증 파일과 .env는 사용하지 않았다. 각 측정의 자동 재시도는 끄고 HTTP 시도 1회로 제한했다. 첫 실패가 재시도 가능한 경우에만 같은 모드로 한 번 재측정했다. 검색어와 응답 본문은 저장하지 않았다.

| 연결 / 검색 주제 | 측정 | 결과 |
| --- | --- | --- |
| direct / 연준 금리 | 최초 + 재측정 | 두 번 모두 connection 오류, HTTP 상태 없음 |
| cloudfront_alias / 연준 금리 | 최초 | HTTP 200, JSON 객체, events 3개 및 시장 항목 12개. 공급자 보고서는 반환됐지만 표시할 열린 일치 시장은 없음 |
| cloudfront_alias / Bitcoin | 후속 통합 확인 | HTTP 200, JSON 객체, events 20개 및 시장 항목 154개. 공급자 보고서에 시장 3개가 포맷되어 반환됨 |

회사 Wi-Fi라는 환경 표시는 사용자 제공 정보에 따른다. 이 측정은 해당 시점 검색 결과만 확인했으며, 집·핫스팟은 미검증이다. 별칭 성공은 공식 경로 복구를 뜻하지 않는다. CDN·DNS 또는 네트워크 정책 변경으로 별칭 경로가 다시 실패할 수 있다.

## 자동 검증
- 집중 테스트: 47 passed.
- 전체 pytest: 1723 passed, 1 skipped, 24 warnings, 103 subtests passed. skip은 선택 의존성 langchain_aws 미설치.
- Ruff, 설치된 tradingagents --help, git diff --check 통과.
- OpenSpec strict 검증 후 구현; 완료 후 아카이브 및 전체 spec strict 검증.
- 기존 미커밋 변경 보존, stage·commit 미실행.
