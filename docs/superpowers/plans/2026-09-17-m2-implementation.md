# M2 Core Integration Implementation Plan

> **For agentic workers:** 구현은 `executing-plans`로 작업 단위별 진행한다. 독립 작업을 나눌 필요가 있을 때만 `subagent-driven-development`를 적용한다. 이 문서는 계획이며 구현 착수나 게이트 통과를 뜻하지 않는다.

**Goal:** 사용자가 로컬 탐구를 만들고, 가설을 탐색·결정하며, 재시작 후에도 같은 상태를 복원하고 Markdown으로 내보내는 최소 흐름을 완성한다.

**Architecture:** `.inquiry/events.jsonl`을 유일한 원본으로 두고 메모리 상태와 문서를 재생성한다. 연산은 검증된 변경 묶음을 만들고, 모델 호출과 터미널 화면은 도메인 밖 어댑터로 연결한다. 프로토타입의 고정 fixture를 제품 데이터로 사용하지 않는다.

**Tech Stack:** Python, 표준 라이브러리 JSON/파일 처리/unittest, 기존 OpenAI SDK. 새 패키지는 이 계획으로 자동 승인하지 않는다. TUI 라이브러리는 M2-0B에서 실제 요구사항에 맞춰 선정하며 코어 저장 구현과 분리한다.

작성: 2026-09-17. 갱신: 2026-09-21. 상태: **M2-4B-3 Challenge 구현·검증·리뷰 완료 / Gate B 미검증**. [계획 검토](../../reports/m2-plan-review.md) · [최신 결과](../../reports/m2-4b3-challenge-eval.md).

사용자 선택은 [ADR-D7](../../decisions/ADR-D7-staged-m2-gates.md)에 기록했다. 저장·복원 코어와 잔여 UX 검증을 병행하고, TUI 통합 전에 UX 검증을 마친다.

## Global Constraints

- 정본: [D1](../../decisions/ADR-D1-storage-format.md), [D2](../../decisions/ADR-D2-graph-model.md), [D3](../../decisions/ADR-D3-confidence-model.md), [D4](../../decisions/ADR-D4-agent-adapter.md), [D5](../../decisions/ADR-D5-state-machine.md), [D6](../../decisions/ADR-D6-cost-model.md), [제품 §18](../../PRODUCT-CONCEPT.md), [M2 범위](../../MILESTONES.md).
- 단일 사용자·로컬·수동 연산. API 결과는 제안이며 자동 상태 확정이나 외부 게시를 하지 않는다.
- 데이터는 append-only 이벤트에서 복원한다. Markdown과 화면은 projection이다. SQLite·서버·동기화는 추가하지 않는다.
- DAG-only, 여러 부모를 가진 합류 허용. 실패/종료 가설과 근거를 삭제하지 않는다.
- 출처 없는 단일 confidence 점수를 만들지 않는다. D3의 허용 evidence 유형은 초기에 지키고 자동 채점·집계는 M3로 남긴다.
- 클릭·키보드로 지도 노드를 골라 상세를 여는 UX와 브랜치 전체 요약은 MVP 이후다. M2에는 ID를 지정한 기본 조회만 둔다.
- 다중 에이전트, 애니메이션, 실시간 presence/claim/lease, 의미 중복·포화 탐지, 웹 뷰어, Markdown import는 범위 밖이다.
- 기존 `prototypes/`와 실제 키·로컬 실행 기록은 보존한다. 기본 테스트는 네트워크와 키 없이 실행해야 한다.

## 0. 착수 조건과 결정 기록

| 항목 | 현재 근거 | 필요한 처리 |
|---|---|---|
| M0 | D1~D6 모두 Accepted | 문서의 오래된 Proposed 표기를 정정하고 ADR 정본을 참조 |
| M1a | 자동 5종·실제 답변 재개 검증 완료 | 최초 사용 UX 미검증을 [마감 보고서](../../reports/m1a-closeout.md)에 유지. 반복 인터뷰 대신 진행 가능한 범위와 남은 확인을 명시적으로 판단 |
| M1b | 사용자 Git-log 디자인 선택, 9조합 75페이지 자동 검사 | [규모 보고서](../../reports/m1b-scale-eval.md)의 18페이지 탐색 부담과 임의 DAG 한계를 검토. 디자인 선택을 전체 UX 통과로 확대하지 않음 |
| 화면 의미 | 사용자 승인: 위→아래 계보, 옆으로 분화 | 기존 위=지지/아래=반박 규칙과의 차이를 정본의 시각 규칙에 기록 |
| TUI 방식 | 현재는 정적 stdout + macOS 이미지 도구 | 지속형 화면과 명령 입력을 제공할 도구를 비교해 선정. 이미지 생성기는 제품 런타임이 아님 |
| D5 close/reopen | 탐색 중→사람 종료는 현 전이표에 없음 | 허용되지 않은 close를 코드로 추가하지 않는다. 필요한 변경은 ADR 수정으로 별도 결정 |

