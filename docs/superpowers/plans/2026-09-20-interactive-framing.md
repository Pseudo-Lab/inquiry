# Interactive Framing Implementation Plan

> **For agentic workers:** Use test-driven-development and verification-before-completion for each task. 기존 분리 worktree를 유지하며 커밋·푸시는 하지 않는다.

**Goal:** `python -m inquiry chat` 한 번으로 ID/JSON 없이 사용자가 직접 Framing을 테스트한다.

**Architecture:** 일반 터미널의 입력/출력 루프가 기존 FramingService를 호출한다. 저장·Run·승인 계약을 바꾸지 않으며 CLI의 지연 OpenAI factory를 공유한다. Gate B 전에는 승인 후 텍스트 요약만 보여 준다.

**Tech Stack:** Python 3.9+, 표준 input/print/unittest, 기존 선택 의존성. 새 라이브러리 없음.

## Global Constraints

- [승인된 설계](../specs/2026-09-20-conversation-gitlog-design.md)와 ADR-D7/D9를 따른다.
- 사용자 키 파일은 읽거나 변경하지 않는다. 실제 유료 API를 대신 호출하지 않는다. 검증은 임시 데이터와 fake adapter로 수행한다.
- Git-log TUI/클릭 상세/AI 탐구 연산/Actions/export를 구현된 것처럼 표시하지 않는다.
- 기존 단발 CLI와 fake adapter 주입 호환성을 유지한다. 현재 `.venv`는 보존하고 추가 설치하지 않는다.

## Task 1 — 대화 루프와 재개

**Files:** 생성 `inquiry/interactive.py`, `tests/test_interactive.py`.

**Interface:** `run_conversation(root, *, adapter_factory, read=None, write=None, max_output_tokens=None, timeout=60.0)`; read는 prompt를 받아 문자열을 반환하고 write는 문자열 하나를 출력한다. 기본은 input/print다. factory는 기존 `(adapter, model)` 계약이다.

- [x] RED: fake 응답 `control → done control → frame`과 입력 `seed → Generate → 답변3개 → Generate → Accept`로 inquiry 생성, suggested 상태, 세 번의 모델 실행을 확인한다.
- [x] RED: 미응답 질문 복원, pending 제안 Save & Exit/Accept, accepted 요약은 factory 호출0으로 검증한다. 여러 draft는 번호로 선택한다.
- [x] RED: Reject 이유 저장 후 Regenerate 선택 전 호출0, 취소/미종결 Run의 명시 Resume, blank 입력 재요청, EOF/Ctrl-C 종료, 저장 실패 후 성공 화면 미표시를 검사한다.
- [x] 구현: draft 선택 → 복구 선택 → 미응답 질문 → pending 승인 메뉴 → 생성 메뉴 순서로 저장 상태를 분기한다. 생성 메뉴는 `1 Generate / 2 Save & Exit`; 생성 실패는 같은 메뉴에서 명시 재시도만 허용한다. Reject 뒤에는 `1 Regenerate / 2 Save & Exit`다. 메뉴/seed/답변에서 `/exit`로 종료한다.
- [x] 제안은 8항목과 후보별 title/claim/difference를 출력한다. 모델/사용자 문자열의 터미널 제어 문자는 표시용 이스케이프로 바꾸고 저장 원본은 변경하지 않는다. raw JSON·내부 세션/질문 ID는 입력 대상으로 노출하지 않는다.
- [x] GREEN: `python3 -S -m unittest tests.test_interactive -v`.

## Task 2 — 명령 연결과 공통 factory

**Files:** 수정 `inquiry/cli.py`, 생성 `tests/test_chat_cli.py`.

- [x] RED: `main(['--dir', root, 'chat'], adapter=fake)`의 전체 대화와 `chat --help`, 모델/토큰/시간 제한, 저장된 inquiry를 SDK 없이 조회하는 경로를 검사한다.
- [x] 기존 nested OpenAI factory를 `_openai_factory(root, model, max_output_tokens, timeout)` helper로 이동해 `framing next`와 `chat`이 동일한 설정/SDK/안내 경계를 사용한다. 새 SDK 호출 구현을 복제하지 않는다.
- [x] chat은 동일한 제한 옵션과 명시 adapter 주입을 제공한다. 입력 종료는 저장된 기록만 보존한다. StoreError/OSError는 재시도하지 않고 상위 CLI의 안전한 오류 경로로 보낸다.
- [x] GREEN: `.venv/bin/python -m unittest tests.test_chat_cli tests.test_openai_cli tests.test_framing_flow tests.test_interactive -v`.

## Task 3 — 바로 실행하는 안내와 검증

**Files:** 수정 `inquiry/README.md`, 설계 상태; 생성 `docs/reports/interactive-framing-eval.md`.

- [x] README 맨 앞에 현재 저장소에서 `.venv/bin/python -m inquiry chat` 한 줄로 실행하는 빠른 시작을 둔다. 승인 후 아직 지도 대신 요약임을 명시한다.
- [x] 실제 터미널 입출력은 임시 inquiry + fake adapter로 확인한다. 실제 사용자의 질문 이해도·모델 품질 평가를 대신하지 않는다.
- [x] 전체 테스트 `.venv/bin/python -m unittest discover -s tests -q`, SDK 없는 focused 테스트, compileall, diff check를 수행한다.
- [x] 독립 리뷰에서 무호출 재개, 승인 경계, 명시 재생성/재시도, 오류/종료, 사용자 실행 안내를 확인한다. 결과와 한계를 기록하고 Gate B는 미검증으로 유지한다.

## 자체 점검

단일 대화형 진입에 범위를 한정했다. 새 UI 프레임워크·지도 통합·네트워크 테스트는 없다. 같은 저장 코어를 사용하므로 별도 UI 데이터베이스나 승인 로직이 필요 없다. 설계 승인과 실제 사람 사용성 검증은 구분한다.
