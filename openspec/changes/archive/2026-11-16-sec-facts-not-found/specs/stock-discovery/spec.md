## ADDED Requirements

### Requirement: SEC 재무 사실 없음 구분

시스템 MUST SEC companyfacts 요청이 HTTP 404를 받으면 그 종목을 공급자 실패가 아닌 자료 없음(XBRL 재무 사실 없음)으로 처리해야 하며, 일시 실패 2차 조회 대상에 넣지 않아야 한다. 다른 HTTP·연결 오류는 기존처럼 공급자 실패로 남겨야 한다.

#### Scenario: CIK는 있으나 XBRL 재무 사실이 없는 회사

- **WHEN** 종목의 CIK는 확인되고 companyfacts 요청이 HTTP 404일 때
- **THEN** 종목 발굴은 그 종목에 "SEC EDGAR annual facts" 실패를 기록하지 않고 해당 팩터를 자료 없음으로 보류하며, 같은 요청을 다시 보내지 않는다

#### Scenario: SEC 서버 오류

- **WHEN** companyfacts 요청이 HTTP 503일 때
- **THEN** 기존처럼 공급자 실패로 기록되고 2차 조회 대상이 된다