M2-0 산출물은 [m2-entry-check.md](../../reports/m2-entry-check.md)다. **M2-0A/Gate A**는 D1~D6와 검토된 계약을 확인한 뒤 저장·복원 코어 착수를 허용한다. **M2-0B/Gate B**는 남은 M1a/M1b UX·시각 규칙 정합·TUI 도구를 코어 개발과 병행해 확인한다. Gate B가 미해결이어도 Gate A 범위의 코어 작업은 가능하지만, M2-6은 시작하지 않는다. 검증 생략이나 무조건 통과로 처리하지 않는다.

TUI 선정 확인 항목: 한국어 셀 정렬, 80/120/160열, 지도와 명령 입력의 동시 표시, 긴 결과를 통한 레이아웃 유지, 종료 시 터미널 복구, 단일 실행의 취소 표시. 이 작은 검증에서 라이브러리와 추가 의존성 필요성을 확정한다. 마우스 노드 선택은 평가 범위에 넣지 않는다.

## 1. 작업 순서

| 단위 | 결과 | 선행 |
|---|---|---|
| M2-0A | 코어 착수 조건 기록 | D1~D6, D7, 계획 critic 검토 |
| M2-0B | 잔여 UX·TUI 선택 기록 | M1a/M1b 결과; 코어와 병행 |
| M2-1 | 이벤트 저장·검증·재생 | M2-0A |
| M2-2 | Inquiry/Hypothesis/Evidence와 DAG·상태 규칙 | M2-1 |
| M2-2A | 최소 실행 계약·fake adapter·복구 | M2-2 |
| M2-3 | Framing draft 재개·승인 후 탐구 생성 | M2-2A |
| M2-4 | OpenAI 구현 연결과 5개 탐구 연산 | M2-3 |
| M2-5 | 기본 조회·Actions·Weekly·Markdown export | M2-4 |
| M2-6 | 실제 데이터로 지속형 터미널 흐름 연결 | M2-5 및 M2-0B/Gate B |
| M2-7 | §18의 10개 시나리오 완주·재시작 검증 | M2-6 |

각 단위는 실패 테스트 → 최소 구현 → 전체 관련 테스트 → 변경 검토 순으로 진행한다. 커밋·푸시는 별도 사용자 요청 범위에 맞춘다.

## 2. 파일과 경계

아래는 구현 경로다. M2-1에서 루트 `inquiry/`와 `tests/` 및 이벤트·저장·최소 모델·재생 파일을 만들었다. 나머지는 후속 작업의 예정 파일이다. 최종 CLI 명령 이름은 M3 공개 전 확정한다.

| 파일 | 책임 |
|---|---|
| `inquiry/__init__.py`, `inquiry/__main__.py` | 패키지와 `python -m inquiry` 진입점 |
| `inquiry/events.py` | 버전 있는 이벤트 형식·변경 묶음 검증 |
| `inquiry/store.py` | JSONL append/read, 단일 writer, 손상 감지 |
| `inquiry/model.py` | Inquiry, Hypothesis, Evidence, Action, Run, State 값 |
| `inquiry/replay.py` | 이벤트를 메모리 State로 재생 |
| `inquiry/graph.py`, `inquiry/transitions.py` | DAG·참조·상태/주체 불변식 |
| `inquiry/commands.py` | 검증된 변경 묶음을 만드는 도메인 명령 |
| `inquiry/framing.py` | 기존 질문 프롬프트·Q&A 재사용, 구조화 프레임 제안 |
| `inquiry/runs.py` | Run 기록·중단 복구·사용량 집계, 모델과 도메인 변경 분리 |
| `inquiry/adapter.py`, `inquiry/openai_adapter.py` | 공급자 독립 실행 계약과 OpenAI 구현 |
| `inquiry/projections.py` | 기본 노드 조회, 지도용 데이터, Weekly/Markdown |
| `inquiry/cli.py`, `inquiry/tui.py` | 입력·출력·선택된 TUI 라이브러리 경계 |
| `tests/test_*.py`, `tests/fixtures/` | 아래 수용 기준과 네트워크 없는 실행 fixture |

`prototypes/m1a-framing`의 문자열 프레임을 정규식으로 제품 데이터에 역파싱하지 않는다. 프롬프트는 재사용하되, 승인할 프레임을 타입/스키마로 검증한 뒤 저장한다. `prototypes/m1b-layout`의 고정 연결선도 실제 DAG 렌더러로 간주하지 않는다.

## 3. M2-1 — 먼저 저장·복원만 완성

**파일:** `events.py`, `store.py`, `model.py`, `replay.py`, `tests/test_store.py`, `tests/test_replay.py`.

**입출력 계약 제안:**

```python
# 변경 묶음 하나가 JSONL 한 줄이다. 아래는 필드 계약이지 구현 코드가 아니다.
Event = {
    "schema_version": 1, "event_id": "unique-id", "seq": 1,
    "inquiry_id": "I-001", "actor": "human:local", "at": "UTC ISO-8601",
    "type": "changes-committed", "changes": []
}
# store.append(event, expected_seq) -> None
# store.read_all() -> list[Event]
# replay(events) -> State
```

