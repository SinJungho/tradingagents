## ADDED Requirements

### Requirement: 확인된 13F 종목명 표기

13F 상세 표와 신규·미보고 목록은 등록된 발행사 표시명을 한국어 회사명과 확인된 티커로 표시해야 한다 (MUST). 아직 등록되지 않은 발행사는 SEC 원문명을 유지하고 티커를 추측하지 않는다.

#### Scenario: Brookfield 별칭

- **WHEN** 13F 발행사명이 `BROOKFIELD CORP`일 때
- **THEN** 상세 표와 신규·미보고 목록에 `브룩필드 코퍼레이션 (BN)`으로 표시한다

#### Scenario: 알 수 없는 발행사

- **WHEN** 13F 발행사명에 확인된 표시 별칭이 없을 때
- **THEN** SEC 원문명을 그대로 표시하고 확인되지 않은 티커를 추가하지 않는다
