# 구현 진행 및 출처 점검 기록

## 구현 확인 (2026-11-18)

- 구현해 둔 범위: Yahoo 일봉 기반 계산기·Market Analyst 도구·`chart-zones`, Tratto CSV 비교 `chart-check`, 미국 상장 Toss 보유 우선 표본, 평가 상태 이력, random/matched `zone-backtest`, 이력 품질 제외, prospective-only SEC 13F 표본 갱신 및 한국어 Tratto skill.
- 전체 합성/mock 저장소 테스트: **1,927 passed, 1 skipped, 24 warnings, 103 subtests passed**. 생략 테스트는 선택적 `langchain_aws` dependency가 없어 skip됐다. 전체 Ruff 검사와 `git diff --check` 통과.
- 재개 중 `evaluate_sample_frames`의 반복 비용을 줄였다. ticker별 Yahoo 이력은 한 번만 정규화하고 동일 기준일/평가 창의 XNYS 세션 경계는 캐시해 재사용한다. 정규화 1회와 세션 캐시 1 miss 회귀 테스트를 포함해 집중 backtest 테스트 **21 passed**다. 이미 시작된 tune 프로세스는 수정 전 코드를 메모리에 올렸으므로 이 최적화의 영향을 받지 않는다.
- 기본 CLI와 `chart-zones`, `chart-check`, `zone-sample refresh`, `zone-backtest run` help 통과. OpenSpec strict validation 통과.
- Yahoo 공개 실자료 smoke: `AAPL`, `as_of=2026-11-17` CLI가 `ok`, 1,255봉으로 계산됐다. snapshot SHA-256은 `25db721417e5e00792be8cff369116199b4e7258f33233fa7b6b24aac02a2a1a`; Yahoo 과거 수정 가능성 때문에 research-only 근거다.
- 2026-11-19 Tratto runtime에서 50개 도구를 확인했다. Workflow typed declaration과 QQQ `get_chart_data` 원문 fixture를 보존했다. 같은 날 QQQ·TQQQ의 chart-check와 드로잉 앵커 검증을 마쳤다. 초기 연결과 Yahoo DNS 실패는 아래 출처 점검 표에 남겼다.
- Toss `zone-sample refresh`를 읽기 전용으로 실행했다. 현재 표본은 48 ticker, 보유 우선 4 ticker, 미국 외 제외 0, 미국 ticker 매핑 불가 0, 조회 시각 `2026-11-18T07:07:14+00:00`이다. 보유 ticker는 고정 48종목에 모두 겹쳐 추가분은 0이다. manifest/pointer schema와 SHA-256을 검증했고 account id, quantity, market value, raw response는 저장되지 않았다. LLM은 호출하지 않았다.
- v1 검증 최소 기준은 50개 기준일인데 2026년 현재 2024-11 이후 검증 이력은 아직 부족하다. 통과 판정 대신 `inconclusive`가 예상되며 기준일 간격을 임의로 줄이지 않는다.
- SEC ZIP, submissions API와 public reuse 조건의 실제 확인은 아래에 기록했다. 13F 구현은 prospective-only mapping 관측시각 gate 안에서 진행할 수 있다. 과거 CUSIP→ticker point-in-time mapping은 없으므로 과거 코호트를 소급 생성하지 않는다.

## 13F 출처 사전 점검

점검 시각: 2026-11-18. SEC 13F 자료와 식별자 변환의 공식 문서 및 실제 읽기 전용 GET을 확인했다. 원문 13F ZIP과 API body는 파일로 남기지 않았다.