한 inquiry 디렉터리에 `.inquiry/events.jsonl` 하나를 둔다. 순서 번호·고유 event_id·버전을 검증하고, 변경 묶음 전체를 미리 검증한 뒤 한 줄로 append 및 flush/fsync한다. 재생에서 불완전한 마지막 줄이나 중간 손상을 만나면 해당 줄을 알리고 수정·추가 쓰기를 중단한다. 자동 잘라내기·덮어쓰기는 하지 않는다. 한 로컬 writer만 허용하고 충돌하면 명확하게 실패시킨다.

저장 위치는 `inquiry new --dir <path>`로 정한 로컬 디렉터리다. 최초 draft 시작 시 inquiry_id를 예약하되, 승인 전에는 Inquiry 객체나 가설을 만들지 않는다. 예약 ID의 로그에는 Framing session과 Run 기록만 있을 수 있다. `changes`는 `kind`로 구별되는 비어 있지 않은 변경 목록이며, 각 종류의 필수 필드를 검증한 뒤 append한다. 질문/답변·실행 기록도 같은 D1 로그를 사용한다. event_id 중복은 저수준 Store에서 거부하고, 재개 명령의 중복 처리는 저장된 session_id/proposal_id/run_id로 명령 계층이 no-op 처리한다.

- [x] `test_store.py`: 한 이벤트 append→새 Store에서 읽기, 두 writer 충돌, 중복 ID/seq 거부, 빈 로그, 잘린 마지막 줄, 중간 JSON 손상, 미지원 버전 거부.
- [x] `test_replay.py`: 같은 로그를 두 번 재생하면 같은 상태, 이벤트를 읽는 것만으로 추가 이벤트/모델 호출 없음.
- [x] 검증 실패 전후 원본 바이트가 동일한지 확인했다. 실제 디스크 쓰기/동기화 실패는 부분 기록이 남을 수 있어 결과 불확실성으로 보고하며 자동 rollback/truncate하지 않는다.
- [x] `python3 -m unittest discover -s tests -v` 실행: 코어 22개 통과, 별도 리뷰 APPROVE.

**완료 기준:** 프로세스를 종료해도 재개 가능한 최소 원본 저장소가 있고, 손상 시 조용히 일부만 복원하거나 데이터를 삭제하지 않는다. API·TUI는 아직 필요 없다.

## 4. M2-2 — 관계와 상태를 이벤트로만 변경

**파일:** `model.py`, `graph.py`, `transitions.py`, `commands.py`, `replay.py`, `tests/test_graph.py`, `tests/test_transitions.py`.

객체 최소 필드:

- Inquiry: id, seed, frame, hypothesis_ids, action_ids.
- Hypothesis: id, title, claim, parent_ids, status, assumptions, falsified_if.
- Evidence: id, type, uri/quote 또는 직접 수집한 내용, retrieved_at, actor.
- Evidence link: evidence_id, hypothesis_id, relation=`supports`/`challenges`.
- State: inquiry(승인 전에는 없음), ID별 객체, framing_sessions, runs, 마지막 seq. ID는 재시작 뒤 재사용하지 않는다.

`branches-from`은 가설의 계보, `supports`/`challenges`는 Evidence와 가설의 관계다. UI fixture의 ‘Support 브랜치’를 그대로 근거 객체로 취급하지 않는다. 에이전트 반론은 검증 전 가설/메모이지 자동 Evidence가 아니다.

상태 전이 변경은 D5의 `{from,to,trigger,actor,at,reason?}`를 그대로 포함한다. 현재 from과 맞지 않는 오래된 변경은 거부한다. 허용표에 없는 전이도 거부한다. 사람 전용 전이를 agent가 요청하면 제안으로 남길 수 있으나 적용하지 않는다.

- [x] 자기 참조·간접 순환·중복 부모·존재하지 않는 참조를 거부하는 테스트를 먼저 작성한다.
- [x] 두 부모 합류를 저장·재생하고 원래 부모를 모두 보존한다.
- [x] D5의 허용 전이를 표 기반으로 검사하고 나머지를 거부한다. 허용표에 없는 `exploring → human-closed`를 조용히 허용하지 않는다.
- [x] `refuted`/`human-closed`에 이유·근거 스냅샷·재개 조건이 없으면 거부한다. 확인된 외부 근거가 없다는 스냅샷도 명시적으로 표현할 수 있게 한다.
- [x] 근거 유형 allowlist를 검사하고 `llm-opinion`을 거부한다. confidence는 M2에서 기본 생성하지 않는다.
- [x] `python3 -m unittest discover -s tests -v` 실행: 코어 41개 통과, 별도 리뷰 APPROVE.

**완료 기준:** 명령에서 만든 변경 묶음을 재생해도 동일한 그래프·상태가 나오며, 화면이나 export가 원본 상태를 직접 수정하지 못한다.

### 근거·상태의 실제 명령 경로

M2-2에서 아래 명령과 `tests/test_decisions.py`를 함께 구현한다. `--by`로 agent를 human처럼 가장하는 옵션은 두지 않는다. 로컬 사용자가 실행한 CLI는 `human:local`, 어댑터 이벤트는 agent 주체로 분리한다.

