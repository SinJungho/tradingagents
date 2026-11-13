# 시장 보고서 BLS 공식 발표 시각 수집

## Why

다음 거래일 일정에서 CPI·고용·PPI 같은 BLS 발표는 FRED 날짜만 있어 발표 시각이 미확인으로 남았다. 코디네이터의 2026-11-13 네트워크 확인에서 BLS 공식 ICS 일정은 연락처가 담긴 User-Agent로 요청하면 HTTP 200으로 응답했고, 연락처가 없으면 HTTP 403이었다. 이는 SEC EDGAR와 같은 자기 식별 규칙이므로 저장소의 SEC User-Agent 규칙을 그대로 따르면 브라우저 위장 없이 수집할 수 있다. DOL 보도자료는 연락처 User-Agent로도 403이어서 주간 실업수당 시각은 계속 확인할 수 없다.

## What Changes

- BLS 공식 ICS 일정을 수집해 선별 발표의 예정 시각을 미국 동부시간 `scheduled_at`으로 붙인다. `TZID=US-Eastern`은 `America/New_York`으로 해석하고 줄 접기와 CRLF를 처리한다.
- FRED 날짜 항목과 발표명이 같은 BLS 발표는 기존 Census·BEA와 같은 방식으로 하나의 일정으로 합친다.
- BLS 일정 조회 성공 후 선별 발표가 없으면 `none_found`, 조회 실패는 `unavailable`로 표시한다.
- 기존 'BLS·DOL 공식 일정' 미수집 항목을 'DOL 주간 실업수당 일정' 미수집 항목으로 바꾼다.

## Out of Scope

DOL 주간 실업수당 발표 시각 수집, 유료 일정 공급자, 브라우저 위장 등 접근 제한 우회, 관행에 근거한 시각 추정, 실제 보고서 생성.
