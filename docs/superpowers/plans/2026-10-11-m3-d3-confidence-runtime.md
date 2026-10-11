# M3-D3 Confidence/Evidence Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` for sequential implementation, or `subagent-driven-development` for bounded delegated work. Apply `test-driven-development` and `verification-before-completion` for each task. 체크박스는 검증 후에만 완료로 바꾼다.

**Goal:** ADR-D3가 결정한 5축 평가(범위 `[low, high]` + source + evidence_ref)를 런타임에 **저장·replay**할 수 있게 한다. 채점은 기존 `Adapter`/`Runner` 경계를 거치는 **런타임 agent run**(`operation='hypothesis.assess'`)으로 수행하고, run 성공과 **원자적으로** `HypothesisAssessed`(agent-estimate)를 기록한다 — operation과 달리 **사람 승인 2단계(OperationProposed→OperationAccepted)를 쓰지 않는 1단계 직접 투영**이다. M3 첫 항목이며, 이후 "근거 기반 가설 제안"·saturation/dedup(§8)이 이 데이터 모델 위에 선다.

**Architecture:** 이벤트 소싱 계약(`domain/events.py` 검증 → `domain/replay.py` projection → `domain/model.py` frozen dataclass)을 그대로 재사용한다. **채점은 operation 경로(deepen/challenge/synthesize)를 재사용하지 않는 전용 1단계 경로**다 — operation 경로는 사람 승인 2단계·`operation/state.py:63` whitelist로 assess를 거부하므로 건드리지 않는다. 채점 run은 `RunStarted(operation='hypothesis.assess', target_ids=[자기 자신], session_id=None)` → `RunSucceeded` + 동반 `HypothesisAssessed`(Runner가 `agent:runner`로 원자 기록)로 끝난다. 평가 결과는 독립 proposal dict가 아니라 **기존 Hypothesis 노드에 부착**되므로, projection은 `domain/replay.py`의 `_apply_domain`-style(`HypothesisStateChanged`가 `hypotheses[id] = replace(...)`하는 것과 동형)로 Hypothesis를 `replace`한다.

**Tech Stack:** Python 3.9+, 표준 라이브러리 unittest, 기존 OpenAI Responses 어댑터와 설치된 `.venv`. 새 의존성 없음.

**Status:** 2026-10-11 계획 수립 → critic 1회차 CHANGES NEEDED → 2026-10-12 B1/B2 확정(런타임 agent run) + G1~N3 반영해 개정 → critic 2회차 CHANGES NEEDED(개정의 "operation run과 동형" 서술이 코드와 충돌) → **assessment 전용 1단계 경로**로 재개정(B'1~B'3 해소) → **Task 1~6 전부 구현·검증 완료(2026-10-12).** → **표현계층 thin slice: `assess` CLI(score/reassess/show) 추가**(실제 터미널 검증용). 신규 56 테스트, 전체 74개 그린.

**후속 슬라이스 (2026-10-12):** `inquiry assess score|reassess|show <hid>` CLI를 기존 branch/explore 패턴(lazy `adapter_factory`·NOTICE)으로 추가. `AssessmentService`에 `adapter_factory` 지원 추가. `show`는 키 없이 조회, `score`/`reassess`는 `.env`의 `OPENAI_API_KEY` 필요. `tests/test_assessment_cli.py` 4개. 나머지 표현계층(컬러/애니메이션/NOW·NEXT·LATER/TUI 통합)은 M3 후반 유지.

**라이브 API 검증 + 수정 (2026-10-12):** 실제 `gpt-5.6-terra`로 score/reassess 호출 확인. 두 버그 수정 —
1. `openai_adapter._create` operation 화이트리스트에 `hypothesis.assess`/`reassess` 누락 → 추가(없으면 `invalid-request`). 계획의 "RunStarted operation whitelist 확인" 항목이 실제로 adapter 레벨에서 필요했음.
2. reassess가 링크된 evidence를 모델에 **전달하지 않아** evidence_strength가 L0 "증거 없음"으로 채점되던 버그 → `AssessmentService._linked_evidence`로 context에 실어 보내고 adapter reassess payload에 포함. 실측 재확인: evidence_strength가 근거를 인용(L1 [0.25,0.35], evidence_refs=[E-001]).
`tests/test_assessment_evidence_plumbing.py` 4개(서비스 context 전달 + adapter `_create` payload + 미지 operation 거부). 전체 78개 그린.