| 명령 | 필수 입력과 효과 |
|---|---|
| `evidence add <H-ID> --supports/--challenges --file <path> --type <allowed-type> --retrieved-at <UTC> [--uri <uri>]` | 관계는 둘 중 하나만. 외부 자료는 uri와 수집 시점 필수. 파일 내용을 불변 스냅샷으로 저장하고 EvidenceCreated+EvidenceLinked를 한 변경 묶음으로 기록. 가설 상태는 자동 변경하지 않음 |
| `evidence link <E-ID> <H-ID> --supports/--challenges` | 기존 근거를 다른 가설에 연결. 없는 ID·중복 링크는 거부 |
| `start <H-ID>` | suggested→exploring, 사람의 탐색 시작 승인 |
| `support <H-ID> --evidence <E-ID> --reason <text>` | exploring/contested→supported. 현재 가설에 연결된 근거만 허용 |
| `contest <H-ID> --evidence <E-ID> --reason <text>` | exploring/supported→contested. 판단과 이유를 기록 |
| `refute <H-ID> --evidence <E-ID> --reason <text> --reopen-if <text>` | exploring/contested→refuted, 근거 스냅샷과 재개 조건 보존 |
| `suspend <H-ID> --reason <text>` | exploring→suspended |
| `reopen <H-ID> --reason <text> --condition-evidence <E-ID>` | suspended/refuted/human-closed→exploring. 재개 조건 충족 여부를 사람이 확인하고 현재 inquiry의 근거 참조와 판단 이유를 기록. 자동 조건 추론·자동 재개는 없음 |

위 명령은 D5의 기존 허용표만 구현하며 `close` 허용 확대는 하지 않는다. Evidence 파일에 LLM 의견을 붙인 것을 외부 근거로 위장하지 않도록 출처를 표시하며, 허용 타입 검증만으로 자료 진위까지 자동 판정할 수 있다고 주장하지 않는다.

통합 테스트 여정: Framing 승인으로 만든 suggested 두 개 → 각각 start → 사람의 실제 출처 fixture를 evidence add/link → support/contest → 두 부모 synthesize → 재시작 후 원래 근거·부모·상태 확인. 상태 enum을 테스트 코드로 직접 주입해 이 경로를 건너뛰지 않는다. `python3 -m unittest discover -s tests -p 'test_decisions.py' -v`로 실행한다.

M2-2 실행 기록: 현재는 수동 `init`/`hypothesis add`로 suggested 가설을 생성한 뒤 위 결정 경로를 검증했다. 실제 Framing 승인의 연결 검증은 M2-3에서 같은 여정에 추가한다. 수동 `synthesize`는 사람이 준 title/claim을 저장하는 코어 명령이며 M2-4의 모델 제안 기능을 앞당겨 구현한 것은 아니다.

## 4A. M2-2A — Framing 이전의 실행 계약

구현 완료: RunStarted/RunDispatched/중간 신호/terminal과 proposal·usage 원자 저장, 명시 복구·중복 방지, 정리 오류 진단을 추가했다. 실제 I/O의 제한은 어댑터가 준수하며 Runner는 신호 사이에서 협조적으로 취소/timeout을 검사한다. 전체 테스트 69개와 별도 재리뷰 APPROVE. 실제 API 연결은 아직 하지 않았다.

**파일:** `adapter.py`, `runs.py`, `model.py`, `replay.py`, `tests/fakes.py`, `tests/test_runs.py`.

`Adapter.run(request) -> Iterator[RunSignal]` 계약과 fake adapter를 먼저 만든다. `RunRequest`는 reserved inquiry_id, run_id, optional session_id, operation, target_ids, context, model, max_output_tokens, timeout을 가진다. `RunSignal`은 progress/heartbeat/최종 proposal/usage 또는 실패·취소 신호다. 모델을 호출하는 코드는 오직 어댑터에 두고, `runs.py`가 started·terminal 기록과 취소를 관리한다. Framing의 질문/프레임 생성부터 이 경로를 쓴다. OpenAI 구체 구현은 M2-4에서 연결한다.

### Run 저장·복구·사용량 계약

- 호출 전에 `RunStarted`를 append한다. provider_request_id는 알려졌을 때 기록하며 키·인증 헤더는 저장하지 않는다.
- 성공 시 `RunSucceeded`와 proposal(또는 질문 batch), 수신한 최종 usage를 **같은 변경 묶음**에 저장한다. 저장 전에는 성공 제안을 사용자에게 승인 대상으로 노출하지 않는다.
- `RunFailed`/`RunCancelled`에는 reason과 usage_status를 포함한다. provider 결과가 미확인이면 provider_outcome=`unknown`으로 남긴다.
- usage_status는 `known`, `unknown`, `not-started`다. known은 provider가 보고한 0 이상의 input/output_tokens, unknown은 두 필드 모두 null, not-started는 요청을 보내기 전에 취소/검증 실패한 경우만 0이다. est_cost는 가격·출처가 없으면 null이다. 누적 표시는 ‘확인된 토큰 합계 + 사용량 미확인 실행 N개’로 한다.
- 단일 writer를 획득한 뒤의 명시적 재개 명령은 terminal이 없는 started Run에 `RunFailed(reason=process-interrupted, provider_outcome=unknown, usage_status=unknown)`을 한 번 기록한다. 단순 로그 replay/조회는 아무것도 append하지 않는다. 두 번째 재개는 이미 종결된 Run을 변경하지 않는다.
- API 성공 직후 로컬 저장 전에 죽으면 완료 여부를 알 수 없다. 이 경우도 unknown이며 자동 재호출하지 않는다. 사용자가 다시 실행하면 새 run_id를 사용한다. SDK의 암묵적 요청 재시도는 꺼 두어, 모르는 과금/결과를 한 실행으로 숨기지 않는다.
- 최종 usage는 run_id별 한 번 집계한다. `RunUsageReported`를 추가로 받는 경우 동일 값은 no-op, 상충하는 값은 오류로 기록 없이 거부한다. known usage를 unknown으로 덮어쓰지 않는다. 부분 progress의 토큰 수를 최종 usage와 이중 합산하지 않는다.

