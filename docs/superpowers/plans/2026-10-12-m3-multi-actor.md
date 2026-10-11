# M3 Multi-Actor (Role Agents) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` for sequential implementation, or `subagent-driven-development` for bounded delegated work. Apply `test-driven-development` and `verification-before-completion` for each task. 체크박스는 검증 후에만 완료로 바꾼다.

**Goal:** M3의 "다중 에이전트 actor"(MILESTONES §M3)를 **역할 에이전트(정체성+프롬프트)**로 구현한다. 고정 역할 세트(Explorer/Skeptic/Researcher/Synthesizer 등, PRODUCT-CONCEPT §11)를 named agent로 두고, 각 역할이 **전용 persona 프롬프트 + (선택) 모델**로 operation을 수행하며, run/제안이 `agent:<role>`로 **귀속·기록·표시**된다. **동시 실행 아님**(solo, `started` run 1개 제한 유지) — 동시 다중 사용자 협업은 M4 Team Mode(후순위).

**Architecture:** 역할은 operation 위에 얹히는 **persona 오버레이**다(역할 = "누가/어떤 관점", operation = "무엇을"). 에이전트 프로필 레지스트리(name→{persona, model?})를 코드에 두고, 서비스가 선택된 프로필의 persona를 operation 시스템 프롬프트에 결합하고 프로필 모델을 쓰며 `actor=agent:<name>`로 Runner에 넘긴다. 기존 `agent:runner` 단일 하드코딩 검증(5곳)을 "유효한 `agent:<name>`"로 느슨하게 풀되 **기존 로그 호환**을 지킨다. 이벤트 소싱/Runner/operation 경로는 그대로 재사용.

**Tech Stack:** Python 3.9+, 표준 라이브러리 unittest, 기존 `.venv`. 새 의존성 없음.

**Status:** 2026-10-12 계획 수립 → critic 1회차 CHANGES NEEDED → B1·W1·W2·G1 반영해 개정(Run.actor 추가로 일관성+provenance 동시 해결) → **Task 1~6 구현·검증 완료(2026-10-12).** 신규 18 테스트, 전체 121 그린.

**선행 결정 (사용자 확정 2026-10-12):**
- **스코프: 역할 에이전트(정체성+프롬프트).** attribution만(축소)도, 책임분리 3역(확대)도 아님.
- **역할 = persona 오버레이**(Framing X): 역할은 operation에 1:1 매핑되지 않고, 선택된 에이전트가 operation을 자기 관점으로 수행. operation이 출력 구조(schema)를 결정, 역할이 관점+정체성+(선택)모델을 결정.
- **동시 실행 없음**: `started` run 1개 제한 유지(solo).
- **기본 에이전트 = `runner`(generalist, persona 없음).** `--agent` 미지정 시 기존 동작과 동일(backward compat). 역할은 opt-in.
- **(critic B1·W1) `Run` 모델에 `actor` 필드 추가.** RunStarted에서 확정, 비-recovery 이벤트는 `run.actor` 일치 강제. 이 한 변경이 (1) run 생애 actor 일관성 강제와 (2) provenance 조회(proposal→run_id→`run.actor`)를 동시에 해결.
- **(critic G1) framing은 `agent:runner` 고정.** 느슨화는 **3곳만**(`replay.py:24`·`operation/state.py:59`·`branch/state.py:46`). `framing/state.py:46`은 느슨화하지 않아 framing 내용 생산자 보호 유지("framing 역할 미도입"과 일치).
- **(critic W2) assess 노드 provenance 제외(후속).** provenance는 branch/operation 제안만. assess의 "어느 agent가 채점했나"는 D3 스키마 재수정이 필요해 이번 범위 밖(run 단위 actor는 보임).

## Global Constraints