**선행 결정 (사용자 확정):**
- **착수 순서(2026-10-11):** M3 추천 순서(D3 → spend cap → 다중 actor → saturation/dedup → 근거 기반 가설 제안 → 표현계층 → 외부검증 2회차) 중 **첫 항목**.
- **축(2026-10-11):** 5축 전부 채점 대상. 포트폴리오 축(novelty·impact)도 optional로 두지 않는다. 단 "채점 대상"과 "현 시점 값 존재"는 다르다 — 근거 없는 시점의 축은 명시적 `null`(N2).
- **이벤트(2026-10-11):** **옵션 A** — `HypothesisAssessed`(전체 스냅샷) + `ConfidenceUpdated`(축별 델타).
- **원칙 4(2026-10-11):** **advisory(경고)** — 근거 없는 상향은 거부하지 않고 flag 기록.
- **채점 주체(B1, 2026-10-12):** **런타임 agent run**. OpenAI 어댑터가 채점 → agent-estimate. `assess-hypothesis/SKILL.md`는 **프롬프트 콘텐츠 정본**일 뿐 런타임이 호출하는 대상이 아니다. 사람 확정(human-judgment 승격) 오프라인 `record()` 경로는 **범위 밖(후속)**.
- **승격 단계(B'2/B'3, 2026-10-12):** 채점은 **operation 경로를 재사용하지 않는 전용 1단계**. assess proposal은 사람 승인 없이 run 성공과 원자적으로 `HypothesisAssessed`(`agent:runner`)로 기록된다. operation의 `OperationProposed`→`OperationAccepted` 2단계를 쓰지 않으며 operation whitelist(`operation/state.py`, `operation/service.py`, OPERATION_SCHEMAS)를 건드리지 않는다. 자동 기록이지만 source는 `agent-estimate`로 남아 "확정"이 아니다(원칙 3 정합).

## Global Constraints

