# ADR-D10 — 다중 에이전트 actor (역할 에이전트)

- 상태: **Accepted** (M3 구현과 함께 확정)
- 작성일: 2026-10-12
- 관련: PRODUCT-CONCEPT §5·§11 · MILESTONES §M3("다중 에이전트 actor") · 의존: D4(agent-adapter)·D5(state-machine) · 구현 계획: [m3-multi-actor](../superpowers/plans/2026-10-12-m3-multi-actor.md)

## 맥락

PRODUCT-CONCEPT §5·§11은 "사람과 여러 AI 에이전트가 함께 일하는 팀"과 Explorer·Researcher·Critic·Simulator·Synthesizer·Reviewer 역할을 그린다. 그러나 M2까지 런타임은 모든 agent 실행을 단일 `agent:runner`로 기록했고(역할·정체성 구분 없음), 제안이 "누가 제안했나"를 드러내지 못했다. MILESTONES §M3는 "다중 에이전트 actor"를 범위로 두되, M4 Team Mode("2명 이상 + 다중 에이전트 동시 탐구")와 구분된다.

## 결정

**단일 사용자(solo) 내 역할 에이전트를 정체성+persona로 도입한다. 동시 실행은 아니다.**

- **역할 = persona 오버레이.** 역할은 operation에 1:1 매핑하지 않는다. 고정 프로필 레지스트리(`features/agents/profiles.py`)가 `name → {persona, model?}`를 정의하고, 선택된 에이전트가 operation을 자기 관점으로 수행한다. operation이 출력 구조(output_schema)를 결정, 역할이 관점+정체성+(선택)모델을 결정. persona는 operation 시스템 프롬프트 앞에 결합한다.
- **actor 정체성.** run과 그 제안은 `agent:<name>`로 기록된다. `Runner.execute(actor=...)`가 run의 모든 이벤트를 동일 actor로 emit한다. `Run` 모델에 `actor` 필드를 두어 RunStarted에서 확정하고, replay가 **비-recovery 이벤트는 run.actor 일치를 강제**한다(run 생애 일관성). `system:recovery`는 예외.
- **생산자 검증 느슨화(3곳).** `replay.py`·`operation/state.py`·`branch/state.py`의 `== 'agent:runner'`를 유효 `agent:<name>`로 완화. **framing은 `agent:runner` 고정**(역할 미도입, inquiry 전 설정 단계).
- **기본 에이전트 `runner`.** persona 없는 generalist. `--agent` 미지정 시 기존 동작과 동일(backward compat). 기존 `agent:runner` 로그는 계속 유효.
- **동시 실행 없음.** `started` run 1개 제한 유지(solo). 여러 사람·에이전트 실시간 협업은 M4.
- **provenance.** branch/operation 제안 view가 수행 agent를 노출(`proposal→run_id→run.actor`). CLI `--agent <name>`로 역할 선택.
- **사람/에이전트 권한 경계 불변.** `transitions.py`의 role(human/agent) 검사와 사람 전용 결정(human: 액터)은 그대로 — 역할 에이전트도 agent 전이 권한(`_AGENT_EDGES`) 내에서만 제안.

## 근거 (provenance)

- PRODUCT-CONCEPT §5·§11의 역할 팀 비전의 직접 구현(외부 정본).
- "누가 제안했나"의 가시성은 §20(충돌·대안 보존) 철학과 정합 — 역할별 관점을 그래프에 남긴다.
- solo 전제(MILESTONES §13)에서 동시 실행은 불필요 → 범위를 정체성+persona로 한정.

## 결과 · 트레이드오프

- 다중 역할은 제안량을 늘려 그래프 슬롭 위험↑ → saturation/dedup(§8, M3 다음 항목) 수요를 당긴다.
- persona는 프롬프트 앞 결합일 뿐 output_schema/validate 계약을 바꾸지 않는다(낮은 결합).
- 역할 세트가 코드 고정이라 사용자 정의 역할은 후속.

## 대안 (기각)

- **attribution만(정체성/귀속만, persona 없음):** 너무 얇아 역할의 실제 효용(관점 차별화)이 없음.
- **책임 분리 3역(accountable/executor/reviewer, §11):** 무겁고 M4 Team Mode와 중복 → 후속.
- **역할↔operation 1:1 매핑:** operation 집합에 역할을 가둬 유연성↓ → persona 오버레이로 대체.

## 열린 질문

- **사용자 정의 역할**(config/.env/이벤트 기반) — M3는 코드 고정 세트. (M_ 후속)
- **assess 노드 provenance**(어느 agent가 가설을 채점했나) — AxisScore/Assessment에 performed_by 필요, D3 스키마 재수정 수반. (후속)
- **역할별 기본 모델** — 현재 프로필 model은 비워둠(전역 설정 사용). 역할에 특화 모델을 둘지 실측 후. (M_ 후속)
- **역할↔operation 추천** — 어느 역할이 어느 operation에 적합한지 안내/추천. (후속)
- **동시 실행·실시간 협업** — M4 Team Mode.
