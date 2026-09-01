# Inquiry Workspace 제품 콘셉트 및 개발 전 기획서

> Working title: **Inquiry**  
> 문서 상태: **Concept / Pre-development**  
> 작성일: 2026-08-18  
> 구현 상태: **아직 개발되지 않음**

## 1. 문서 목적

이 문서는 사람과 AI 에이전트가 함께 질문을 구체화하고, 여러 가설을 분기해 탐색하며, 근거·실험·사고실험·의사결정·할 일을 연결하고, 그 과정을 재사용 가능한 Markdown 산출물로 남기는 오픈소스 도구의 개발 전 기준 문서다.

현재까지 확정된 것은 제품 방향과 핵심 경험이며, 기술 스택·저장 형식·프로젝트 이름 등은 아직 최종 결정되지 않았다.

## 2. 한 문장 정의

> 생각을 분기하고, 가설을 검증하고, 아이디어가 살아남거나 사라진 이유를 기록하며, 그 과정을 팀의 지식 자산으로 만드는 터미널 기반 공동 탐구 환경.

영문 표현 후보:

> A shared workspace for branching thoughts, testing hypotheses, and preserving why ideas lived or died.

## 3. 배경과 문제

현재의 주요 도구는 서로 다른 단위를 관리한다.

| 도구 종류 | 주로 관리하는 것 |
|---|---|
| 채팅형 AI | 한 대화 안의 질문과 답변 |
| Git | 코드 변경과 코드 브랜치 |
| 이슈 트래커 | 이미 정해진 작업과 담당자 |
| 문서 도구 | 정리된 결과물 |
| 에이전트 하네스 | 에이전트 실행과 검증 |

그러나 연구·기획·전략·창작 과정에서는 다음이 충분히 관리되지 않는다.

- 처음에는 질문 자체가 불명확하다.
- 하나의 질문에서 서로 다른 가설과 해석이 생긴다.
- 코드 없이 조사, 토론, 반례 탐색, 시뮬레이션 또는 사고실험만 수행할 수도 있다.
- 어떤 가설을 왜 채택·보류·기각했는지 시간이 지나면 사라진다.
- 여러 사람과 에이전트가 무엇을 탐색 중인지 한눈에 보기 어렵다.
- 작업 과정은 채팅에 남지만 위클리, 연구 노트, 블로그 등으로 재사용하기 어렵다.

Inquiry는 완성된 답보다 **질문과 가설이 진화하는 과정**을 관리한다.

## 4. 제품 철학

### 4.1 기본 단위는 태스크가 아니라 가설이다

태스크는 가설을 검증하기 위해 수행하는 다음 행동이다. 제품의 중심 객체는 `Issue`나 `Ticket`이 아니라 `Hypothesis`다.

### 4.2 불확실성을 억지로 제거하지 않는다

사용자가 모르는 부분은 필수 입력값으로 강제하지 않는다. 여러 해석이나 조건부 가설로 분기해 탐구 가능한 형태로 바꾼다.

### 4.3 에이전트의 확신을 진실처럼 표현하지 않는다

확률과 confidence는 출처·근거 강도·불확실성 범위와 함께 표시한다. 측정할 수 없는 작업에는 가짜 진행률을 부여하지 않는다.

### 4.4 사람이 최종적인 탐구 경계를 가진다

에이전트는 가설을 만들고 탐색할 수 있지만, 사람이 설정한 비용·시간·윤리·범위·승인 경계를 넘지 않는다. 사람의 종료와 채택 결정은 명시적으로 기록한다.

### 4.5 실패한 아이디어도 지식이다

기각된 가설은 삭제하지 않는다. 종료 이유, 당시 근거, 재개 조건을 보존한다.

### 4.6 그래프는 살아 있는 원본이고 문서는 목적별 산출물이다

탐구 상태는 계속 변하지만, 필요한 시점에 위클리·연구 노트·의사결정 기록·블로그 등으로 투영할 수 있어야 한다.

### 4.7 로컬 우선, 개방형 포맷을 지향한다

핵심 기록과 산출물은 특정 SaaS에 잠기지 않아야 한다. 원본(canonical)은 개방형 이벤트 로그(append-only JSONL)이며, 엔티티 Markdown과 산출물은 언제든 이 로그에서 재생성 가능한 export다. Markdown, YAML, JSONL 등 사람이 읽고 다른 도구에서 재사용 가능한 형식을 우선한다. (저장 형식 결정은 [ADR-D1](./decisions/ADR-D1-storage-format.md) 참조)