| 출처 | URL | HTTP/응답 | 자료 형식·필드 | 시점·갱신·한도 | 판정 |
| --- | --- | --- | --- | --- | --- |
| SEC Form 13F Data Sets | [SEC 13F datasets](https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets) | 실제 GET: HTTP 200, `application/octet-stream`, 100,719,015 bytes, ZIP signature `504b0304`, SHA-256 `4db97d5652e262de51617971104e06313211de4d092e6bcb5d7bf34ee7efe054`. 인덱스 최신 기간은 2026-06~08, 96.05 MB | 공식 PDF는 7개 UTF-8 tab-delimited 파일과 metadata를 명시한다. submission, cover page, summary, information table을 accession으로 연결 | 분기별 갱신. 분기 마지막 영업일 ET 17:30 이후 제출은 다음 posting에 들어간다. latest bulk period가 아직 2026-08이므로 2026-09 filing은 submissions API와 filing archive에서 확인해야 한다 | 사용. 원본 filing과 SEC 추출 오류 고지를 유지하고 ZIP을 저장소에 넣지 않음 |
| SEC EDGAR submissions / filing archive | [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | 실제 GET: HTTP 200, `application/json`. 최근 13F-HR의 `acceptanceDateTime` 예시 `2026-11-16T21:00:04.000Z`; CIK와 body는 출력·저장하지 않음 | filer filing history와 제출·접수 timestamp | submissions는 filing metadata를 실시간 제공하지만 ZIP 분기 dataset보다 먼저 갱신될 수 있다. bulk에 아직 포함되지 않은 보고는 archive 원문으로 확인 | 사용. `periodOfReport`와 공개 가능 timestamp를 분리하고 다음 XNYS 세션부터만 허용 |
| SEC Form 13F FAQ 및 XML spec | [SEC Form 13F FAQ](https://www.sec.gov/rules-regulations/staff-guidance/frequently-asked-questions-about-form-13f), [SEC XML 정보표 안내](https://www.sec.gov/submit-filings/filer-support-resources/how-do-i-guides/create-xml-information-table-form-13f-using-excel) | SEC 공개 페이지 정상 조회(웹 fetch) | 표에는 CUSIP, class, value(천 달러), shares/principal amount와 SH/PRN, put/call 필드가 존재. `putCall` 옵션 표시와 보통주/ETF title/class 분류를 각각 점검해야 함 | 일반 보고는 분기말 뒤 최대 45일 지연. 수정 신고는 별도 제출이며 원 제출을 소급 덮어쓰지 않음 | 사용. 보통주를 확실히 구분 못하는 항목은 제외 또는 ambiguous로 기록 |
| SEC Official List of Section 13(f) Securities | [SEC 13(f) list](https://www.sec.gov/rules-regulations/staff-guidance/official-list-section-13f-securities) | SEC 공개 페이지 정상 조회(웹 fetch) | CUSIP과 issuer name 중심의 분기별 공식 eligible-security 목록. 일부 기간 TXT와 PDF 제공 | 분기별 게시. 회사 ticker와 과거 effective interval을 제공하지 않음 | 13F 신고 가능 종목 확인용으로 사용; CUSIP→ticker 매핑 대체가 아님 |
| OpenFIGI Mapping API | [OpenFIGI docs](https://www.openfigi.com/api/documentation), [ToS](https://www.openfigi.com/docs/terms-of-service), [FAQ](https://www.openfigi.com/about/faq) | 실제 무인증 mapping GET: HTTP 200 JSON. 공개 CUSIP 한 건은 exchange 제약 없이 303개 결과, `exchCode=US` 적용 시 1개 결과. 실제 ticker와 response body는 기록하지 않음 | CUSIP를 입력해 FIGI 및 instrument metadata를 조회하는 무료 보조 서비스 | 무인증 분당 25요청, 요청당 10 jobs. ToS의 재배포 허용은 FIGI identifier에 한정되고 FAQ는 제3자 proprietary identifier 재배포 제약을 설명한다. 과거 유효기간은 제공되지 않음 | U.S. 거래소 필터 후에도 결과가 정확히 하나일 때만 후보 사용. raw response/CUSIP는 보존하지 않고 ticker sample은 로컬 전용. mapping 관측시각보다 앞선 날짜에 코호트를 적용하지 않음 |
| USD ETF 기준지수 | [ProShares USD](https://www.proshares.com/our-etfs/leveraged-and-inverse/usd) | 운용사 공개 페이지 정상 조회(웹 fetch) | USD는 ProShares Ultra Semiconductors이며 Dow Jones U.S. Semiconductors Index의 일일 2배 수익 목표 | 현재 운용사 설명 확인. 과거 구간에서의 index history는 별도 자료 확인 필요 | sample metadata에 정식 이름 기록. 2배 ETF 별도 코호트 유지 |
| IONQ 합병·첫 거래일 | [IonQ 보도자료](https://investors.ionq.com/news/news-details/2021/IonQ-Becomes-First-Publicly-Traded-Pure-Play-Quantum-Computing-Company-Closes-Business-Combination-with-dMY-Technology-Group-III/default.aspx), [SEC 8-K](https://www.sec.gov/Archives/edgar/data/1824920/000119312521290624/d234711d8k.htm) | 발행사·SEC 자료 정상 조회(웹 fetch) | 합병 완료 2021-09-30, IONQ ticker 첫 거래 2021-10-01 | SEC 제출과 발행사 보도자료의 날짜가 일치 | sample에서 IONQ 가격 이력은 2021-10-01 이전 제외 |

### 출처 점검의 한계와 구현 조건

- SEC 분기 dataset은 `FILING_DATE`만 제공하고 filing accepted timestamp는 포함하지 않는다. submissions API는 최근 accepted timestamp를 실제 제공했지만 latest bulk ZIP보다 앞선 제출까지 일괄 이력 조회를 보장하지 않는다. 단계 4 refresh는 source snapshot과 mapping 관측시각 이후의 다음 XNYS 세션만 eligibility로 삼고, 확인하지 못한 accepted timestamp는 filing date로 대체하지 않는다.
- SEC datasets의 `as-filed` 집계는 amendment가 별도 accession으로 포함된다. 과거 시점의 관측 상태를 만들 때 분기 기준일만으로 현재 최신 amendment를 적용하지 말고 acceptance timestamp 이전 제출만 선택한다.
- CUSIP에서 ticker로 가는 무료 공식 point-in-time 매핑은 확인되지 않았다. OpenFIGI는 비공식·현재 기준·rate-limited이며 표본 1건에서도 exchange 필터를 빼면 후보가 303개로 늘었다. 단계 4는 `exchCode=US`, 정확히 하나의 FIGI/ticker/common-stock match라는 좁은 규칙과 observation timestamp를 적용하며 나머지는 `ambiguous`/`unmapped`로 남긴다. 과거 CUSIP→ticker 매핑을 복원하거나 과거 표본을 채우지 않는다.
- SEC 13F의 45일 제출 지연과 현재 고정 ticker 표본의 선택 편향은 결과 일반화 한계로 공개한다.

## 재개 확인 (2026-11-18)

### 합성 테스트 보강

- ZigZag 경계, `as_of` 반응 창 차단, penetration 재진입 감점, 이중 KDE 모드와 가격순 안정 정렬을 직접 확인했다.
- CLI의 10 ticker 제한·개별 ticker 실패 후 지속·주봉 옵션 거부, Market Analyst `max_tool_rounds` 안에서 `get_chart_zones` 호출을 mock으로 확인했다.
- chart-check 다중 CSV 블록, ET 날짜 변환, 중복·누락 날짜, 허용 오차 경계, range/data 각각 1회 재시도를 확인했다.
- matched 실제 구간 중첩 집계, inside 방향 미정과 activation, baseline 1,000회 거부 상한, bootstrap 빈 분모·block 부족, validation holdout 잠금 및 상태 전이를 합성 자료로 확인했다.
- 최소 50 기준일 미달 평가 fixture는 `inconclusive`다. 이 결과는 synthetic 한 종목·한 기준일에 대한 테스트이며 실자료의 통계 평가가 아니다.
- 재개 후 검증: 집중 신규 테스트 **44 passed**; 전체 저장소 **1,927 passed, 1 skipped, 24 warnings, 103 subtests passed**. 전체 Ruff, 기본 CLI와 신규 CLI help, OpenSpec strict validation도 통과했다. 전체 테스트의 로그인 callback은 첫 샌드박스 실행에서 loopback bind 제한으로 7건 실패했으나, 권한을 허용한 로컬 mock 재실행에서 모두 통과했다.

### 외부 출처 재확인 (승인 후 재시도)

확인 시각: 2026-11-18. Yahoo/SEC/OpenFIGI는 읽기 전용 GET/POST만 사용했다. Toss 계좌 원문·식별자·보유 수량/평가액과 매핑 response body는 출력하거나 저장하지 않았다.

| 출처/절차 | 관찰 결과 | 근거·한계 | 판정 |
| --- | --- | --- | --- |
| Yahoo AAPL CLI smoke (`chart-zones --date 2026-11-17`) | CLI status `ok`, 1,255 bars, CSV rows 1,255, snapshot SHA-256 `25db721417e5e00792be8cff369116199b4e7258f33233fa7b6b24aac02a2a1a` | `/private/tmp/chart-zones-yahoo-smoke-retry`에만 저장. Yahoo split-adjusted, dividend-unadjusted bars; 과거 자료 수정 가능 | 한 종목 계산 smoke 완료; Tratto 비교·전체 통계 검증과는 별개 |
| SEC 13F dataset index / ZIP | 인덱스 최신 기간은 2026-06~08, 96.05 MB. 실제 GET HTTP 200, `application/octet-stream`, 100,719,015 bytes, signature `504b0304`, SHA-256 `4db97d5652e262de51617971104e06313211de4d092e6bcb5d7bf34ee7efe054` | 실제 ZIP은 스트리밍 hash만 계산하고 파일로 저장하지 않음. SEC PDF는 7개 UTF-8 TSV 데이터 파일과 accession 기반 키를 명시 | 출처/파일 gate 통과 |
| SEC submissions API | 실제 GET HTTP 200, `application/json`; 13F-HR `acceptanceDateTime` 예시 `2026-11-16T21:00:04.000Z` | 응답 body와 filer CIK를 출력·저장하지 않음. 현 bulk ZIP은 2026-08까지라 더 최근 filing은 dataset 갱신 또는 filing archive와 연결해야 함 | 공개시각 필드 gate 통과 |
| SEC 재배포 조건 | [SEC Website Dissemination](https://www.sec.gov/about/privacy-information)는 SEC 사이트 정보 복사·추가 배포를 허용하며 SEC 출처 표기를 권고 | SEC/EDGAR 상표·logo 사용 허용과는 별개. 데이터에는 SEC 추출 정확도 disclaimer 적용 | SEC 공개 데이터는 재사용 가능 |
| 무료 CUSIP 매핑 | [OpenFIGI API](https://www.openfigi.com/api/documentation) 무인증 API가 HTTP 200 JSON을 반환했다. U.S. exchange 필터 전 303 결과, `exchCode=US` 적용 후 1개 결과였다. | [ToS](https://www.openfigi.com/docs/terms-of-service)는 FIGI 식별자의 공개 재배포를 허용하고, [FAQ](https://www.openfigi.com/about/faq)는 제3자 식별자 재배포 제한을 설명한다. 무인증 한도 25 req/min·10 jobs/request. current mapping에는 과거 effective interval이 없음 | 구현 gate는 **prospective-only** 범위로 통과. 응답 원문/CUSIP 저장 금지, U.S. 결과가 정확히 1개일 때만 보조 ticker 후보 사용, 매핑 관측 전 기준일에 소급 편입 금지 |
| SEC 실제 13F sample refresh (`zone-sample refresh --source sec`) | 최신 bulk report period `2026-06-30`; 상위 100 CUSIP에서 ticker 10개 `ready`, 단일 매핑 80, ambiguous 14, unmapped 6. 첫 eligible XNYS session `2026-11-19` | SEC ZIP/SQLite work file/sample은 `/private/tmp`에서 처리 후 삭제. ticker·FIGI·CUSIP·position values는 CLI 출력에 없고 임시 파일도 테스트 후 삭제했다. 이 smoke는 Yahoo/Toss/LLM을 호출하지 않음 | 실제 ZIP parser·mapping·pointer 흐름 완료 |
| Tratto MCP runtime / QQQ 차트 (2026-11-19) | 50개 도구 노출. `open_chart(QQQ)` ready; daily 775 bars, loaded range `2023-10-17`~`2026-11-17`. `get_chart_data(last_n=5)`는 summary와 `bars_csv`를 반환 | workflow typed declarations와 원문 응답은 [fixtures/tratto_runtime_tool_schemas.json](fixtures/tratto_runtime_tool_schemas.json), [fixtures/tratto_get_chart_data_qqq_last5.json](fixtures/tratto_get_chart_data_qqq_last5.json)에 저장. raw `tools/list` JSON-RPC export는 runtime에서 제공하지 않음. `set_range` 후 주봉으로 바뀌어 daily로 재설정해야 했음. CSV 안에 XNYS 일요일 `2026-11-15`가 보여 CLI 대조 없이 수용하지 않음 | live response 구조 확인; raw schema 및 data comparison 미완료 |
| Yahoo QQQ `chart-zones --date 2026-11-17` 재시도 3회 | 세 번 모두 Yahoo cookie/crumb 및 history 요청이 `DNSError` | QQQ에 대한 `chart-zones ok` run_dir가 없어 `chart-check`를 실행하지 않음. 실패 호출은 run artifact를 만들지 않음. `chart-check ok`가 없으므로 drawing API와 `read_drawings` 앵커 비교를 호출하지 않음 | Yahoo 네트워크 gate 실패, live drawing 미완료 |
| Toss 보유 sample | `zone-sample refresh` 성공. 48 ticker 중 4개가 우선 처리, 미국 외 제외 0, 미국 ticker 매핑 불가 0, 보유 추가 ticker 0. 조회시각 `2026-11-18T07:07:14+00:00` | 표본 manifest와 pointer의 허용 필드, sample hash 및 ticker-only 저장을 검증했다. 값/계좌 식별자/raw 응답은 출력하거나 저장하지 않음 | 사용자 지정 미국 상장·보유 우선 조건 완료 |

### 표본·통계 및 실행 비용

- `tune`은 2026-11-19 16:28 UTC에 기록 `20335c6118db`를 남겼다. 학습 기준일 범위는 2019-01-02~2024-07-26이며 44개 snapshot 해시를 로컬 CSV와 대조했다.
- `validate`는 2026-11-20 00:21 UTC에 기록 `9a82cfde2877`을 남겼다. 기준일 범위는 2024-11-01~2026-08-07이며 48종목 중 35종목의 snapshot 해시를 로컬 CSV와 대조했다. 가격 자료 없음 9종목, 설명되지 않은 일간 가격 단절 4종목을 기록했다. 두 실행 기록은 `/private/tmp/chart-zone-backtest-run`에 있다.
- 두 구간 유형의 최종 판정은 `inconclusive`였고 저장된 사유는 `primary_sample_data_incomplete`다. Matched 평가에는 유형별 28종목과 기준일 23개가 있어 최소 기준일 50개에 미달했다. 고유 터치 사건은 지지·저항 569건, inside 84건으로 inside도 최소 100건에 미달했다. 두 유형 모두 길이 6·12 설정에서 완전 시간 블록 6개를 확보하지 못했다.
- Toss pointer는 실제 조회시각이 있는 응답으로 갱신됐다. 미국 보유 ticker만 반영하고, 48개 고정 표본과 모두 겹쳐 별도 추가분은 없었다. 기존 합성 fixture는 매도 후 이력 유지, timestamp 누락 시 pointer 불변을 확인한다.
- SEC 출처 gate는 공개 재사용 권한, 실제 ZIP hash, submissions acceptance timestamp, 무료 매핑 한계 확인으로 통과했다. 다만 mapping 결과는 관측 시각 이후에만 효력이 있으며 SEC refresh는 Yahoo/LLM을 호출하지 않는다. 정확한 단일 U.S. match가 없으면 `ambiguous`/`unmapped`로 남기고, 과거 filing으로 과거 코호트를 재구축하지 않는다.

2026-11-19 Chrome 실측에서 `--chart-timezone Asia/Seoul`로 QQQ와 TQQQ의 원본 CSV를 각각 64행 대조했다. 두 종목 모두 `ok`였고, 드로잉 19개씩의 저장 ID와 브라우저 앵커를 확인했다. Yahoo 기술 지표 목록 호출은 두 종목 모두 `UNSUPPORTED_CIQ_HANDLE`을 반환했다.

## 아카이브 확인 (2026-11-23)

- 기준일 2026-11-18인 QQQ·TQQQ의 보존 CSV를 현재 비교 코드로 재검증해 두 종목 모두 `ok`를 확인했다. 기존 드로잉 기록에는 종목별로 좌표 검증을 통과한 저장 ID 19개가 있다.
- 별도 2026-11-20 기준 실행은 두 종목 모두 해당 거래일 봉이 비교 CSV에 없어 `insufficient`였다. 해당 기준일의 검증 상태는 그대로 기록한다.
- 평가 기록 `9a82cfde2877`에서 지지·저항 및 inside 모두 `inconclusive`를 재확인했다. 유효 기준일이 23개로 사전등록 기준 50개에 미달했다.
- 차트·구간 백테스트·표본 집중 테스트 73개가 통과했다. 전체 pytest는 1,991개 통과, 1개 건너뜀(`langchain_aws` 부재), 경고 24개, 하위 테스트 103개 통과였다. Ruff, 기본 및 차트 관련 CLI 도움말, OpenSpec 변경 strict 검증도 통과했다.
