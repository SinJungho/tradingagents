# 환경별 검증 기록

검증 시각: 2026-11-13T02:05:05.544297+00:00. 현재 실행 네트워크이며 집 네트워크라는 근거는 없다.

| 경로 | HTTP 상태 | JSON 파싱 |
| --- | --- | --- |
| cloudfront_alias (기본) | 200 | 성공 |
| direct (명시 선택) | 응답 미확보: ConnectionError | 확인 불가 |

TLS 검증과 리다이렉트 거부, netrc 인증 미사용을 유지했다. 공개 `public-search` GET만 실행했으며 응답 원문은 기록하지 않았다. 코드·기본 설정·README·기존 transport 테스트의 별칭 기본값 일치를 확인했다.

## 실패 시 조정

`tradingagents doctor`로 경로·네트워크 진단을 확인한다. 집 환경에서 동일 GET을 실행해 상태·파싱·시각을 기록한 뒤에만 E3를 완료한다. 경로 조정이 필요하면 `TRADINGAGENTS_POLYMARKET_TRANSPORT=direct` 또는 `cloudfront_alias`를 명시적으로 설정한다. IP 자동 전환이나 TLS/리다이렉트 제한 완화는 하지 않는다. 현재 direct 실패 기록을 성공 기록으로 덮어쓰지 않는다.
