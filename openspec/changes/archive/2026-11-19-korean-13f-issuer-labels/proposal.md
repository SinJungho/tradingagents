# 13F 종목명에 한국어 이름과 티커 표시

## Why

사용자는 13F 표의 `BROOKFIELD CORP`를 `브룩필드 코퍼레이션 (BN)`으로 표현해 달라고 요청했다. 13F 원문에는 티커가 없으므로 확인된 종목명만 별칭으로 표시해야 한다.

## What Changes

- 확인된 13F 발행사 표시명을 한국어 이름과 티커로 바꾸고, 표·신규·미보고 목록에서 같은 표기를 사용한다.
- 첫 확인 별칭은 `BROOKFIELD CORP` → `브룩필드 코퍼레이션 (BN)`이다. 티커는 Brookfield Corporation 공식 FAQ에서 확인했다.
- 별칭이 등록되지 않은 발행사는 원문명을 유지하며 티커를 추측하지 않는다.

| 출처 | URL | HTTP 상태 | 형식 | 기준일·시각 | 한도·요구 | 판정 |
| --- | --- | --- | --- | --- | --- | --- |
| Brookfield Corporation 주주 FAQ | https://bn.brookfield.com/share-information/faqs | 확인 불가(브라우저 GET에서 정상 페이지 확인, 상태 코드는 노출되지 않음) | HTML | 현재 FAQ; 클래스 A 보통주 심볼은 NYSE·TSX 모두 BN | 공개 페이지, 인증 불필요 | 사용 |

## Out of Scope

- 등록되지 않은 모든 13F 발행사의 자동 티커 검색·한국어 이름 생성
- 보유 가치, 비중, 순위, 분기 비교 변경