## 5. 주요 사용자와 사용 사례

### 주요 사용자

- 연구자와 리서치 팀
- 창업자와 초기 제품 팀
- 사람과 여러 AI 에이전트가 함께 일하는 팀

### 대표 사용 사례

- 막연한 아이디어를 구체적인 탐구 질문으로 발전시킨다.
- 하나의 문제에 대해 상반된 가설을 병렬로 탐색한다.
- 여러 에이전트에게 탐색·비판·시뮬레이션·종합 역할을 할당한다.
- 팀원이 현재 어떤 브랜치에서 일하는지 확인한다.
- 탐구 결과를 Markdown 연구 노트나 공개 블로그 초안으로 만든다.

## 6. 핵심 개념 모델

### 6.1 처음 배우는 세 가지 객체

사용자에게 처음부터 많은 Node 유형을 노출하지 않는다. 기본 모델은 다음 세 가지뿐이다.

| 사용자 표현 | 내부 표현 | 설명 |
|---|---|---|
| `Question / Goal` | `Inquiry` | 무엇을 알고 싶거나 이루고 싶은가 |
| `Idea / Possibility` | `Hypothesis` | 가능할 수 있는 답, 설명 또는 방향 |
| `Check / Finding` | `Evidence` | 아이디어를 더 믿거나 의심하게 만든 확인 결과 |

```text
Question  →  Possibility  ←  Finding
 질문/목표      가능성          확인 결과
```

`Check`는 자료 조사, 논리적 반박, 사고실험, 시뮬레이션, 인터뷰, 실제 실험, 프로토타입 등 여러 검증 방법을 포괄한다. 사용자는 이들을 각각 다른 Node 유형으로 배울 필요가 없다.

### 6.2 처음 배우는 세 가지 관계

| 관계 | 의미 |
|---|---|
| `branches-from` | 이 가능성이 어떤 질문 또는 가설에서 나왔는가 |
| `supports` | 이 Finding이 가능성을 강화하는가 |
| `challenges` | 이 Finding이 가능성을 약화하거나 반박하는가 |

고급 관계인 `refines`, `depends-on`, `synthesizes`, `supersedes`는 시스템이 문맥으로 추론하거나 사용자가 고급 기능을 열었을 때만 표시한다.

실제 사고는 분기 후 재결합되므로 내부 구조는 단순 트리가 아니라 DAG(방향성 비순환 그래프)를 기본으로 하는 Inquiry Graph가 적합하다. 분기 후 재결합은 다부모 노드로 표현한다. **MVP(M2~M3)는 DAG-only로 확정하며, 제한적 순환은 M5 이후 재검토한다** ([ADR-D2](./decisions/ADR-D2-graph-model.md) 참조).

### 6.3 확장 개념은 기본 객체에 흡수한다

| 확장 개념 | 기본 모델에서의 표현 |
|---|---|
| Assumption | Hypothesis의 필드 또는 하위 Possibility |
| Experiment | Check의 실행 방법 |
| Simulation | Check의 실행 방법 |
| Thought experiment | Check의 실행 방법 |
| Decision | Hypothesis 상태를 변경한 이벤트 |
| Action | Question 또는 Hypothesis에 붙는 체크리스트 |
| Output | 그래프에서 생성되는 문서 |
| Synthesis | 여러 부모를 가진 새로운 Hypothesis |

### 6.4 가설의 기본 구조

```yaml
id: H-001
type: hypothesis
title: "멀티모달 Agent 실행을 재현·비교하는 오픈소스 디버거는 실제 수요가 있다"
claim: >
  화면, 음성, 이미지와 도구 호출이 섞인 Agent 실행을 하나의 타임라인에서
  재현하고 비교할 수 있다면 개발자가 실패 원인을 찾는 시간이 줄어든다.

assumptions:
  - "멀티모달 Agent 팀이 실행 재현과 디버깅에 반복적인 어려움을 겪는다"
  - "서로 다른 모델과 프레임워크의 실행 기록을 공통 형식으로 변환할 수 있다"

falsified_if:
  - "개발자가 기존 tracing 도구만으로 문제를 충분히 해결한다"
  - "프로토타입 사용자가 한 번 체험한 뒤 반복해서 사용하지 않는다"

assessment:
  plausibility: 0.72
  evidence_strength: 0.30
  novelty: 0.65
  impact: 0.80
  testability: 0.55
  source: agent-estimate
  range: [0.50, 0.80]

status: exploring
accountable: chanran
executor: agent:research-2
reviewer: minji
```