- 정본: [MILESTONES §M3](../../MILESTONES.md), [PRODUCT-CONCEPT §5·§11](../../PRODUCT-CONCEPT.md), [ADR-D4(agent-adapter)](../../decisions/ADR-D4-agent-adapter.md), [ADR-D5(state-machine)](../../decisions/ADR-D5-state-machine.md).
- **적용 범위:** 역할은 **branch(fork)·explore(deepen/challenge/synthesize)·assess(score/reassess)** run에 적용. **framing은 기본 에이전트 유지**(inquiry 전 설정 단계, cancel 자동화 로직 보존) — framing에 역할 미도입.
- **actor 느슨화(3곳):** `operation/state.py:59`·`branch/state.py:46`·`replay.py:24`의 `== 'agent:runner'`를 "유효한 `agent:<name>`(role=='agent', 이름 비어있지 않음)"로. **`framing/state.py:46`은 느슨화하지 않음**(agent:runner 고정 — framing 역할 미도입). `system:recovery` 특례(`replay.py:23`)·framing cancel(`framing/state.py:91,95`)은 보존. **기존 `agent:runner` 로그는 계속 유효**.
- **run 생애 actor 일관성(강제):** `Run`에 `actor` 필드 추가 → RunStarted에서 확정. `_apply_run`에서 비-RunStarted·비-`system:recovery` 이벤트는 `event['actor'] == run.actor`를 **강제**(recovery만 예외). "Runner 구성상 성립"에 의존하지 않고 replay가 임의 로그에도 강제한다. framing run은 actor=agent:runner이므로 느슨화된 `replay.py:24`를 통과하고 framing 내용은 `framing/state.py:46`이 재검사해 보호.
- **provenance 조회:** 제안의 수행 agent = `proposal['run_id']` → `state.runs[run_id].actor`. Run.actor 추가로 자명해짐. assess 노드(Hypothesis.assessment)의 채점 agent는 이번 범위 밖.
- **transitions.py 무변경:** role(human/agent)만 검사하므로 `agent:<name>` 흡수됨(확인됨). agent 전이 권한(`_AGENT_EDGES`)은 역할 무관하게 동일.
- **provenance:** 제안/노드가 "누가 제안했나"를 드러내야 한다(§11). 최소 `show`·proposal view(JSON)에 수행 agent 노출. graphlog/tui 표시는 thin/후순위.
- **persona 결합:** `system = persona_preamble + operation_system`(operation 프롬프트는 보존, 앞에 역할 관점 preamble). output_schema는 operation 그대로.
- **모델 선택:** 프로필에 model이 있으면 그 모델로, 없으면 기존 전역 설정. openai_adapter는 model을 문자열로 받으므로 영향 적음.
- **레지스트리 위치:** 코드 내 고정 기본 세트(M3). config/.env/이벤트 기반 사용자 정의 역할은 **범위 밖**(후속).
- `.env`·실제 `.inquiry`·사용자 환경 미수정. 테스트는 합성 데이터+TemporaryDirectory. 실제 API·커밋·푸시는 별도 요청 전 금지.
- `schema_version=1` 호환. 구버전 프로그램이 새 동작을 거부하는 기존 보장 유지. 역할 미지정 로그 = 기존 동작.
- 구현 순서 Task 1→2→3→4→5→6. 각 단계 통과 전 다음으로 확장 금지.

## 파일과 책임

| 파일 | 책임 |
|---|---|
| 새 `features/agents/profiles.py` | `AGENT_PROFILES`(name→{persona, model?}) 기본 세트 + `runner` generalist. `resolve(name)`·`actor_for(name)`. 순수 데이터/조회 |
| 수정 `domain/model.py` | `Run.actor: str` 필드 추가(기본 `'agent:runner'`, 맨 뒤) |
| 수정 `llm/runs.py` | `execute(actor=...)` 파라미터(기본 `agent:runner`) → 그 run의 모든 이벤트를 해당 actor로 `_record`. recovery/`system:recovery` 보존 |
| 수정 `domain/replay.py` | `_apply_run`: `agent:runner` 검증을 유효 `agent:<name>`로 느슨화(24행) + RunStarted에서 `Run.actor` 확정 + 비-recovery 이벤트 `event['actor']==run.actor` 강제 |
| 수정 `features/operation/state.py`·`branch/state.py` | 생산자 검증 `== 'agent:runner'` → 유효 `agent:<name>`. **`framing/state.py`는 변경 없음**(agent:runner 고정) |
| 수정 `features/{branch,operation,assessment}/service.py` | 선택 프로필의 persona를 operation 프롬프트에 결합 + 프로필 model 사용 + `actor` 전달 |
| 수정 `ui/cli.py` | branch/explore/assess run 명령에 `--agent <name>`. 기본 `runner`. `show`에 수행 agent 노출 |
| 수정 `ui/graphlog.py`·`ui/tui.py` | (thin, 후순위) 노드/활동에 수행 agent 표시 |

## Tasks