- 정본: [ADR-D3](../../decisions/ADR-D3-confidence-model.md), [ADR-D5](../../decisions/ADR-D5-state-machine.md), [assess-hypothesis 스킬](../../../.claude/skills/assess-hypothesis/SKILL.md), [MILESTONES §M3](../../MILESTONES.md).
- **범위 저장 계약(D3):** 각 축은 단일 점수가 아니라 `[low, high]`(0≤low≤high≤1)로 저장. 요약 점수는 파생값으로만. 임의 폭 금지 — 범위는 인접 등급 간 불확실성을 뜻한다.
- **미채점 축(N2·G6):** 아직 근거가 없는 축은 **명시적 `null`** 로 저장한다. `events.py`의 `CHANGE_FIELDS`가 정확한 필드 집합을 요구하므로(136행) **필드 생략은 거부** — null을 명시적으로 넣는다.
- **source 위계(D3):** `agent-estimate < human-judgment < measured-result`. 런타임 채점은 **항상 `agent-estimate`** 이며 자동 확정하지 않는다(원칙 3). 상위 source로의 승격은 이번 범위 밖.
- **원칙 2(외부 증거만, N3):** evidence_ref는 기존 `Evidence`(`EVIDENCE_TYPES`: external-article·measured-result·human-interview·human-judgment·dataset)만 가리킨다. review note(`ReviewNoteCreated.origin='model-opinion'`)·`llm-opinion`은 불가. `events.py`의 기존 배제 규칙을 약화하지 않는다.
- **원칙 4(advisory, G5):** evidence_ref 없는 등급 상향은 **거부하지 않고** `unverified=true` 플래그 + rationale 열린질문으로 기록. 이는 D3 본문(원칙 4 "허용한다"의 강한 표현)을 M3에서 **운용상 완화**하는 것이므로, **ADR-D3에 운용 결정을 반영(또는 열린 질문 추가)하는 후속 작업을 범위에 포함**(Task 6). 정본 drift를 남기지 않는다.
- **채점 run 경로(B1·B2·B'1~B'3):** `operation='hypothesis.assess'` RunRequest(target=자기 자신 1개, `session_id=None`, 단일 배치)를 만들고 `features/assessment/prompts.py`의 고정 프롬프트 + output_schema로 어댑터가 채점 JSON을 반환한다. Runner가 **`RunSucceeded`와 원자적으로 `HypothesisAssessed`를 `agent:runner`로 기록**한다. 따라서:
  - **(B'1)** `runs.py:159`의 success allow-list(현재 `{FramingControlRecorded, QuestionsIssued, FrameProposed, BranchProposed, OperationProposed}`)에 `HypothesisAssessed`(및 exploring 재채점용 `ConfidenceUpdated`)를 **추가**한다.
  - **(B'2)** operation 경로(`operation/state.py`·`operation/service.py:72`·OPERATION_SCHEMAS/PROMPTS)는 **수정하지 않는다** — assess는 전용 경로이므로 "Operation is not implemented yet" 거부(operation/state.py:63)에 닿지 않는다.
  - **(B'3)** `replay.py`의 `_apply_run` RunStarted snapshot 분기(33-36행)는 fork/deepen/… 만 처리하므로 `hypothesis.assess`는 `target_snapshot=None`이 된다. assess는 operation의 target_snapshot 재계산 비교(operation/state.py:73)를 **타지 않으므로** None이 무해함을 보장한다. 단 `RunStarted`가 `operation='hypothesis.assess'`를 거부하지 않는지(운영 whitelist 유무) 확인·필요 시 등록한다.
  - 사람 확정의 `_commit`/`human:local` 경로는 이번 범위 밖.
- **ConfidenceUpdated 제약(G4):** `evidence_ref`는 **대상 Hypothesis에 이미 `EvidenceLinked`된** Evidence id만 허용(링크 선행). exploring 중 evidence_strength 갱신은 기존 `EvidenceCreated`/`EvidenceLinked`를 대체하지 않고 그 위에서 축 값만 갱신한다.
- **projection 스타일(G2):** `HypothesisAssessed`/`ConfidenceUpdated`는 `domain/replay.py`의 `_apply_domain`에 분기를 추가해 `hypotheses` 가변 dict의 대상 Hypothesis를 `replace(hypo, assessment=...)`로 갱신한다. operation-style 독립 proposal projection을 쓰지 않는다.
- **kind 검증(G1):** 두 새 kind를 `domain/events.py`의 `CHANGE_FIELDS` 중앙 whitelist에 **정확한 필드 frozenset**으로 등록한다. 미등록 시 "Unsupported change kind"로 거부됨.
- **스냅샷 하위호환(G3):** `parent_snapshot`(branch/schema.py:44)이 `asdict(hypothesis)` 전체를 쓰므로, `assessment` 필드 추가가 기존 run의 `target_snapshot` 재계산 비교(operation/state.py:73, branch/state.py:58)를 깬다. **`parent_snapshot`이 `assessment` 키를 제외**하도록 수정해 구버전 로그 무회귀를 보장한다(assessment는 후보 생성용 부모 투영이 아니다).
- `.env`, 실제 `.inquiry`, 사용자 설치 환경은 읽거나 수정하지 않는다. 모든 테스트는 합성 데이터와 TemporaryDirectory를 쓴다. 실제 API 호출·커밋·푸시는 별도 사용자 요청 전 하지 않는다.
- 기존 `schema_version=1` 로그를 그대로 읽는다. 새 이벤트 kind는 명시적으로 검증하고, 구버전 프로그램이 새 kind를 거부하는 동작은 유지한다. downgrade 호환을 주장하지 않는다.
- 기존 상태 전이(`transitions.py`)·Branch·Framing·Operation 저장 형식과 closure의 `evidence_snapshot` 계약을 보존한다. Store 검증 약화, 자동 상태 승격, 자동 재채점은 없다.
- 구현 순서는 Task 1→2→3→4→5→6이다. 각 단계가 통과하기 전 다음으로 확장하지 않는다. 공유 파일 동시 수정을 피한다.

## 파일과 책임

| 파일 | 책임 |
|---|---|
| 수정 `domain/model.py` | `Assessment` 값 객체(축별 `{low, high, source, evidence_refs, unverified, rationale, updated_at}`) + `Hypothesis.assessment: Optional[Assessment] = None`. frozen 유지 |
| 수정 `features/branch/schema.py` | `parent_snapshot`이 `assessment` 키를 제외하도록(G3 하위호환) |
| 새 `features/assessment/schema.py` | 축 이름 집합, 범위(0≤low≤high≤1)·source 위계·null 규칙의 **순수 형식 검증**. evidence_ref **존재성**은 여기서 안 함(N1) |
| 새 `features/assessment/prompts.py` | 채점 run 고정 시스템 프롬프트 + output_schema(5축). SKILL.md 앵커를 정본으로 참조 |
| 새 `features/assessment/service.py` | AssessmentService: `hypothesis.assess` RunRequest 구성(target=자기 자신, session_id=None), run 성공과 원자적 `HypothesisAssessed`(`agent:runner`) 기록, evidence_strength `ConfidenceUpdated`, 조회. **operation 경로 재사용 안 함** |
| 수정 `llm/runs.py` | Runner success allow-list(159행)에 `HypothesisAssessed`·`ConfidenceUpdated` 추가(B'1) |
| 수정 `domain/events.py` | `CHANGE_FIELDS`에 두 kind 등록 + payload 검증(범위/source/null/advisory 플래그). 기존 Evidence·transition·operation 검증 불변 |
| 수정 `domain/replay.py` | `_apply_domain`에 두 kind 분기 추가 — 대상 Hypothesis를 `replace`해 assessment 투영(evidence_ref 존재성·EvidenceLinked 선행 검증 포함). `_apply_run`은 `hypothesis.assess`에 snapshot 불요(None 무해, B'3) |

## Tasks

### Task 1 — `Assessment` 모델 + 직렬화 왕복 + 스냅샷 하위호환 ✅ (2026-10-12)
- `domain/model.py`에 `Assessment` frozen dataclass와 축 값 객체, `Hypothesis.assessment` 필드 추가.
- `features/branch/schema.py`의 `parent_snapshot`이 `assessment`를 제외하도록 수정.
- **수용 기준:** (a) 4축을 범위+source로 담은 Hypothesis `asdict` 왕복 동일, `evidence_strength=None` 허용. (b) assessment 없는 구버전 Hypothesis 로드 정상. (c) **`parent_snapshot(hypothesis)` 출력이 assessment 추가 전후 동일** — 기존 operation/branch target_snapshot replay 무회귀(합성 구버전 로그로 검증).
- **결과:** `AxisScore`/`Assessment` 추가, `assessment` 필드는 끝에 default None(위치인자 생성 영향 없음). `parent_snapshot`은 `assessment` 키 제외. `tests/test_assessment_model.py` 8개 신규 통과, 전체 `unittest discover -s tests` 26개 그린(무회귀).

### Task 2 — assessment 순수 형식 검증 (schema) ✅ (2026-10-12)
- `features/assessment/schema.py`: 축 whitelist, `0≤low≤high≤1`, source 위계, 미채점 축 명시적 null, advisory(상향+evidence_ref 없음 → `unverified=true` 허용·기록).
- **수용 기준:** `low>high`·범위밖·미지 축·미지 source·필드 생략은 거부. 상향+근거없음은 **거부되지 않고** unverified 플래그 세팅. **evidence_ref 존재성은 검증하지 않음**(replay 소관, N1).
- **결과:** `features/assessment/{__init__,schema}.py` 생성. `AXES`·`SOURCE_RANK`·`validate_axis`·`validate_assessment`. 관계적 규칙(상향 판정·source 역행 방지·evidence_ref 존재성)은 Task 3로 분리하고 순수 형식만 검증. `tests/test_assessment_schema.py` 16개 신규 통과, 전체 42개 그린.

### Task 3 — 이벤트 검증 + `_apply_domain` projection + Runner allow-list ✅ (2026-10-12)
- `domain/events.py` `CHANGE_FIELDS`에 `HypothesisAssessed`·`ConfidenceUpdated` 정확한 필드 frozenset 등록 + payload 검증.
- `llm/runs.py:159` success allow-list에 두 kind 추가(B'1) — run 성공과 원자적으로 저장 가능하게.
- `domain/replay.py` `_apply_domain`에 두 kind 분기 — 대상 Hypothesis를 `replace`. `ConfidenceUpdated.evidence_ref`는 **이미 EvidenceLinked된 Evidence만**(선행 검증), 존재성은 `evidence`/링크 dict 대조. `_apply_run`은 `hypothesis.assess`에 snapshot을 만들지 않음(None 무해).
- **수용 기준:** `HypothesisAssessed`→`ConfidenceUpdated`(evidence_strength) 로그 replay 시 5축 정확 복원, 축별 델타는 해당 축만 갱신·나머지 보존. 미등록 kind/미링크 evidence_ref/없는 Hypothesis는 거부. `hypothesis.assess` run은 target_snapshot 없이도 replay 통과. 구버전 로그 replay 회귀 없음. **operation 검증 경로 불변 확인**(기존 operation 테스트 그대로 통과).
- **결과:** events.py에 두 kind 등록·검증(schema 재사용), runs.py allow-list 확장, replay.py `_axis_score`/`_check_refs` 헬퍼 + 두 projection 분기. `updated_at`은 event.at에서 스탬프. snapshot 축의 evidence_ref도 존재+링크 검증. `tests/test_assessment_events.py` 13개 통과, 전체 55개 그린(additive 변경, operation/branch 경로 불변).
- **스코프 결정(후속 가능):** `run_id`는 기록하되 replay에서 "실제 성공한 `hypothesis.assess` run"인지 batch 수준 링크 검증은 하지 않음(`_apply_domain`에 `runs` 미전달; Runner가 유일 발행자). operation의 `validate_operation_batch`급 run 링크 검증이 필요하면 후속으로 추가. B'3(assess run snapshot=None 무해)은 Task 5 e2e에서 실제 run으로 확정.

### Task 4 — AssessmentService (채점 run 수명주기, 전용 1단계 경로) ✅ (2026-10-12)
- `features/assessment/service.py`: `suggested` 진입 시 `operation='hypothesis.assess'` run(target=자기 자신 1개, session_id=None, 단일 배치)으로 4축(plausibility·novelty·impact·testability) 초기 채점 → run 성공과 **원자적으로 `HypothesisAssessed`**(`agent:runner`) 기록. exploring 중 evidence_strength `ConfidenceUpdated`. 조회. **operation whitelist·OPERATION_SCHEMAS는 수정하지 않는다.**
- **수용 기준:** 가설 1건에 초기 채점 1건 + evidence 추가 후 evidence_strength 갱신 1건이 이벤트 스토어에 기록·조회. **사람 승인(OperationAccepted) 없이** source=`agent-estimate`로 투영(자동 상태 전이 없음, 확정 아님). 키·SDK 없이 조회 가능(합성 어댑터로 테스트).
- **결과:** `AssessmentService.assess`/`update_confidence`/`assessment` + 공용 `_score`가 Runner `success_changes` 경유 원자 발행(operation 경로 미사용). `prompts.py`(output_schema·시스템 프롬프트 v0), `schema.validate_initial_output` 추가. `tests/test_assessment_service.py` 8개 통과, 전체 63개 그린. **B'3 실증:** `hypothesis.assess` run이 실제 RunStarted→Dispatched→Succeeded 흐름에서 `target_snapshot=None`으로 성공(Task 5 e2e 확인분을 실제 run으로 달성). status 불변(agent-estimate ≠ 전이).

### Task 5 — 채점 run end-to-end ✅ (2026-10-12)
- `features/assessment/prompts.py` 프롬프트+output_schema로 `hypothesis.assess` run이 채점 JSON을 반환 → run 성공과 원자적 `HypothesisAssessed` 기록 → replay 복원까지 통합.
- **수용 기준:** 합성 어댑터로 run 1회 → assessment 이벤트 영속화 + replay 복원 end-to-end 통과. SKILL.md 앵커와 output_schema 축 정의가 일치.
- **결과:** prompts.py에 SKILL.md L0–L4 눈금 + 5축 앵커 전사, output_schema 축/필드/source enum이 런타임 schema와 일치(테스트로 고정), 모듈 로드 시 축 커버리지 assert. e2e 내구성: 새 service 인스턴스가 store를 처음부터 replay해 동일 복원(초기 채점→evidence 링크→evidence_strength 갱신 전체 사이클). `tests/test_assessment_prompts.py` 7개 통과, 전체 70개 그린.

### Task 6 — ADR-D3 운용 결정 반영 (문서) ✅ (2026-10-12)
- 원칙 4를 M3에서 **advisory로 운용**한다는 결정을 ADR-D3에 반영(또는 열린 질문 추가). 채점 주체=런타임 agent run(agent-estimate), 오프라인 human-judgment 승격은 후속임을 기록.
- **수용 기준:** ADR-D3가 코드 동작(advisory·agent-estimate)과 정합. 정본 drift 없음.
- **결과:** ADR-D3에 "M3 런타임 운용 결정(2026-10-12)" 섹션 추가 — 채점 주체(런타임 agent run, 전용 1단계), "기록≠확정"으로 원칙 3과의 정합 명시, 원칙 4 advisory 운용, evidence_ref 규칙, 채점 시점. 열린 질문에 원칙 4 강제 수위·assessment↔run 링크 검증 2건 추가. 보완 일자 갱신.

## 범위 밖 (후속)
- **오프라인 `record()` 경로**(사람/Claude Code가 human-judgment로 확정, `_commit`/`human:local`): 런타임 채점 안정 후 M3 내 재판단.
- **GRADE 범위 확장 트리거**(risk_of_bias/inconsistency/indirectness/imprecision)·**stale/decay 신호**: D3 열린 질문.
- **여러 evidence 집계식**(규칙 vs 사람 판단): D3에서 "M3 실측 후 결정"으로 미룸. 신뢰 축에 한해 추후 검토.
- confidence 히스테리시스(supported↔contested flapping 방지, ADR-D5 열린 질문).
- novelty를 §8 dedup 파이프라인에 실제 연결하는 것은 M3 saturation/dedup 항목에서.
