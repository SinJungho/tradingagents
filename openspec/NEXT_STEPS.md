# 후속 작업 목록

최종 갱신: 2026-11-24

## 현재 상태

- fork 작업 브랜치 `work/local-improvements`에 작업별 모델 프리셋, 장기 추세선 검증, 시장 스트레스 지표, 포트폴리오 시장 근거 점검을 정리했다.

- `work/local-improvements`에서 포트폴리오 실패 진단, 미국장 공통 리서치, 차트 구간·Tratto 연동, 리서치 하네스 지침을 검증한 로컬 커밋으로 정리했다.

- 브랜치·PR: fork(`SinJungho/tradingagents`) PR #1~#6이 `main`에 병합됐다(PR #6: 2026-11-20, merge commit `3586252` — 공시 스냅샷 skill, 샌드박스 네트워크 정책, 사용 한도 오류 분류). `scoped-sandbox-network-access`는 2026-11-20 기준 커밋 새 워크트리에서 독립 Codex·Orca 세션 재현 후 아카이브했다.
- 차트 선 긋기 제거(2026-11-18): 선 긋기와 차트 분석을 Yahoo Finance + 차트 MCP 연동으로 별도 구현해 이 저장소의 선 후보·구조선·피보나치·AVWAP·시나리오 경계와 기존 `chart-eval` 실험(가격 채점·9셀 토론), `technical-backtest`를 제거했다. 복구용 백업은 `results/_backup-line-drawing-removed-2026-11-18.tgz`(git 비추적). 상세: `openspec/changes/archive/2026-11-18-remove-chart-line-drawing/`.
- 차트 구간·Tratto 연동: Yahoo 계산기·Market Analyst 도구·CLI, chart-check·skill, Toss 보유 우선 표본, zone-backtest, SEC 13F prospective cohort를 구현하고 2026-11-23에 아카이브했다. 2026-11-19 QQQ·TQQQ의 chart-check와 브라우저 드로잉을 확인했다. 2026-11-20 종료한 Yahoo validation은 48종목 중 35종목의 이력을 사용했고, 기준일 23개로 최소 50개에 미달했다. 두 구간 유형 모두 `inconclusive`다. [상세 기록](changes/archive/2026-11-23-chart-zones-tratto-integration/README.md)
- 최신 기술 분석 제거(2026-11-18): `chart_eval`과 `technical-latest`(Toss 일봉 지표·차트·보고서)를 삭제했다. 차트 분석은 Yahoo Finance + 차트 MCP로 별도 진행한다. 상세: `openspec/changes/archive/2026-11-18-remove-technical-latest/`.
- 공개 포트폴리오 공시(2026-11-18): `portfolio-disclosures` skill과 `scripts/disclosures.py`가 SEC 13F(수정 신고 반영, 분기 비교), 하원 연간 재무공시 주식 보유(금액 구간 순, 2026-11-19), 하원 PTR(RC4 암호화 PDF 포함)을 78칸 고정폭 표로 보여준다. 상원의원은 사용자 결정으로 범위에서 뺐다. 상세: `openspec/changes/archive/2026-11-18-portfolio-disclosures-tui/`.
- 시장 보고서
  - 실제 LLM 재평가(Red 64, Blue 78; 이전 52, 73)의 지적을 고쳤다: 뉴스 50건 조회와 공급자 한도 표시, 금리 관측일 불일치 비고, DXY(ICE DXY) 라벨, 핵심 요약의 최대 변동 포함, 지수 이름 숫자의 해석 검사 제외. 기록: `results/market-reports/2026-11-12-a80efcde3994475289e8c78f4777e5ea/quality-review.md`.
  - 표기: 머리말 시각 ET 통일, 다음 개장 이후 생성 주의, "해당 없음" 값 칸, DXY·WTI·금 직전 거래일 대비 변화율, 저가치 헤드라인 제외와 기사 표, 시장 폭 제외·실패 종목은 앞 10개와 "외 N개".
  - 장후 판정: 금요일 선물은 17:00 ET 주말 휴장, NYSE 조기 폐장일(2026-11-27, 12-24 등)은 선물 폐장 15분 뒤·주식 17:00 ET 기준.
  - LLM 해석은 검증(JSON·근거 ID·숫자 금지)에 실패하면 사유를 붙여 1회 재요청하고, 시도별 거부 사유를 `evidence.json`에 남긴다. 2026-11-15 정상 생성 조건 실제 LLM 확인에서 해석 15개가 첫 응답에 통과했다: `results/market-reports/2026-11-13-0c2731a3a9724b8b8fe913ddee75c901/quality-review.md`.
  - 재현성 1일 차(2026-11-13 대상, 다음 개장 전 생성): `results/market-reports/2026-11-13-e986363a3f9b40d19b0ba87846b6bcd0/quality-review.md`. 11월 16·17일 대상 예약 보고서는 현재 로컬 결과 폴더에서 확인되지 않는다. 11월 19·20일의 보존 보고서 3건에서 시장 폭과 품질 경고를 비교했다. [비교 기록](changes/archive/2026-11-23-verify-chart-drawing-evidence/README.md)
