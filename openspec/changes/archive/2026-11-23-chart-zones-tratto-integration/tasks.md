## 사전 검토

- [x] 저장소 AGENTS.md, 관련 코드, 2026-11-18 제거 결정, 기존 skill/OpenSpec 범위 확인
- [x] Toss 고정 표본은 미국 상장 ticker만 포함하고 보유 ticker를 처리 우선순위로 둔다. 한국 상장은 XNYS v1에서 제외한다.
- [x] 기본 48종목과 보유 추가분의 코호트·보유 확인 시점·개인정보 최소화 규칙을 명시한다.
- [x] SEC 13F 공식 필드, 공개시점, 수정 신고, 보고 단위, 13(f) 목록, CUSIP 매핑 위험을 문서화한다.
- [x] USD 추종 지수와 IONQ 합병 완료일/첫 거래일을 출처 문서로 고정한다.
- [x] SEC 실제 gate를 확인했다: quarterly ZIP HTTP 200·ZIP signature·SHA-256, submissions JSON HTTP 200·accepted timestamp, SEC 공개 자료 재사용 조건, 무인증 OpenFIGI 결과 수/쿼터/약관을 기록했다. 현재 CUSIP→ticker 이력은 없으므로 13F는 관측 시각 이후에만 효력이 있는 prospective-only 코호트로 구현한다.

## 단계 1: Yahoo 구간 계산 및 CLI

- [x] `chart_zone_params=v1`, 고정 상수, Yahoo `auto_adjust=False`/actions, vendor router 등록
- [x] XNYS `as_of`, Yahoo 실패 기록 경로, 5년 snapshot hash, unknowns 및 최소 504봉 처리
- [x] Wilder ATR, 확정 ZigZag, 고정 KDE 50% HDR·최대 폭·동점·겹침 규칙 구현
- [x] Market Analyst `get_chart_zones` 도구와 숫자 evidence 경로 등록
- [x] LLM 없이 실행하는 `chart-zones` CLI와 ticker별 부분 실패·해시 경로 구현
- [x] 동등 입력 재현, 미래 행 불변, XNYS 경계, 부족/결측·잘못된 OHLC, Yahoo 인자, snapshot bytes 합성 테스트
- [x] 피벗 경계 누출, 반응 window 차단, penetration 재진입, KDE 다봉/경계, score tie를 각각 직접 검증한다.
- [x] 전체 48종목, 최대 10개, 주봉 미지원, Market Analyst 호출 예산 회귀 테스트를 추가한다.
- [x] Yahoo 실자료 한 종목을 네트워크가 허용되는 환경에서 확인하고 결과를 source failure와 구분해 기록한다. `AAPL` 1,255 bars, `ok`, snapshot SHA-256 `25db721417e5e00792be8cff369116199b4e7258f33233fa7b6b24aac02a2a1a`.

- [x] 마지막 확정 ZigZag 스윙의 피보나치 되돌림 앵커·비율 가격·`fib_start`/`fib_end` 확인 window를 출력하고 ok/invalidated/unavailable 합성 테스트를 추가한다.

- [x] 스윙 시작·최근 실적 발표 앵커의 일봉 Anchored VWAP과 `avwap_earnings` 확인 window를 출력하고, 발표 시각·미래 일정·결측·LLM 입력 축소 합성 테스트를 추가한다.

## 단계 2: Tratto chart-check 및 skill

- [x] `chart-check` 날짜 정규화·비교·허용오차·원문 CSV 저장·재시도 metadata 구현
- [x] `.agents/skills/tratto-chart/` 한국어 절차, 50개 도구 카탈로그, 차트 작업·삭제 제한 references 작성
- [x] 계산 파라미터 v1 reference와 전역 Codex/Claude skill link 구성
- [x] 활성 Tratto runtime의 50개 도구 목록과 실제 workflow 입력 선언을 저장하고, QQQ `get_chart_data` 원문 응답 fixture를 보존한다.
- [x] raw JSON-RPC `tools/list` JSON Schema를 확인한다.
- [x] chart-check 다중 원문 블록·윈도별 겹침·날짜/중복/누락/시간대/허용오차 경계 테스트를 완료한다.
- [x] 실제 브라우저에서 chart-check `ok` 후 드로잉하고 `read_drawings` 앵커 및 drawing ID를 검증한다.

- [x] Tratto 5년 일봉 수집·Python 피벗 분석, 장기·최근 추세선, 목적별 보조 도구 선택 절차를 문서화한다.

## 단계 3: 고정 표본 및 zone-backtest

