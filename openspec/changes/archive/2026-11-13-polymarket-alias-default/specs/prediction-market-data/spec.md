## MODIFIED Requirements

### Requirement: Polymarket 선택형 별칭 연결
시스템 MUST 전송 설정이 없을 때 Polymarket 공개 검색에 `cloudfront_alias`를 사용해야 한다. `direct`는 명시 설정된 경우에만 사용해야 한다. 잘못된 설정은 오류로 처리해야 한다. 별칭은 시스템 resolver의 공식 호스트 canonical name에서 얻은 유효한 cloudfront.net 하위 DNS 이름이어야 한다. 별칭 HTTPS URL과 TLS SNI를 사용하고 HTTP Host는 공식 호스트를 유지해야 한다. 인증서 검증을 켜고 리다이렉트를 거부하며 30초 timeout, 최대 3회 HTTP 시도와 실행 단위 회로 차단기를 유지해야 한다. 경로 자동 전환은 금지한다.

#### Scenario: 기본 별칭 경로
- **WHEN** 전송 방식이 명시되지 않은 상태에서 Polymarket 공개 검색을 요청할 때
- **THEN** 시스템은 CloudFront 별칭 URL을 사용하고 별칭 인증서를 검증하며 공식 Host로 공개 검색을 요청한다

#### Scenario: direct 명시 선택
- **WHEN** 사용자가 `polymarket_transport`를 `direct`로 명시할 때
- **THEN** 시스템은 공식 Gamma API 호스트로 공개 검색을 요청한다

#### Scenario: 별칭 선택
- **WHEN** `cloudfront_alias`가 명시되고 유효한 별칭을 얻을 때
- **THEN** 별칭 인증서를 검증하고 공식 Host로 공개 검색을 요청한다

#### Scenario: 별칭 또는 TLS 실패
- **WHEN** 별칭이 없거나 허용되지 않거나 인증서 검증에 실패할 때
- **THEN** 공식 경로로 우회하지 않고 unavailable과 안전한 실패 분류를 기록한다

#### Scenario: 리다이렉트 응답
- **WHEN** 공개 검색이 3xx를 반환할 때
- **THEN** 리다이렉트를 따라가지 않고 조회 실패로 처리한다
