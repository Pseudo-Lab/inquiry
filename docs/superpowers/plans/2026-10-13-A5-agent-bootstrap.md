# A5 — 에이전트 inquiry 부트스트랩 (C: 사람 seed → 에이전트 frame 제안 → 사람 accept) (plan)

> 핸드오프 Track A/A5. 지금은 사람이 init해야 에이전트가 push 가능. **정책 결정(사용자): 주제(seed)는 항상 사람이 던진다.
> 에이전트는 그 seed에 대해 frame을 제안만 하고, 사람이 accept해야 inquiry가 생긴다**(ADR-D12 경계: 사람 부트스트랩/확정, 에이전트 제안).

## 1. 목표 / 범위
- **목표:** (A) inquiry 미존재 시 에이전트에게 명확한 안내 + (C) 사람 seed → 에이전트 frame 제안 → 사람 accept → InquiryCreated.
- **범위 밖:** LLM-run framing(self-run, agent:runner) 재사용 — 피벗과 불일치. 무거운 8필드 frame 강제(최소 frame로 충분). TUI accept UI(후속; 우선 CLI).

## 2. 현황 (코드 근거)
- `IngestService._commit`(ingest/service.py:40): `state.inquiry is None`이면 'Initialize an inquiry first (the human bootstraps it).' — 모든 agent push 차단.
- 사람 부트스트랩: `Commands.initialize(seed, frame)`(commands.py:74) → `InquiryCreated(seed, frame)`, actor=human:local. CLI `init`(cli.py:206,455)은 `initialize(seed, {'question': q})`로 **최소 frame** 사용.
- **InquiryCreated 검증(events.py:238-243): seed=text, frame=dict이면 OK** — 임의 최소 frame 통과(무거운 validate_frame 불필요).
- 기존 framing(features/framing)은 LLM-run(Runner, `agent:runner`, FrameProposed는 run_id 필수, validate_batch가 actor=agent:runner 강제) → **피벗의 harness-agent 제안과 불일치, 재사용 안 함**.
- `State`(model.py)에 부트스트랩 컬렉션 없음 → 신규 projection 필드 필요.
- replay 디스패치(replay.py:280 else)는 inquiry 존재를 요구 → pre-inquiry 신규 kind는 **그 앞에서** 처리해야.

## 3. 접근 — 경량 bootstrap 경로(framing과 별개)

### 3.1 신규 이벤트 (pre-inquiry, 각 trivial)
- `BootstrapSeeded {kind, bootstrap_id, seed}` — 사람이 주제 던짐.
- `BootstrapFrameProposed {kind, bootstrap_id, frame}` — 에이전트가 구조화 frame 제안(최소: central_question·purpose·criteria·scope).
- `BootstrapAccepted {kind, bootstrap_id}` — 사람 확정(InquiryCreated와 같은 이벤트에 동반).
- `BootstrapRejected {kind, bootstrap_id, reason}` — 사람이 약한 제안 폐기(에이전트 재제안 유도).
- CHANGE_FIELDS 등록 + events.py 검증 branch(bootstrap_id text; frame dict; seed text; reason text).

### 3.2 State 투영
- `State.bootstraps: dict` 추가(기본 빈 dict). `{bootstrap_id: {id, seed, frame|None, status: seeded|proposed|accepted|rejected, proposed_by|None}}`.
- replay: 신규 kind를 **inquiry 존재 요구 전에** 처리. 액터 불변식 — Seeded/Accepted/Rejected=human, FrameProposed=agent(is_agent_actor). Accept는 InquiryCreated도 동반(이후 inquiry 존재).