### 6.5 상태 모델

> 아래 다이어그램은 개념 개관이다. **허용 전이표·불변식을 포함한 정식 상태 머신은 [ADR-D5](./decisions/ADR-D5-state-machine.md)를 정본으로 한다** (충돌 시 D5 우선).

```text
suggested → exploring → supported ─┐
                  │               ├→ synthesized
                  ├→ contested ───┤
                  ├→ suspended    ├→ human-closed
                  └→ refuted ─────┘
```

추천 상태:

- `suggested`: 에이전트가 제안했지만 아직 활성화되지 않음
- `exploring`: 사람 또는 에이전트가 탐색 중
- `supported`: 현재 근거상 지지됨
- `contested`: 의미 있는 상반된 근거가 있음
- `suspended`: 판단을 보류함
- `refuted`: 현재 근거상 반박됨
- `synthesized`: 다른 가설에 통합됨
- `human-closed`: 사람이 명시적으로 종료함

## 7. 첫 시작: Framing Session

사용자에게 완성된 질문이나 가설을 요구하지 않는다. 사용자는 막연한 생각을 입력하고, 에이전트는 3~5회의 적응형 질의응답으로 최소한의 탐구 프레임을 만든다.

```bash
inquiry new
```

```text
완성된 질문일 필요가 없습니다. 지금 떠오르는 생각을 적어주세요.

❯ 이번에 Agent 관련 오픈소스 프로젝트를 새롭게 만들어보고 싶은데,
  멀티모달과 관련해 무엇을 새롭게 만들 수 있을지 모르겠어.
  사람들이 실제로 반복해서 사용할 만한 것이면 좋겠어.
```

### 기본 세 가지 Framing 질문

1. 무엇을 알고 싶거나 바꾸고 싶은가?
2. 이 탐구 결과를 실제로 어떤 결정이나 산출물에 사용할 것인가?
3. 무엇을 확인하면 `사람들이 실제로 사용할 만하다`고 판단할 수 있는가?

현재 믿음, 반증 조건, 시간·비용·대상 범위는 답변에 꼭 필요할 때만 후속 질문으로 묻는다. 기본 세 문항으로 충분하면 더 이상 질문하지 않는다.

### 기본 세 가지 Framing 모드

| 모드 | 목적 |
|---|---|
| `explore` | 새로운 가능성을 넓게 찾고 더 깊이 이해한다 |
| `decide` | 여러 가능성을 비교해 선택을 돕는다 |
| `test` | 특정 가능성이 실제로 성립하는지 확인한다 |

`create`, `forecast`, `thought-experiment`는 별도 기본 모드가 아니라 `explore` 또는 `test` 안에서 선택하는 방법으로 제공한다. 사용자가 모드를 고르지 않아도 첫 입력을 바탕으로 하나를 추천한다.

### Framing 결과

- 중심 질문
- 탐구 목적
- 사용 맥락 또는 결정 대상
- 현재 믿음
- 판단 기준
- 탐구 범위와 비범위
- 아직 열린 질문
- 초기 가설 후보

에이전트가 생성한 초기 가설은 회색 `suggested` 상태로 표시하고, 사용자가 승인하거나 탐색을 시작할 때 활성화한다.

## 8. 탐구 연산

처음에는 세 가지 행동만 안내한다.

| 기본 행동 | 내부 연산 | 설명 |
|---|---|
| `Branch` | `fork` | 새로운 가능성을 만든다 |
| `Check` | `deepen`, `research`, `challenge`, `simulate`, `experiment` | 조사·반박·사고실험·시뮬레이션 등으로 가능성을 확인한다 |
| `Decide` | `continue`, `suspend`, `support`, `close` | 계속 탐색하거나 보류·지지·종료한다 |

```text
[f] Branch     새로운 가능성 만들기
[c] Check      조사·반박·실험·사고하기
[d] Decide     계속·보류·지지·종료
```

`Check`를 선택한 뒤에만 세부 방법을 보여준다.

```text
어떻게 확인할까요?

  Research        자료와 사용 사례 조사
  Challenge       가장 강한 반론 탐색
  Think           논리와 전제를 깊게 검토
  Simulate        조건별 결과 시뮬레이션
  Experiment      사용자 검증 또는 프로토타입 실행

  [Enter] 추천 방법 사용
```