Run 복구 테스트는 started 직후 종료, 일부 progress 뒤 종료, usage 없는 취소, provider 성공 후 append 전 종료, append 성공 후 출력 전 종료를 각각 주입한다. 기대 결과는 그래프 미변경 또는 저장된 proposal 한 개이며, 알려진 사용량의 중복 집계와 unknown→0 변환이 없어야 한다. `python3 -m unittest discover -s tests -p 'test_runs.py' -v`로 실행한다.

## 5. M2-3 — Framing에서 저장 가능한 Inquiry로

**파일:** `framing.py`, `commands.py`, `cli.py`, `tests/test_framing_flow.py`.

흐름: `FramingStarted`로 draft 생성 → 누적 3~5문항 → 구조화된 8항목 프레임/2~4개 후보 → 저장된 제안 미리보기 → 사람 승인 → `FrameAccepted`, `InquiryCreated`, `HypothesisCreated`를 한 변경 묶음으로 기록. M2-2A fake adapter를 주입해 먼저 검증하며 직접 SDK를 호출하지 않는다.

`FrameProposal`은 8항목, 각 후보의 title/claim/차별 축, 원본 Q&A를 가진다. 모르는 부분은 미정이다. 새 가설 상태는 suggested로 저장하고, 사람이 탐색을 요청할 때 exploring 전이를 별도로 기록한다. 저장된 답변으로 재개하면 질문 수와 내용을 이어받는다.

### 승인 전 draft 저장

| 변경 kind | 필수 데이터와 기록 시점 |
|---|---|
| FramingStarted | session_id, reserved inquiry_id, seed. 첫 모델 호출 전 기록 |
| QuestionsIssued | session_id, batch_id, qid별 질문 문자열. RunSucceeded와 함께 저장한 뒤 표시 |
| AnswerRecorded | session_id, qid, 사용자가 제출한 답변. 각 답변 제출 직후 다음 질문으로 이동하기 전에 저장. 모른다는 답변도 명시적으로 저장 |
| FrameProposed | session_id, proposal_id, run_id, 검증된 FrameProposal. 미리보기 전에 RunSucceeded와 함께 저장 |
| FramingCancelled / FramingResumed | session_id, reason. 취소는 draft를 보존하며 그래프를 생성하지 않음. `resume <session-id>`로 명시 재개 |
| FrameRejected | session_id, proposal_id, reason. 거부한 제안의 이력 보존. 같은 제안을 뒤늦게 승인할 수 없음 |
| FrameAccepted | session_id, proposal_id, 생성할 inquiry/hypothesis ID 매핑. InquiryCreated/HypothesisCreated와 함께 한 줄로 저장 |

상태는 draft=`active/cancelled/accepted`, 제안=`pending/rejected/accepted`로 구분한다. 가설의 D5 상태와 섞지 않는다. qid는 session 내 유일하며 이미 저장된 질문 재표시는 새 문항으로 세지 않는다. 질문 수는 고유 QuestionsIssued의 qid 수로 계산한다. 이미 제출된 qid에 다른 답변을 조용히 덮어쓰지 않는다.

재개는 미응답 qid부터 표시하고, 저장된 pending proposal이 있으면 모델 재호출 없이 미리보기를 복원한다. 거부 후에는 사용자가 재생성을 명시해야 새 run_id/proposal_id로 같은 Q&A에서 제안을 만든다. 새 질문은 누적 5개 한도 안에서만 가능하다. accepted session에 대한 같은 승인은 기존 ID를 반환하는 no-op이고 다른 proposal 승인은 거부한다.

전원 종료 시나리오: QuestionsIssued 저장 직후/표시 전에는 같은 질문만 표시; 답변 저장 직후에는 해당 답변을 다시 묻지 않음; FrameAccepted 저장 후/출력 전에는 기존 inquiry와 가설만 반환. 엔터를 누르지 않은 입력 문자는 복원 대상이 아니며 질문 자체는 남긴다.

- [x] 5종 fixture를 구조화된 프레임으로 처리하고 누락 필드·빈 후보·중복 ID를 거부한다.
- [x] 승인 전에는 그래프가 바뀌지 않는지, 거부/취소 시 가설이 생기지 않는지 검사한다.
- [x] 이미 답한 5문항으로 재개하면 질문 추가가 없는지 검사한다.
- [x] 중단·재시작 후 승인 중복 처리로 가설이 두 번 만들어지지 않는지 검사한다.
- [x] `python3 -m unittest discover -s tests -p 'test_framing_flow.py' -v` 실행.

