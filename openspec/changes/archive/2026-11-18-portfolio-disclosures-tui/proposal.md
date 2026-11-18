# 공개 포트폴리오 공시 TUI skill

## Why

기관 투자자 Form 13F와 미국 하원의원 주식 거래 공시를 한 화면에서 볼 재사용 흐름이 없다. 13F 정보표는 수십~수천 행이고 하원 PTR은 PDF라서, 에이전트가 원문을 눈으로 읽어 합계·비중·분기 변화를 내면 숫자가 틀리기 쉽다. 계산은 결정론적 스크립트가 맡고, 출력은 좁은 터미널에서도 열이 맞는 고정폭 텍스트여야 한다.

## What Changes

- `.agents/skills/portfolio-disclosures/`에 skill과 스크립트 `scripts/disclosures.py`를 추가한다. 표준 라이브러리와 저장소 헬퍼만 쓰며, 앱 CLI(`tradingagents`)는 바꾸지 않는다.
- 13F: CIK나 운용사 이름으로 제출자를 찾는다. 최근 두 보고기간의 13F-HR에 수정 신고를 반영해 보고 가치, 비중, 상위 보유, 신고 주식 수 변화(신규·증가·감소·유지·미보고)를 낸다. SEC 요청에는 저장소 `sec_edgar`의 User-Agent·속도 제한과 `get_with_retry`를 그대로 쓴다.
- 하원: Clerk 연도별 색인(ZIP 안 XML)에서 PTR을 찾는다. 전자 제출 PDF에서 거래일, 구분, 티커, 금액 구간, 소유를 읽으며, 빈 사용자 암호로 RC4 암호화된 PDF도 포함한다. 스캔 PDF는 판독 불가로 표시한다.
- 출력: 78칸 고정폭 텍스트. 위에서부터 대상별 한 줄 요약, 대상별 상세, 해석 한계 순서다. 에이전트는 출력을 코드 블록으로 그대로 옮긴다.
- 데이터 출처 점검(2026-11-18):

| 출처 | URL | HTTP 상태 | 형식 | 기준일·시각 | 한도·요구 | 판정 |
| --- | --- | --- | --- | --- | --- | --- |
| SEC 제출 목록 | https://data.sec.gov/submissions/CIK0001067983.json | 200 | JSON. `recent`는 최근 1,000건, 이전은 `files` 페이지 | `filingDate`, `reportDate` | 연락처 User-Agent, 초당 10회 미만 | 사용 |
| SEC 제출 원문 | https://www.sec.gov/Archives/edgar/data/1067983/000119312526463399/0001193125-26-463399.txt | 200 | 문서별 `<TYPE>`과 XML(표지, INFORMATION TABLE) | 보고기간 2026-09-30, 제출 2026-11-16 | 위와 같음. 2023-01-03 이전 제출은 가치가 천 달러 단위 | 사용 |
| EDGAR 전문 검색 | https://efts.sec.gov/LATEST/search-index?forms=13F-HR&entityName=bridgewater | 200(한 번 500 응답 뒤 재요청 200) | JSON. `entity_filter` 집계에 이름·CIK | 날짜 범위 지정 | 문서화된 API는 아니며 sec.gov 검색 화면이 쓰는 공개 경로 | 이름 검색에만 사용. CIK 지정이 대안 |
| 하원 PTR 색인 | https://disclosures-clerk.house.gov/public_disc/financial-pdfs/2026FD.zip | 200 | ZIP 안 XML·TXT. 이름, 지역구, 유형(P=PTR), 제출일, DocID | 2026FD.xml 수정 2026-11-17 | 연도별 파일 | 사용 |
| 하원 PTR 원문 | https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/2026/20035780.pdf | 200 | PDF. 전자 제출은 Type0 글꼴과 ToUnicode, 표본 절반은 빈 사용자 암호 RC4-128(R3). DocID 8·9로 시작하는 스캔본은 이미지 | 거래일, 통지일, 서명일 | 없음 | 사용(스캔본 제외) |
| 2차 의원 거래 자료(House Stock Watcher) | https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/data/all_transactions.json | 403 | 확인 불가 | 확인 불가 | 확인 불가 | 사용 불가(접근 차단) |

## Out of Scope

- 상원의원 공시 전체(2026-11-18 사용자 결정). 공식 출처 eFD(https://efdsearch.senate.gov/search/home/)는 브라우저가 아닌 요청을 403(Akamai)으로 막고 세션마다 이용 동의를 요구한다.
- 앱 CLI 명령, 대시보드, 상시 추적·알림, 결과 캐시
- 하원 연간 재무공시(자산 목록) 해석, 스캔 PDF 문자 인식
- CUSIP→티커 변환, 분할 보정, 실제 매매 추정, 현재 보유·평가액 산출, 매매 추천
- 유료 의원 거래 API(Quiver, FMP 등)