### 확장 연산

| 연산 | 설명 |
|---|---|
| `compare` | 여러 가설을 동일한 기준으로 비교한다 |
| `synthesize` | 여러 브랜치를 새로운 가설로 통합한다 |
| `reframe` | 탐구 결과를 바탕으로 중심 질문을 재구성한다 |
| `reopen` | 새로운 조건이나 근거로 종료된 가설을 다시 탐색한다 |

확장 연산은 처음부터 메뉴에 모두 노출하지 않는다. 유사한 가설, 상반된 Finding 또는 질문 범위의 변화가 감지될 때 문맥에 맞춰 제안한다.

### 사고 포화 감지

무한 탐색이 반복적인 문장 생성으로 변하지 않도록 다음을 관찰한다.

- 새 가설·전제·근거의 생성 여부
- 기존 노드와의 의미 중복도
- confidence 변화
- 새로운 연결 또는 반례 발생 여부
- 같은 행동과 결론의 반복 여부

새 정보 없이 반복되면 `saturated` 신호를 표시하고 보류, 관점 변경, 인간 질문 또는 종료를 제안한다.

## 9. 핵심 인터페이스: 지속형 Terminal TUI

Inquiry는 별도 대시보드보다 Claude Code나 Codex처럼 터미널에 상주하는 대화형 환경을 우선한다.

```text
╭─ inquiry ─ “사람들이 실제로 사용할 멀티모달 Agent OSS는?” ───────────╮
│ Team 4/5  Agents 3  Active 3  Waiting 1  Checks 18  Updated 2s ago │
├─ POSSIBILITY MAP ──────────────────────────────────────────────────┤
│                       ╭─◉ H-12 Replay debugger        [A2]         │
│       ╭─● H-03────────┤                                             │
│ ● ROOT● H-01──────────◆ SYN-04──────◌ H-21 Local workflow builder │
│       ╰─◐ H-06 Evaluation toolkit────× H-09                       │
├─ LIVE TEAM ────────────────────────────────────────────────────────┤
│ ACTOR       STATE       NODE    CURRENT ACTIVITY           ELAPSED │
│ agent-2     thinking    H-12    comparing OSS traces          24s │
│ minji       reviewing   H-06    checking user interviews       6m │
│ agent-4     waiting     H-21    approval from Chanran          3m │
├─ WEEKLY ACTIONS · W34 ─────────────────────────────────────── 3/7 ─┤
│ ☑ 기존 멀티모달 Agent 도구 10개 조사             H-12  minji      │
│ ◉ 개발자 pain-point 인터뷰 정리                   H-06  agent-2    │
│ ☐ Replay debugger CLI mockup 검증                  H-12  chanran    │
│ ☐ 세 가설의 반복 사용 가능성 비교                 ROOT  unassigned│
╰───────────────────────────────────────────────────────────────────╯

● agent-2 is checking H-12

  서로 다른 프레임워크의 화면·음성·도구 호출 기록을 한 타임라인에서
  비교하는 사용 흐름을 조사하고 있습니다.

╭─ H-12 · exploring ─────────────────────────────────────────────────╮
│ [CR] owner · [agent-2] checking · 4 findings · 2 open questions   │
╰───────────────────────────────────────────────────────────────────╯
❯ H-12가 일회성 데모가 아니라 반복 사용될 이유를 확인해줘
```

기본 TUI는 htop처럼 상단에 전체 상태, 중앙에 움직이는 작업 목록, 하단에 주간 체크리스트와 대화 입력을 둔다. 사용자는 별도 대시보드로 이동하지 않고 현재 탐구와 팀 운영 상태를 함께 본다.

### htop형 상태 보기

- 전체 팀원과 에이전트의 online/active/waiting/stale 수
- 현재 actor, 상태, 작업 Node, 활동 내용, 경과 시간
- Node 또는 actor별 정렬과 선택
- 선택한 작업의 hypothesis, Finding, heartbeat 상세 보기
- 실제 heartbeat가 없는 작업은 애니메이션을 중단하고 `paused`로 표시
- 좁은 터미널에서는 `Live Team`과 `Weekly Actions`를 탭으로 접음

```text
[1] Map   [2] Team   [3] Weekly   [4] Docs   [/] Filter
```

### 지도 밀도