2026-09-20 완료: [검증 결과](../../reports/m2-3-framing-eval.md). 질문 완료 판단도 `FramingControlRecorded`로 저장해, 완료 판단 직후 중단되면 질문 제어기를 다시 호출하지 않는다. 취소 Run과 세션 취소는 같은 이벤트다. 실제 공급자 연결과 모델 품질 검증은 이 단계 완료 범위가 아니다.

**완료 기준:** 모델 결과가 승인 후 실제 inquiry에 들어가고, 앱을 다시 실행해 같은 질문·가설을 볼 수 있다.

## 6. M2-4 — 실행 경계와 탐구 연산

실행 단위를 **M2-4A: BYOK 설정·OpenAI 어댑터·Framing CLI 연결**과 **M2-4B: 가설 탐구 5연산**으로 나눈다. 먼저 [M2-4A 상세 계획](2026-09-20-m2-4a-openai-framing.md)을 따른다. 아래 전체 M2-4 체크리스트는 두 단계를 합친 범위이며, M2-4A만 끝났다고 5연산까지 완료 처리하지 않는다.

2026-09-20: M2-4B의 첫 실행 단위 [Branch 계획](2026-09-20-m2-4b1-branch.md)을 구현·오프라인 검증했다([결과](../../reports/m2-4b1-branch-eval.md)). fork만 완료했으며 아래 5연산 전체 체크리스트는 아직 완료하지 않는다.

2026-09-21: 사용자가 Challenge를 새 가지가 아닌 검토 메모로 저장하도록 선택했다. 나머지 세 연산은 [상세 설계](../specs/2026-09-20-remaining-operations-design.md)와 [상세 구현 계획](2026-09-21-m2-4b-remaining-operations.md)을 따른다. Deepen과 Challenge는 저장·승인·CLI/chat 구현, 자동 검증, 최종 리뷰 APPROVE까지 완료했다. AI Synthesize는 미착수다.

### 배포·연결 전제 (ADR-D8)

[ADR-D8](../../decisions/ADR-D8-local-byok-distribution.md)에 따라 독립 로컬 CLI에서 사용자의 API 키로 공급자를 직접 호출한다. 운영자 로그인·중계·과금 서버나 Codex/Claude CLI 설치를 기본 경로에 추가하지 않는다. OpenAI는 첫 어댑터이며 다른 공급자·로컬 모델 지원은 후속 범위다.

- [ ] 모델·키 설정과 CLI 어댑터 주입 경로를 연결한다. 구현 전 프로젝트 범위 키 보관 위치·권한·설정 우선순위·Git 제외를 정하고, shell export 없이 사용할 수 있게 한다. 기존 키 파일을 덮어쓰거나 키 내용을 출력하지 않는다.
- [ ] 키 누락·잘못된 인증·공급자 오류는 비밀정보 없는 안내로 처리하고, 키가 이벤트·출력·오류 로그·export에 기록되지 않는지 가짜 비밀값으로 검사한다.
- [ ] 초기 설정/사용 안내에 직접 공급자 호출·사용자 부담 API 비용·전송되는 관련 문맥을 명시한다. 불필요한 프로젝트 파일은 자동 수집·전송하지 않는다.
- [ ] 키·네트워크 없이 저장·조회·복원·사람 승인과 기본 테스트가 동작하는지 회귀 검증한다. 실제 API smoke는 명시적 실행으로 구분한다.
- [ ] 설치·최초 설정·키 변경/제거 안내를 작성한다. 공개 배포 전 패키징·배포 채널·라이선스 점검은 별도 완료 조건으로 남긴다.

이 항목은 확정된 제품 방향의 구현 계획이며, 아직 키 설정 UX나 실제 OpenAI 연결이 완성됐다는 뜻은 아니다.

**파일:** `openai_adapter.py`, `commands.py`, `tests/test_adapter.py`, `tests/test_operations.py`. `adapter.py`/`runs.py` 계약은 M2-2A에서 이미 검증한 것을 사용한다.

M2-2A 계약에 OpenAI 어댑터를 연결하고, Framing의 질문/결과 생성 및 탐구 연산이 동일한 Run 기록·사용량·취소 경계를 사용하게 한다. 감지하지 못한 heartbeat를 생성하거나 가짜 퍼센트를 표시하지 않는다. 이 단계에서만 기존 SDK를 실제 호출하며 네트워크 없는 테스트와 API smoke 결과를 구분한다.

Run의 상태와 Hypothesis의 상태는 별개다. 모델 실행 성공이 가설 지지/반박 확정을 뜻하지 않는다. 네트워크 실패, 거절, 미완료 응답, 취소는 가설을 바꾸지 않고 Run 결과만 기록한다. 외부 API 호출 자체와 로컬 기록을 하나의 원자적 작업이라고 주장하지 않으며, 중단된 실행은 자동 재호출하지 않는다.

