# ChatGPT 플랜 인증 목적지 반영
## Why
선택 공급자 기준 정책에서 불필요한 OpenAI 인증 호스트는 제외하지만, ChatGPT 플랜 인증을 선택한 실행에는 이 호스트가 필요하다.
## What Changes
네트워크 정책은 ChatGPT 플랜 인증이 설정되었을 때만 auth.openai.com 목적지를 포함한다. API 키 인증에서는 해당 목적지를 생략한다.
## Out of Scope
인증 흐름, LLM 공급자 선택 및 네트워크 접근 권한 적용은 변경하지 않는다.