- `compact`: 한 줄 상태와 핵심 계보만 표시
- `normal`: 기본 상주 그래프
- `fullscreen`: 전체 그래프를 이동하며 탐색

```bash
inquiry map --layout evidence
inquiry map --layout divergence
inquiry map --layout time
inquiry map --layout team
```

### 시각적 의미

- 중앙선: 현재 중심 사고의 계보
- 위쪽: 지지 또는 확장
- 아래쪽: 반론, 대안 설명, 실패 조건
- 중심선과의 거리: 원래 질문과의 개념적 차이
- 선의 밝기 또는 굵기: 근거 강도
- 노드 링: 불확실성 또는 confidence 범위
- 합류점: 여러 브랜치의 통합

색 외에도 기호와 텍스트를 함께 사용해 접근성을 유지한다.

| 표현 | 상태 |
|---|---|
| 회색 `◌` | 제안됨 또는 미탐색 |
| 파랑 `◉` | 탐색 중 |
| 초록 `●` | 현재 근거상 지지됨 |
| 주황 `◐` | 논쟁 중 |
| 노랑 `∙` | 보류 또는 대기 |
| 빨강 `×` | 사람이 종료 또는 기각 |
| 보라 `◆` | 다른 가설에 통합됨 |

## 10. 활동 애니메이션

작업 중인 노드만 의미 있는 저속 애니메이션을 사용한다. 장식적인 반복 동작보다 현재 활동을 전달하는 것이 목적이다.

```text
Frame 1  ● H-01 ──•──────◉ H-12  agent-2 · thinking
Frame 2  ● H-01 ─────•───◉ H-12  agent-2 · thinking
Frame 3  ● H-01 ───────•─◉ H-12  agent-2 · thinking
```

활동 표현 후보:

```text
◌ ◍ ● ◍   thinking
─·─•─●─   researching
▁▃▅▇▅▃   simulating
◐ ◓ ◑ ◒   reviewing
∙ ∙ ∙     waiting
!           blocked
```

원칙:

- 실제 heartbeat가 있는 작업만 움직인다.
- 측정 불가능한 사고 작업에는 가짜 퍼센트를 표시하지 않는다.
- 전체 작업량이 명확한 시뮬레이션 등에만 `34/100` 진행률을 쓴다.
- 화면 전체가 아니라 변경된 행과 노드만 갱신한다.
- `--no-animation`, `--no-color`, ASCII fallback을 제공한다.

## 11. 팀 협업

### 역할

- `Explorer`: 새로운 가능성을 생성한다.
- `Researcher`: 외부 근거를 수집한다.
- `Critic`: 반례와 취약점을 찾는다.
- `Simulator`: 조건별 결과를 모델링한다.
- `Synthesizer`: 여러 브랜치를 통합한다.
- `Reviewer`: 근거와 결론을 검토한다.
- `Human owner`: 최종 채택·종료 권한을 가진다.

### 책임 모델

```yaml
accountable: chanran
executor: agent:research-2
reviewer: minji
```

에이전트가 실행하더라도 인간 책임자가 유지된다.

### Presence와 작업 점유

```text
              ╭─◉ H-12  A2 · thinking…
    ╭─● H-03──┤
●───● H-01────◆ SYN-04  MK · reviewing
    ╰─◉ H-06  CR · typing…
         ╰────× H-09  closed by Chanran
```

- `claim`과 제한 시간 lease로 중복 작업을 줄인다.
- heartbeat가 끊기면 `active`를 `paused` 또는 `connection-lost`로 전환한다.
- 충돌 시 작업을 버리지 않고 대안 브랜치로 보존한다.
- 다른 팀원의 활동은 대화를 방해하지 않는 작은 이벤트로 표시한다.

## 12. 공동 Actions와 시간

투두는 별도 프로젝트 관리 계층이 아니라 가설을 검증하기 위한 `Next Action`이다.

```text
◉ H-12 멀티모달 Agent Replay debugger는 실제 수요가 있다

  Next actions
  ☑ 유사 오픈소스 프로젝트 10개 조사          MK
  ◉ 개발자 pain-point 인터뷰 정리             agent-2 · working
  ☐ 반복 사용을 방해하는 요인 조사             CR
  ☐ Replay CLI mockup 사용자 검증              unassigned
```

전체 팀 보기:

```text
Working
◉ 개발자 인터뷰 결과 정리       H-12  agent-2

Next
☐ 기존 tracing 도구 비교        H-12  CR
☐ 초기 사용자 인터뷰 요청       H-18  unassigned

Waiting
◌ 테스트 trace 제공 승인        H-06  waiting for Chanran
```

### 시간 모델

초기에는 세 가지 horizon만 기본 제공한다.

- `NOW`: 현재 작업 중
- `NEXT`: 다음으로 할 일
- `LATER`: 유효하지만 지금은 하지 않을 일

Due date와 review cadence는 선택적으로만 사용한다. 초기 범위에는 스프린트, 간트 차트, 스토리 포인트, 복잡한 캘린더를 포함하지 않는다.

### Needs update

업데이트 필요 여부는 단순 날짜가 아니라 상태를 함께 본다.

- `stale`: 설정된 기간 동안 활동이 없음
- `unresolved`: 상반된 근거가 해결되지 않음
- `waiting`: 외부 입력 또는 승인을 기다림
- `orphaned`: 활성 상태지만 담당자가 없음
- `outdated`: 외부 근거의 유효기간이 지남
- `drifting`: 하위 결과와 상위 평가가 불일치함

## 13. Weekly Reflection

Weekly는 별도 관리 객체가 아니라 이벤트 기록과 현재 그래프를 7일 관점으로 보여주는 view다.

```bash
inquiry weekly
inquiry weekly --team research
inquiry weekly --mine
```

포함할 내용:

- 이번 주에 새로 탐색한 가설
- 강화되거나 약화된 가설
- 새 근거와 반례
- 사람의 채택·종료·통합 결정
- 해결되지 않은 논쟁
- 업데이트가 필요한 브랜치
- 완료·진행·대기 중인 Actions
- 다음 주에 탐색할 질문

Weekly의 중심은 활동량이 아니라 **이번 주에 팀의 생각이 어떻게 바뀌었는가**다.

## 14. Markdown 산출물

### 산출물 종류

```bash
inquiry write weekly
inquiry write blog
inquiry write research-note H-001
inquiry write experiment EXP-014
inquiry write decision D-001
inquiry write brief
inquiry write handoff
```

| Output | 목적 |
|---|---|
| Weekly reflection | 주간 변화와 다음 탐구 공유 |
| Research note | 특정 가설과 근거를 깊게 정리 |
| Experiment report | 실험 조건·결과·한계 기록 |
| Decision record | 무엇을 왜 채택·종료했는지 기록 |
| Public blog | 외부 독자를 위한 서사형 글 |
| Brief | 신규 참여자를 위한 현재 상태 요약 |
| Handoff | 다른 사람 또는 에이전트에게 작업 이관 |

### 권장 디렉터리

```text
.inquiry/
├── inquiry.md
├── hypotheses/
├── evidence/
├── decisions/
├── actions/
├── templates/
└── events.jsonl

outputs/
├── weekly/
├── research-notes/
├── decisions/
└── blog/
```

### 추적 가능성

생성 문서에는 기반이 된 Inquiry, event 시점, 관련 가설과 근거를 기록한다.

```yaml
generated_from:
  inquiry: multimodal-agent-oss
  through_event: 184
  generated_at: 2026-08-23T17:30:00+09:00
status: draft
```

그래프가 변경되면 어떤 문서가 오래되었는지 표시한다. 자동 게시보다는 초안 생성, 사람 검토, 승인된 Markdown 저장을 기본 흐름으로 한다.

Markdown에서 발견된 새로운 질문을 그래프로 다시 가져올 수 있지만, 자동 수정하지 않고 사람의 승인을 받는다.

## 15. CLI 초안

```bash
# 시작과 프레이밍
inquiry new
inquiry new --mode thought-experiment
inquiry reframe

# 탐구
inquiry fork H-001 --count 3
inquiry deepen H-003 --depth 2
inquiry challenge H-003 --agent critic
inquiry simulate H-003 --scenario "예산이 30% 감소"
inquiry compare H-001 H-003 H-005
inquiry synthesize H-001 H-005

# 근거와 결정
inquiry evidence add H-003 --supports --file evidence.md
inquiry suspend H-004
inquiry close H-002 --by human --reason "실행 범위 밖"
inquiry reopen H-002

# 팀
inquiry assign H-003 @minji
inquiry assign H-004 agent:research-2
inquiry claim H-004 --lease 2h

# Actions
inquiry action add H-003 "멀티모달 Agent 개발자 인터뷰"
inquiry action check A-014
inquiry actions --team

# 보기
inquiry tui
inquiry map --layout evidence
inquiry map H-003 --depth 3
inquiry watch
inquiry weekly

# 산출물
inquiry write weekly --out outputs/weekly/2026-W34.md
inquiry write blog --audience "Agent 오픈소스 개발자"
```

