# 실제 자료 확인 (2026-11-18 KST)

조건: Claude 세션(외부 네트워크 있음), 결과 캐시 없음. SEC 요청은 `.env`의 `SEC_EDGAR_USER_AGENT`를 썼다(값은 기록하지 않음).

| 확인 | 대상 | 결과 |
| --- | --- | --- |
| 13F 수치 | `--filer 1067983`(Berkshire) | 2026-09-30 보고 $304.2B, 30종목. 신규 1·증가 4·감소 6·유지 19·미보고 0, AAPL 비중 25.0%, BAC 주식 수 -5.7%. 원문 정보표를 별도 정규식으로 합산한 값과 모두 일치 |
| 수정 신고 | Berkshire 2025-03-31 | NEW HOLDINGS 13F-HR/A가 D R Horton·Lennar·Nucor 3종목 $1.11B를 더함. 수정 신고 tableValueTotal $1,106,550,356과 일치 |
| 이름 검색 | "bridgewater associates", "warren buffett", "pershing square" | CIK 1350694로 조회. 13F 제출자 없음(본인은 13F-NT만 제출). 후보 2개(CIK 2026053, 1336528) 나열 |
| 대형 제출자 | `--filer 19617`(JPMorgan) | 8,235종목, $1.8T. 대상 4개 전체 실행 약 5초 |
| 하원 PTR | Pelosi, Gottheimer, Greene, Johnson, Khanna | 전자 제출 PTR 20건을 모두 판독(빈 사용자 암호 RC4 암호화본 포함). 거래는 각각 16·22·6·21건. Khanna의 최근 5건은 스캔본이라 판독 불가로 표시 |

한계

- 성만 주면 그 성의 PTR 제출자가 한 명일 때 바로 조회한다("Johnson" → Julie Johnson TX32). 출력에 나온 이름과 지역구로 대상을 확인해야 한다.
- EDGAR 전문 검색이 연속 요청 중 한 번 500을 돌려줬고, 다시 요청하자 200이었다. 계속 실패하면 CIK로 지정한다.
- 암호화 판독 근거는 실제 PTR(20035143 등)을 복호화해 거래 행이 나온 것이다. 합성 테스트는 같은 키 유도 함수로 만든 왕복 자료라서 키 유도 자체를 독립 검증하지는 않는다.