| 연산 | 저장되는 결과와 사람 경계 |
|---|---|
| fork | 부모 하나에서 2~4개 새 suggested 후보. 승인된 후보만 반영 |
| deepen | 원 가설을 삭제하지 않고 전제/검증 항목 보완 제안. 수정 승인 후 반영 |
| challenge | 반론 후보 생성. 반론 문장 자체를 외부 근거 또는 refuted 판정으로 저장하지 않음 |
| synthesize | 서로 다른 부모 2개 이상으로 새 suggested 가설 생성. D5에 따라 통합 가능한 부모를 synthesized로 바꾸는 것까지 한 변경 묶음으로 처리 |
| close | D5에서 허용된 상태의 지정 노드만 사람이 종료. 이유/스냅샷/재개 조건 필수. 자손 전체를 암묵적으로 종료하지 않음 |

새 통합 가설을 바로 탐색하려면 suggested→exploring에 대한 사람 명령이 필요하다. D5의 synthesized 상태를 단순히 ‘합류 지점’ 표시와 혼동하지 않는다.

D6에 따라 M2에도 실제 토큰 사용량과 inquiry 누적 사용을 표시한다. 가격 정보가 없으면 비용은 미확인으로 표시하고 임의 금액을 만들지 않는다. 자동 cap·다중 실행 차단 UI는 M3 범위다. M2는 한 번에 한 수동 실행과 요청별 토큰/시간 제한을 둔다.

- [ ] fake adapter로 5연산 제안→승인→재생, 승인 거부·잘못된 출력 시 원본 불변 검사.
- [ ] 합류 부모 중 하나가 없거나 전이 불가하면 새 가설/부모 상태 모두 미반영 검사.
- [ ] 부분 스트림 뒤 취소, 재시도 실패, 프로세스 중단 시 중복 가설/중복 사용량이 없는지 검사.
- [ ] 사람 전용 전이를 agent 실행 완료만으로 적용하지 않는지 검사.
- [ ] `python3 -m unittest discover -s tests -p 'test_adapter.py' -v`와 `test_operations.py` 실행. 실제 API smoke는 별도 명시 실행으로 기록한다.

**완료 기준:** 사용자가 호출한 한 연산이 명확한 실행 결과와 승인 가능한 변경으로 끝나고, 실패가 부분 그래프 변경을 남기지 않는다.

## 7. M2-5 — 조회·Actions·문서 출력

**파일:** `commands.py`, `projections.py`, `cli.py`, `tests/test_actions.py`, `tests/test_projections.py`.

- `show <id>`: 상태, claim, 부모, 연결 근거, 다음 Actions, 종료 이유를 읽기 전용으로 보여준다. 지도 클릭/키보드 선택 패널은 구현하지 않는다.
- Action: id, inquiry_id 또는 hypothesis_id, text, done. 생성/체크/해제는 이벤트이며 고아 참조는 거부한다. NOW/NEXT/LATER·기한·팀 담당 UI는 M3 이후다.
- Weekly: 지정 기간의 이벤트에서 결정·변경·남은 질문을 투영한다. 변경이 없으면 변경 없음이라고 쓴다. 모델이 성과를 발명하지 않는다.
- Markdown: inquiry, through_event, generated_at, draft 표식과 가설·근거 ID를 포함한다. 같은 로그/시점/시계 fixture에서는 같은 내용이 나온다.
- 기존 사용자 편집 파일은 자동 덮어쓰지 않는다. 새 출력 경로를 사용하거나 명시적 overwrite 승인 경로를 둔다. 외부 게시와 Markdown import는 없다.

- [ ] Action 체크 후 재시작 상태 유지, 잘못된 가설 ID 거부, 이미 완료된 Action의 중복 체크 처리 검사.
- [ ] Weekly에 실제 이벤트만 반영되는지, 종료 가설과 그 이유가 남는지, 문서가 원본 로그 없이도 읽히는지 검사.
- [ ] 출력 경로가 지정한 outputs 밖으로 벗어나지 않는지, 출력 실패가 이벤트 원본을 훼손하지 않는지 검사.
- [ ] `python3 -m unittest discover -s tests -p 'test_actions.py' -v`와 `test_projections.py` 실행.

**완료 기준:** 기본 상세·Actions·Weekly·export가 모두 같은 이벤트 시점의 상태를 보여준다.

## 8. M2-6 — 실제 상태를 터미널에 연결

2026-09-20 화면 흐름 결정: [ADR-D9](../../decisions/ADR-D9-conversation-before-map.md)에 따라 대화형 Framing → 승인 저장 → Git-log 전환으로 연결한다. [상세 설계](../specs/2026-09-20-conversation-gitlog-design.md)의 대화형 `chat`은 구현·오프라인 검증했으며 승인 후에는 아직 텍스트 요약이다. Gate B 전 TUI 통합 금지는 유지한다. 미구현 탐구 연산/Actions/문서 출력까지 완료한 것으로 취급하지 않는다.

**파일:** `projections.py`, `cli.py`, `tui.py`, `tests/test_ui_projection.py`, `tests/test_cli.py`.

M2-0B/Gate B가 해소된 후 그 단계에서 선정한 라이브러리를 사용한다. 화면은 State의 투영과 Run 상태만 읽으며, 명령은 Commands→Store를 거쳐 적용한다. 화면에서 객체를 직접 변경하지 않는다.