자연어 대화와 정확한 slash/CLI 명령을 함께 지원한다.

## 16. 기술 구조 초안

```text
Human input ──────┐
Agent output ─────┼──▶ Event stream ──▶ Inquiry graph ──▶ TUI renderer
Team activity ────┤                          │
Evidence ─────────┘                          ├──▶ Markdown compiler
                                              ├──▶ Weekly views
                                              └──▶ Team synchronization
```

### 필수 구성요소

1. `Core graph engine`
   - Node, Edge, 상태 전이, 유효성 검증
2. `Event store`
   - 누가, 언제, 무엇을 변경했는지 append-only 기록
3. `Agent adapter`
   - 특정 모델이나 CLI에 종속되지 않는 실행 인터페이스
4. `TUI renderer`
   - 지속형 그래프, 대화, 활동, Actions 표시
5. `Document compiler`
   - 그래프와 이벤트를 Markdown 템플릿으로 변환
6. `Team service`
   - presence, claim/lease, heartbeat, 동기화

### 저장 구조에서 결정할 사항

다음 중 무엇을 canonical source로 둘지는 프로토타입에서 검증해야 한다.

- 이벤트 로그를 원본으로 하고 Markdown을 projection으로 생성
- Markdown entity 파일을 원본으로 하고 이벤트 로그를 감사 기록으로 사용
- 로컬 데이터베이스를 원본으로 하고 두 형식을 모두 export

제품 철학상 Markdown의 이식성을 유지하면서도 실시간 팀 동기화와 충돌 복구가 가능한 절충이 필요하다.

## 17. MVP 범위

### Phase 0: UX Prototype

목적은 핵심 상호작용을 검증하는 것이다.

- 단일 사용자 로컬 실행
- 막연한 입력에서 3~5회 Framing Session
- 중심 질문과 초기 가설 생성
- `fork`, `deepen`, `challenge`, `synthesize`, `close`
- 흑백 정적 TUI 그래프
- 노드 상세 보기
- 가설별 체크박스 Actions
- Weekly preview
- Markdown export

### Phase 1: Open-source MVP

- 컬러 상태 표현
- 저속 활동 애니메이션
- 여러 에이전트 actor 지원
- evidence와 confidence 출처 관리
- 사고 포화 및 중복 가설 감지
- `NOW / NEXT / LATER`
- Weekly, research note, decision record 템플릿
- Git을 통한 파일 버전 관리 가능
- `--no-color`, `--no-animation`, ASCII fallback

### Phase 2: Team Mode

- 실시간 presence
- claim과 lease
- heartbeat와 stale worker 감지
- 담당자, 실행자, reviewer 분리
- 팀 활동 피드
- 충돌 시 대안 브랜치 보존
- 팀 Weekly와 shared Actions

### Phase 3: 확장

- 웹 그래프 뷰어
- 고급 시뮬레이션 플러그인
- 문헌·데이터·인터뷰 connector
- 외부 문서 및 블로그 게시 연동
- 조직별 템플릿과 정책
- 탐구 그래프 간 재사용 가능한 knowledge link

## 18. MVP 성공 기준

첫 번째 버전은 다음 시나리오를 끝까지 수행할 수 있어야 한다.

1. 사용자가 한 문단의 막연한 생각을 입력한다.
2. 3~5번의 질의응답 후 중심 질문과 범위가 생성된다.
3. 서로 다른 성격의 초기 가설이 제안된다.
4. 사용자가 하나의 가설을 선택해 에이전트에게 탐색시킨다.
5. 가설이 분기되고 근거 또는 반례가 연결된다.
6. 사용자가 특정 브랜치를 종료하거나 여러 브랜치를 통합한다.
7. 가설에 연결된 Action을 생성하고 체크한다.
8. TUI에서 현재 그래프와 작업 상태가 계속 보인다.
9. 탐구의 변화가 Weekly Markdown으로 생성된다.
10. 생성된 Markdown을 도구 없이 읽고 다른 시스템에서 재사용할 수 있다.

## 19. 초기 비범위

