# Tasks

- [x] 1. 빠른·심층 모델 기본값과 tier별 reasoning effort 적용
  - [x] 1.1 빠른 모델을 `gpt-6-luna`, 심층 모델을 `gpt-6.1-sol`로 설정
  - [x] 1.2 전역 설정이 없을 때 빠른 OpenAI tier에 `xhigh` 적용
  - [x] 1.3 전역 reasoning effort와 모델 환경 변수 재정의 유지
- [x] 2. CLI 모델 목록, 문서와 회귀 테스트 갱신
  - [x] 2.1 OpenAI 심층 모델 선택 목록에 `gpt-6.1-sol`을 추가
  - [x] 2.2 설정 예제와 포트폴리오 안내의 기본값 갱신
  - [x] 2.3 기본값, 빠른 tier effort, 전역 override를 mock 테스트로 검증
- [x] 3. 저장소 검증 및 OpenSpec 아카이브
  - [x] 3.1 포커스 테스트와 전체 pytest 실행
  - [x] 3.2 Ruff, CLI help, OpenSpec 검증 실행
  - [x] 3.3 필수 작업이 완료되면 변경 아카이브