- 위→아래 계보, 옆 분기, 두 부모 합류, 종료 가지 보존이라는 선택안을 따른다. UI 용어는 영어, 사용자 내용은 원문 언어를 유지한다.
- fixture 묶음 대신 실제 State의 부모 연결을 사용한다. 현재 목업의 페이지 수·최대 세 가지 lane을 제품 규칙으로 고정하지 않는다. 표현 한도를 넘으면 숨긴 수와 경계 ID를 명시하고 기본 조회로 접근하게 한다.
- 명령 입력 중에도 현재 그래프와 실행 상태가 남아 있어야 한다(§18-8). 상태 갱신은 실제 실행 이벤트에 근거한다.
- 비용은 실측 토큰/알 수 있는 추정치만, 긴 출력은 화면 경계를 넘어 지도를 밀어내지 않게 처리한다.
- 클릭/방향키 노드 탐색은 후순위다. `show <id>`와 명령 입력으로 기본 정보 조회를 제공한다.

- [ ] 실제 replay state와 표시 ID·부모·상태 일치, 합류 부모 누락 없음, 숨긴 노드 ID에 기본 조회 접근 가능 여부 검사.
- [ ] 80/120/160열 × 10/30/100개, 긴 한글 claim과 빈 그래프, 종료 가설이 많은 경우 검사.
- [ ] 실행 취소·터미널 resize·종료 시 화면과 입력 상태 복구를 실제 터미널에서 확인한다.
- [ ] `python3 -m unittest discover -s tests -p 'test_ui_projection.py' -v`와 `test_cli.py` 실행.

**완료 기준:** 가짜 그래프가 아닌 저장된 탐구가 지속형 화면에 표시되고, 기본 명령 후 상태가 일관되게 갱신된다.

## 9. M2-7 — 최종 수용 시나리오

**파일:** `tests/test_journey.py`, `tests/fixtures/`, `docs/reports/m2-exit.md`.

| PRODUCT-CONCEPT §18 | 검증할 관찰 결과 | 담당 작업 |
|---|---|---|
| 1 입력 | 한 문단 seed로 inquiry 흐름 시작 | M2-3 |
| 2 프레이밍 | 누적 3~5문항, 중심 질문·범위 유지 | M2-3 |
| 3 초기 가설 | 성격이 다른 후보를 suggested로 제시 | M2-3 |
| 4 탐색 | 사람이 ID를 지정해 단일 실행 시작 | M2-4 |
| 5 분기·근거 | 새 가설과 실제 근거/반례의 참조 보존 | M2-2/4 |
| 6 종료·통합 | 이유 있는 종료, 두 부모 합류, 기존 가설 이력 유지 | M2-4 |
| 7 Actions | 가설에 연결된 항목 생성·체크·재시작 복원 | M2-5 |
| 8 지속 화면 | 명령 중 그래프·작업 상태 동시 표시 | M2-6 |
| 9 Weekly | 실제 변경·결정으로 Markdown 생성 | M2-5 |
| 10 재사용 | 앱 없이 문서 읽기, 출처·기준 event 확인 | M2-5 |

- [ ] 임시 디렉터리와 fake adapter로 전체 여정을 자동 실행한다. 서로 다른 프로세스에서 중간에 재시작해도 같은 상태인지 확인한다.
- [ ] 네트워크 없는 `python3 -m unittest discover -s tests -v`가 통과한다.
- [ ] 실제 API와 실제 터미널로 수동 여정 1회를 실행하고 사용량·실패/취소·출력 위치를 기록한다. 자동 fixture 결과와 구분한다.
- [ ] 열린 오류와 미검증 항목을 m2-exit.md에 기록한다. 필수 시나리오를 끝내지 못했다면 M2를 완료로 표시하지 않는다.

## 10. 계획 자체 점검

- 기존 D1~D6를 임의로 다시 결정하지 않았는가: 저장·DAG·상태·독립 근거·단일 실행·누적 표시로 반영했다.
- M2 범위를 놓쳤는가: 기본 조회, Actions, Weekly, export, 지속 화면과 §18 1~10을 매핑했다.
- 과도한 구현을 넣었는가: DB/팀/자동 채점/의미 중복/마우스 상세/임의 외부 도구 실행은 제외했다.
- 정적 프로토타입을 제품처럼 취급했는가: 실제 State projection과 TUI 선정은 별도 작업으로 명시했다.
- 불확실성을 숨겼는가: M1a/M1b UX와 D5에서 허용되지 않은 전이, TUI 선택을 M2-0에 드러냈다.

M2-4B-3 Challenge 검토 메모와 대화형 연결까지 구현·오프라인 검증·최종 리뷰를 마쳤다([결과](../../reports/m2-4b3-challenge-eval.md)). 다음 기능은 AI Synthesize다. Gate B 사람 사용성 검증은 병행한다. 사용자의 chat 실행 완료 보고를 모든 모델 품질 검증으로 확대하지 않는다. TUI 통합은 Gate B 이후이며 현재 변경은 커밋·푸시하지 않았다.