- 완전한 프로젝트 관리 또는 Jira/Linear 대체
- Git 브랜치 관리 도구
- 캘린더와 간트 차트
- 정밀한 공수 및 비용 청구
- AI confidence를 객관적인 진실 확률로 보장하는 기능
- 사람 승인 없는 외부 자동 게시
- 무제한 자율 실행
- 특정 모델 공급자 전용 구현

## 20. 주요 위험과 대응

### 그래프 폭발

너무 많은 유사 가설이 생길 수 있다.

- 의미 중복 감지
- 탐색 깊이·시간·비용 제한 (비용·예산·spend cap 정책은 [ADR-D6](./decisions/ADR-D6-cost-model.md) 참조)
- `suggested`와 `active` 분리
- synthesis와 archive 유도

### 가짜 정밀도

에이전트가 만든 `73%`가 객관적으로 보일 수 있다.

- 단일 점수보다 범위 사용
- `agent estimate`, `human judgment`, `measured result` 출처 표기
- evidence strength와 plausibility 분리

### 프로젝트 관리 도구로의 과도한 확장

- Action은 항상 가설이나 Inquiry에 연결
- 시간은 `NOW / NEXT / LATER` 중심
- Weekly는 별도 객체가 아닌 view
- 캘린더·스프린트는 초기 비범위

### 에이전트의 반복 사고

- novelty와 중복도 측정
- 새 근거·전제·연결이 없는 반복 감지
- 관점 변경 또는 인간 질문으로 escalation

### 팀 동기화 충돌

- event 기반 변경 기록
- claim/lease
- 충돌 내용을 대안 브랜치로 보존
- 사람 결정의 명시적 우선권

### 문서와 그래프의 불일치

- 문서 생성 기준 event 기록
- stale document 감지
- 재생성 전 diff와 미리보기
- Markdown import 시 사람 승인

## 21. 미결정 사항

개발 전에 다음을 프로토타입 또는 사용자 테스트로 결정해야 한다.

1. 최종 프로젝트 이름과 CLI command
2. canonical 저장 형식
3. 그래프의 순환 허용 범위
4. confidence 입력과 업데이트 방식
5. 최초 지원 에이전트와 연결 방식
6. 단일 터미널 화면에서 그래프·대화·상세 패널의 최적 비율
7. normal/compact/fullscreen 전환 방식
8. 실시간 팀 서버를 언제 도입할지
9. 생성 Markdown을 수정한 뒤 그래프로 반영하는 round-trip 규칙
10. 외부 근거의 provenance와 인용 규격
11. 사람이 종료한 가설을 다시 제안할 수 있는 조건
12. 공개 블로그 생성 시 민감한 팀 정보의 기본 제외 정책

## 22. 개발 전 권장 검증

코드를 본격적으로 작성하기 전에 다음 세 가지를 먼저 검증한다.

### A. 정적 TUI 프로토타입

- 터미널 폭 80, 120, 160 columns에서 가독성 비교
- 위쪽 지지, 아래쪽 반박 구조가 직관적인지 확인
- 10, 30, 100개 노드에서 정보 과밀도 확인

### B. Framing Session 프로토타입

서로 다른 유형의 입력으로 테스트한다.

- 연구 질문
- 제품 아이디어
- 정책 의사결정
- 창작 아이디어
- 순수 사고실험

질문이 너무 많거나 답을 유도하지 않는지 평가한다.

### C. Markdown 산출물 테스트

동일한 그래프에서 다음 세 문서를 생성해 품질 차이를 확인한다.

- 내부 Weekly
- 근거 중심 Research Note
- 외부 독자용 Blog

단순 활동 요약이 아니라 생각의 변화를 제대로 설명하는지 검증한다.

## 23. 최종 제품 경험

```text
막연한 생각
    ↓
Framing Session
    ↓
중심 질문과 초기 가설
    ↓
사람·에이전트의 병렬 탐구
    ↓
근거·반례·시뮬레이션·사고실험
    ↓
공동 Actions와 사람의 결정
    ↓
Weekly Reflection과 Reframing
    ↓
Markdown 문서·연구 노트·블로그
```

Inquiry의 궁극적인 목표는 더 많은 아이디어를 생성하는 것이 아니다. 팀이 무엇을 생각했고, 무엇을 시험했고, 무엇을 버렸으며, 왜 현재의 판단에 도달했는지를 지속적으로 이해할 수 있게 만드는 것이다.