### Task 1 — 에이전트 프로필 레지스트리
- `features/agents/profiles.py`: `AGENT_PROFILES` 기본 세트(`runner` generalist[persona 없음] + explorer/skeptic/researcher/synthesizer 등 §11 기반) + `resolve(name)`(미지 이름 거부) + `actor_for(name)`(`agent:<name>`).
- **수용 기준:** 기본 프로필 조회·persona/model 접근. 미지 이름 거부. `runner`는 persona 없음(기존 동작 동일). 순수 함수 테스트.

### Task 2 — Run.actor 필드 + actor 플러밍 + 검증 느슨화 (backward compat)
- `domain/model.py`: `Run.actor: str = 'agent:runner'`(맨 뒤).
- `llm/runs.py`: `execute(..., actor='agent:runner')`; 그 run의 모든 이벤트를 해당 actor로 기록.
- `domain/replay.py`: `_apply_run`에서 RunStarted 시 `Run.actor=event['actor']` 확정; 비-RunStarted·비-`system:recovery` 이벤트는 `event['actor']==run.actor` 강제. 생산자 느슨화는 `replay.py:24`·`operation/state.py:59`·`branch/state.py:46` **3곳만**(framing:46 고정).
- **수용 기준:** 구버전(`agent:runner`) 로그 그대로 replay(무회귀, 기존 RunStarted엔 actor 없음→envelope actor로 채움). `agent:explorer` run 시작→성공→replay 시 `run.actor=='agent:explorer'`, 제안 귀속. **run 생애 중 actor 불일치(agent:explorer 시작 후 agent:skeptic 성공) 거부**. `system:recovery`로 끝나는 run은 허용(혼입 예외). 비-agent actor의 run 이벤트 거부. framing run(agent:runner)·cancel 자동화 무회귀.

### Task 3 — persona + model 주입 (서비스)
- `features/{branch,operation,assessment}/service.py`: 프로필 인자(또는 agent name) 수용 → `system = persona + operation_system`, 프로필 model 사용(없으면 기존), `actor=agent:<name>`로 execute.
- **수용 기준:** 합성 어댑터로 explorer/skeptic 프로필 run이 각자 actor로 제안 기록. persona가 system에 결합됨(캡처로 확인). 프로필 model override 동작. 기본 `runner`는 persona 없이 기존과 동일.

### Task 4 — CLI `--agent`
- `ui/cli.py`: branch/explore/assess run 명령에 `--agent <name>`(기본 `runner`). 미지 이름은 명확한 에러. `--agent`가 프로필을 서비스로 전달.
- **수용 기준:** `--agent explorer`로 run 시 agent:explorer 귀속. 미지정 시 runner(기존 동작). 미지 이름 거부. 키 없이(합성 어댑터) 검증.

### Task 5 — provenance 표시 (제안 단위)
- `ui/cli.py` `show`·proposal view(`branch/service._view`, `operation/service._view`)에 수행 agent 노출 — `proposal['run_id']`→`state.runs[run_id].actor`. (thin) graphlog/tui에 수행 agent 표시.
- **수용 기준:** branch/operation 제안 출력에 수행 agent 포함, 역할별 제안 구분. assess 노드 채점 agent는 범위 밖(제외 명시).

### Task 6 — ADR/문서
- 다중 actor(역할=persona 오버레이, 동시실행 제외, backward compat) 결정을 ADR로 기록(신규 또는 D5 확장). MILESTONES M3 진행 반영.
- **수용 기준:** 문서가 코드 동작과 정합. M3 vs M4 경계 명시.

## 범위 밖 (후속)
- **동시 실행/실시간 협업**(여러 사람·에이전트 동시) — M4 Team Mode.
- **사용자 정의 역할**(config/.env/이벤트 기반) — M3는 코드 고정 세트.
- **책임 분리 3역**(accountable/executor/reviewer, §11) — M4와 중복, 후속.
- graphlog/tui의 풍부한 활동 표시(heartbeat 애니메이션 등) — 표현계층.
- 역할↔operation 자동 매핑/추천(어느 역할이 어느 operation을 해야 하는지) — 후속.
- **assess 노드 provenance**(어느 agent가 가설을 채점했나) — AxisScore/Assessment에 performed_by 추가 필요, D3 스키마 재수정 수반 → 후속.
- **framing 역할** — framing은 agent:runner 고정, 역할 미도입.
