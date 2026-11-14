## ADDED Requirements

### Requirement: Polymarket 선택형 별칭 연결
시스템 MUST 공개 검색에만 기본 direct 또는 cloudfront_alias 연결을 사용하고 잘못된 설정은 오류로 처리해야 한다. 별칭은 시스템 resolver의 공식 호스트 canonical name에서 얻은 유효한 cloudfront.net 하위 DNS 이름이어야 한다. 별칭 HTTPS URL과 TLS SNI를 사용하고 HTTP Host는 공식 호스트를 유지해야 한다. 인증서 검증을 켜고 리다이렉트를 거부하며 30초 timeout, 최대 3회 HTTP 시도와 실행 단위 회로 차단기를 유지해야 한다. 경로 자동 전환은 금지한다.

#### Scenario: 별칭 선택
- **WHEN** cloudfront_alias를 선택하고 유효한 별칭을 얻을 때
- **THEN** 별칭 인증서를 검증하고 공식 Host로 공개 검색을 요청한다

#### Scenario: 별칭 또는 TLS 실패
- **WHEN** 별칭이 없거나 허용되지 않거나 인증서 검증에 실패할 때
- **THEN** 공식 경로로 우회하지 않고 unavailable과 안전한 실패 분류를 기록한다

#### Scenario: 리다이렉트 응답
- **WHEN** 공개 검색이 3xx를 반환할 때
- **THEN** 리다이렉트를 따라가지 않고 조회 실패로 처리한다

### Requirement: 별칭 진단 구분
시스템 MUST doctor에서 공식 경로와 선택된 별칭 경로를 구분하고 HEAD 도달성과 검색 GET 성공을 구분해야 한다. 네트워크 정책은 선택한 별칭 목적지 또는 해결 실패를 표시해야 한다. 로그에는 검색어·응답 본문·인증정보를 남기지 않아야 한다.

#### Scenario: 별칭 경로 진단
- **WHEN** 별칭 연결이 선택된 상태에서 doctor를 실행할 때
- **THEN** 공식 경로 실패를 숨기지 않고 별칭 Host를 적용한 HEAD 결과를 별도로 표시하며 GET은 미검증이라고 알린다