- [x] 기본 48종목을 코드에 고정하고 미국 Toss ticker 정규화·우선순위·10종목 batch·매도 후 유지·불변 revision 구현
- [x] 합성 Toss adapter fixture로 비밀 최소화·한국 ticker 제외·조회 시각 누락을 검증한다.
- [x] append-only evaluation 파일과 `latest_evaluation`, `last_passed_evaluation`, `effective_status`, `pending`, `stale` 상태 projection 구현
- [x] 최신 failed/inconclusive가 과거 passed를 effective 상태로 덮지 않는 합성 테스트
- [x] XNYS 기준 과거 `as_of`, 60세션 embargo, validation holdout 잠금, 결과 기록 및 189/378/756 반감기 학습 민감도를 구현한다.
- [x] 터치 다음 봉 판정, same-bar 실패, 세션 결측 제외, unmatched 분리, random/matched baseline, 조건부·전체 유효 hit·touch rate를 구현한다.
- [x] 종목 cluster와 날짜 원형 block bootstrap 3/6/12, 10,000회 고정 seed, 최소 표본 gate를 구현한다.
- [x] matched 폭/거리 caliper, 실제 구간 overlap 공시, primary endpoint·Bonferroni 단측 기준·분리 코호트 정책을 사전 고정한다.
- [x] 표본 이력 1% 결측·분할 설명 가격 단절 필터와 IONQ 2021-10-01 시작일을 적용하고 제외 사유/품질값을 평가 기록에 보존한다.
- [x] 임계값·inside 활성화/방향 미정·matched overlap·세 block·bootstrap 분모 0/부족 조건과 holdout lock을 직접 검증하는 합성 테스트를 보강한다.
- [x] 고정된 ticker 이력을 사건별 평가에서 반복 복사·정렬하지 않도록 하고 평가 결과 동등성을 검증한다.
- [x] 사건별 반복을 줄이기 위해 동일 `as_of`/평가 창의 XNYS 세션 경계를 재사용하고 캐시 적중을 테스트한다.
- [x] 20세션 간격 기준 50개 미만 validation 날짜는 합성 평가에서 `inconclusive`인지 확인한다.
- [x] 고정 48종목 표본으로 Yahoo tune 및 validation을 실행하고 확보한 snapshot hash·이력 품질·최소 표본 결과를 기록했다. Validation에서 35종목을 사용했고, 가격 자료 없음 9종목과 일간 가격 단절 4종목을 기록했다. 두 구간 유형 모두 `inconclusive`다.
- [x] 현재 Toss 보유 종목을 `zone-sample refresh`로 읽기 전용 조회해 미국 상장만 저장되는지와 보유 우선순위를 확인한다. 48 ticker 중 보유 우선 4, 미국 외 제외 0, 매핑 불가 0, 고정 sample 밖 추가 0이며 pointer/manifest schema·hash·민감 필드 부재를 확인했다.

## 단계 4: 13F 동적 표본

- [x] SEC 실제 출처/약관 gate 이후 filing 공개와 dataset/mapping 관측 다음 XNYS 세션부터 편입한다. current mapping은 관측시각보다 앞선 기준일에 적용하지 않는다. 실제 refresh smoke는 eligible session `2026-11-19`를 만들었다.
- [x] 고정 48종목·Toss 보유·13F 코호트를 분리하고 13F 지연·보고 모집단·공동 재량 중복·매핑 시점 bias flag를 sample/평가에 기록한다.
- [x] amendment/late filing, report 단위, security type/option/ETF, CUSIP mapping 모호성과 미매핑을 synthetic/mock fixture로 검증한다.
- [x] `zone-sample refresh --source sec`로 SEC ZIP 및 mapping을 처리하고 immutable input hash, ambiguous/unmapped 기록, private cache와 외부 주간 scheduler 안내를 추가한다. 실제 SEC refresh smoke에서 10 ticker cohort가 생성됐고 임시 파일을 삭제했다.

## 전체 검증 및 마무리

- [x] 합성·mock 확인 뒤 허용된 Yahoo 실자료 smoke를 수행한다. AAPL 1,255 bars, `ok`, snapshot hash를 README에 기록했다.
- [x] Tratto 실제 MCP schema와 브라우저 드로잉 확인을 수행한다. QQQ와 TQQQ에서 확인했다.
- [x] `pytest -q`, `ruff check .`, 기본 CLI 및 신규 CLI help를 통과시킨다. 최신 전체 suite는 1,927 passed, 1 skipped, 24 warnings, 103 subtests passed다.
- [x] OpenSpec strict validation을 통과시키고 구현 task/spec 상태를 동기화한다.
- [x] 검증·단계 수용 조건을 확인하고 OpenSpec 변경을 아카이브한다. 마감 검증 결과는 README에 기록했다.

- [x] 차트 CSV 시간대 인자와 서울 시간대 일봉 검증을 추가한다.