- 종목 발굴
  - 가격·SEC·분할 병렬 조회(작업 8개), SEC 초당 8회 공용 제한, Yahoo 적응형 속도 제한(429마다 간격 2배), 일시 실패(`VendorUnavailableError`) 심볼 2차 조회.
  - SEC companyfacts 404(CIK는 있으나 XBRL 재무 사실 없음, 주로 신규 상장)는 공급자 실패가 아닌 자료 없음으로 처리하고 2차 조회하지 않는다(2026-11-16). 이전에는 `get_with_retry`가 붙인 상태 코드를 읽지 못해 모든 SEC HTTP 오류가 실패로 집계됐다.
  - 시총 스크리너를 거래소 상장주로 제한(Yahoo 10,000행 페이지 한도 회피), 실패 원인 문구 보존.
  - 실측: `sp500`(503종목) 빈 캐시 718초 → 142초. `all`(5,654종목) 빈 캐시 45분, SEC 캐시 23분, 종목 실패 1.6~5.1%(Yahoo 상태에 따라 다름). 시총 구간 대형 908·중형 1,083·소형 1,443·초소형 2,120.
- 설정(2026-11-15): `SEC_EDGAR_USER_AGENT`에 사용자 연락처를 설정했고 SEC·BLS 요청이 그 값으로 200 응답을 받는 것을 확인했다(값은 기록하지 않음).
- 운영: `orca.yaml` setup이 워크트리마다 `.venv`를 만든다(2026-11-15 기본 설정 워크트리에서도 별도 승인 없이 실행 확인). `results/`는 품질 평가 기록만 추적한다. 같은 IP에서 `discover --universe all`을 하루 여러 번 실행하면 Yahoo가 지연 제한을 누적하므로 하루 한 번 정도로 둔다.
- 결정 기록(2026-11-13): Russell 2000은 무료 대체 출처가 없어 실패 표시를 유지한다. 실적 공시 표본은 7개를 유지한다. Codex 샌드박스 외부 네트워크는 열지 않고 코디네이터가 출처를 확인한다.

- 드로잉 완료 검증기: `chart-drawings-check`로 Tratto 추가·재사용의 조회와 화면 증거를 검사한다. [드로잉 확인·백테스트 제외 기록](changes/archive/2026-11-23-verify-chart-drawing-evidence/README.md)

## 사용자 작업

에이전트가 대신할 수 없거나 사용자 결정·환경이 필요한 일이다.

| 순서 | 작업 | 이유와 방법 | 규모 |
| --- | --- | --- | --- |
| 1 | fork PR 반영 결정 | 검증한 로컬 커밋을 fork PR에 반영할지 정한다. | 작음 |

## 우선순위

| 우선순위 | 후속 작업 | 근거 | 규모 | 사용자 결정 |
| --- | --- | --- | --- | --- |
| 1 | `all` 실패율 재측정(선택) | SEC 404 구분 뒤 `discover --universe all` 실패율이 얼마나 줄었는지 측정하지 않았다(2026-11-15 실패 93건, 같은 로그의 SEC 404 110줄). Yahoo 지연 제한을 피해 하루 한 번만 실행한다. | 중간 | 불필요 |
| 2 | GOOGL LLM 그래프 재개 | 2026-11-17 `--ticker GOOGL --date 2026-11-16 --checkpoint` 실행이 ChatGPT 구독 사용량 한도로 Research Manager 단계에서 멈췄다. 한도가 풀린 뒤 같은 명령으로 재개하면 Trader·Risk·PM 결정을 얻는다. | 작음 | 실행 시점 |
| 3 | 공시 스냅샷 보강(선택) | PTR 옵션 행사가·만기(설명 칸), 하원 연간 재무공시의 수정 신고 반영은 아직 하지 않는다. 요청이 있을 때 `data-source-check`부터 한다. | 중간 | 필요 여부 |
| 주기 확인 | Russell 2000 출처 | iShares IWM AJAX가 CSV 대신 HTML을 반환한다(2026-11-16 08:47 KST 재확인도 동일. 2026-11-15에는 기본·기준일 지정·JSON 형식 모두 HTML, 경로 축약은 404). Vanguard·SSGA·FTSE Russell 무료 대체 없음. 복구 전까지 `discover --universe russell2000`은 실패한다. | 작음 | 유료 출처는 범위 밖 |
| 출처 재확인 | 미국 파생·ETF 주간 자료 | Cboe SPX 옵션 통계와 ICI 주간 ETF 순발행은 CLI에서 403이었다. 공개 시각과 저장 조건을 확인할 수 있는 출처가 생기면 자동 수집을 재검토한다. CME 공식 미결제약정·FedWatch를 쓰려면 이용 조건을 먼저 확인한다. | 작음 | 신규 유료 계약은 현재 범위 밖 |

## 다음 시작점

차트 구간 예측력은 고정 표본 이력과 사전등록한 20세션 간격·기준일 최소 50개 조건이 충족되면 재평가한다.