### 3.3 서비스
- `Commands.seed_topic(seed)` [human] → BootstrapSeeded, `_commit(allow_new=True)`. 이미 inquiry 있으면 거부.
- `Commands.accept_bootstrap(bootstrap_id)` [human] → bootstrap이 proposed여야. 한 이벤트에 **[InquiryCreated(seed, frame), BootstrapAccepted(bootstrap_id)] 순서**(critic G2: InquiryCreated 먼저). 이미 inquiry 있으면 거부.
- `Commands.reject_bootstrap(bootstrap_id, reason)` [human] → BootstrapRejected.
- `IngestService.propose_frame(bootstrap_id, frame)` [agent] → BootstrapFrameProposed. **critic B2: `IngestService._commit`에 `allow_new=False` 파라미터 추가**(Commands._commit 미러, 중복 없이). propose_frame은 `_commit(build, allow_new=True)`. bootstrap이 seeded/rejected여야, inquiry 이미 있으면 거부.

### 3.4 MCP
- `inquiry_propose_frame(bootstrap_id, central_question, purpose, criteria, scope_include, scope_exclude)` → 최소 frame dict 조립 → IngestService.propose_frame. 구조화 에러(add_evidence 패턴).
- **(A 안내, critic B1)** `mcp_server.status`에서만 분기(monitor.summary·TUI 불변): `state.inquiry is None`이면
  `{initialized: false, bootstraps: [{id, seed, status, has_frame, proposed_by}], hint: "..."}` 반환, 아니면 기존 summary 그대로. push 에러도 seed 언급.
- 터미널 생성(InquiryCreated)은 tool로 노출 안 함 — 사람 accept 전용.

### 3.5 CLI (사람 게이트)
- `inquiry seed <topic>` → seed_topic.
- `inquiry bootstrap list` (JSON) → 대기 중 bootstraps.
- `inquiry bootstrap accept <id>` → accept_bootstrap.
- `inquiry bootstrap reject <id> --reason` → reject_bootstrap.

## 4. 수용 기준 (TDD, tests/test_agent_bootstrap.py)
1. **seed→propose→accept 전체 흐름:** 사람 seed → 에이전트 propose_frame → 사람 accept → `state.inquiry` 생성, frame 반영, bootstrap status=accepted.
2. **에이전트는 inquiry 못 만듦:** propose_frame만 가능; InquiryCreated를 내는 agent 경로 없음(accept는 human). agent actor로 BootstrapAccepted/InquiryCreated replay 거부.
3. **주제는 사람이:** propose_frame은 기존 bootstrap(사람 seed) 없으면 에러(에이전트가 seed 발명 못 함).
4. **미초기화 안내(A):** inquiry 없을 때 `inquiry_status` → initialized:false + 대기 bootstraps + hint. push 에러에 seed 언급.
5. **reject 후 재제안:** 사람 reject → 에이전트가 같은 bootstrap에 다시 propose 가능.
6. **이미 inquiry 있으면:** seed/propose/accept 모두 거부(단일 inquiry).
7. **최소 frame 통과:** central_question만 있는 최소 frame도 accept→InquiryCreated 성공.
8. **CLI:** seed·bootstrap list·accept 동작. **회귀:** 기존 init/framing 불변.

전체 스위트 그린(현재 242 그린 유지).

## 5. 작업 순서(TDD)
1. red: seed→propose→accept 흐름 → 실패.
2. green: 이벤트+검증+replay+State.bootstraps + 서비스.
3. MCP(propose_frame, status 안내)·CLI red→green.
4. 액터 불변식·주제-사람·reject·단일 inquiry·최소 frame.
5. 전체 스위트, 커밋, PR, 머지, 정리.

## 6. 위험/주의
- **State 필드 추가**: replay의 State(...) 생성자(위치 인자)에 bootstraps 전달 — 누락 시 기존 테스트 깨짐. 끝에 추가 + 명시 전달.
- **pre-inquiry 커밋**: IngestService/Commands 모두 inquiry-필수 가드가 있음 → bootstrap 경로만 우회(그 외는 불변).
- **액터 경계**: FrameProposed=agent만, Seeded/Accepted/Rejected=human만 — replay에서 강제(테스트2).
- 새 이벤트 kind는 replay 디스패치에서 inquiry-요구 else보다 **먼저** 분기(안 그러면 'Create an inquiry before domain objects'로 막힘).
- 피벗 불일치 방지: LLM framing 재사용 금지(agent:runner·run_id 결합). 완전 별도 경량 경로.
