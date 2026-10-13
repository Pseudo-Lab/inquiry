# 부트스트랩 UX — 에이전트 seed+frame 제안 → 사람 TUI 수락 (plan)

> 사용자 결정(정책 변경): A5의 "주제는 사람이 타이핑" 불편을 줄이기 위해, **에이전트가 대화 맥락에서 seed+frame을
> 초안으로 제안**하고 **사람은 TUI에서 키 하나로 수락**한다. 경계는 "사람이 originate"→"사람이 **승인**"으로 완화하되,
> **inquiry 생성 게이트(accept=사람 전용)는 그대로 유지** — 에이전트는 여전히 inquiry를 직접 못 만든다.

## 1. 목표 / 범위
- **A. 에이전트 제안:** MCP `inquiry_propose_bootstrap(seed, central_question, …)` → agent-draft seed+frame을 한 번에 'proposed' bootstrap으로.
- **B. TUI 수락:** inquiry 없을 때 TUI가 대기 bootstrap을 보여주고 `accept <BT-id>`/`reject <BT-id>`로 사람이 확정 → inquiry 생성 → 그래프 뷰 전환.
- **C. 기계적:** CLI `--dir` 기본값을 `INQUIRY_DIR` 환경변수로(반복 입력 제거).
- **범위 밖:** 완전 대화형(③안), 기존 A5 human-seed 경로(`inquiry seed`) 제거(유지).

## 2. 현황 (코드 근거)
- A5(현재): `BootstrapSeeded`=human 전용(replay), `BootstrapFrameProposed`=agent(seeded/rejected 필요), `BootstrapAccepted/Rejected`=human. `State.bootstraps` 투영. `IngestService.propose_frame`·`Commands.seed_topic/accept_bootstrap/reject_bootstrap`.
- replay 디스패치: bootstrap kind들은 inquiry-요구 `else` 전에 분기, 액터 불변식 강제. BootstrapSeeded는 현재 `is_human`만 허용(변경 대상).
- TUI: `_reload_state`가 state·nodes 로드(inquiry 없으면 nodes=[]). `_rebuild_table` 빈 분기(394)가 "가설 없음" 렌더. `_dispatch`의 `accept`/`reject`→`_accept`/`_reject`(op/branch proposal 전용). `state.inquiry`로 pre/post 구분 가능(pre-inquiry엔 op proposal 없음).
- CLI `--dir` 기본 `'.'`(cli.py:140).

## 3. 접근

### 3.1 에이전트 bootstrap 제안 (정책 완화)
- **replay 완화:** `BootstrapSeeded`를 human **또는 agent** 허용(초안 작성자 구분은 event actor로). accept/reject는 **human 전용 그대로**(inquiry 생성 게이트 불변).
- `IngestService.propose_bootstrap(seed, frame)` [agent]: 한 이벤트에 `[BootstrapSeeded(agent), BootstrapFrameProposed(agent)]` → status 'proposed', proposed_by=agent. (같은 이벤트 내 순서로 seeded→proposed 적용.)
- MCP `inquiry_propose_bootstrap(seed, central_question, purpose='', criteria=None, scope_include=None, scope_exclude=None)` → 최소 frame 조립 → propose_bootstrap. 구조화 에러. 활동 로깅 포함.
- 기존 human 경로(`seed_topic`→agent `propose_frame`)·`inquiry seed` CLI 유지(둘 다 가능).

### 3.2 TUI 수락
- `_reload_state`: `self.bootstraps = [b for b in state.bootstraps.values() if b['status'] in ('seeded','proposed')]`(대기).
- `_rebuild_table` 빈 분기: inquiry 없고 대기 bootstrap 있으면 **대기 제안 목록** 렌더(id·seed·central_question·proposed_by) + 힌트 "`accept <BT-id>` / `reject <BT-id>`". 없으면 기존 "가설 없음".
- `_dispatch`: `accept`/`reject`에서 `state.inquiry is None`이면 `_accept_bootstrap(rest)`/`_reject_bootstrap(rest)`로, 아니면 기존 proposal 경로.
- `_accept_bootstrap(rest)`: rest=BT-id(없고 proposed 1개면 그것). status 'proposed'(frame 有)만 수락 → `Commands.accept_bootstrap` → `_reload_state`+`_rebuild_table`(이제 inquiry 존재 → 그래프). 'seeded'(frame 無)면 "에이전트 frame 제안 먼저" 안내.
- `_reject_bootstrap(rest)`: BT-id → `Commands.reject_bootstrap(id, 'tui-reject')`.
- 실시간 반영(follow 폴링)으로 에이전트가 propose하면 TUI에 대기 목록 자동 갱신.

### 3.3 CLI 기계적
- `--dir` 기본값 `os.environ.get('INQUIRY_DIR', '.')`. 문서에 alias 예시.

## 4. 수용 기준 (TDD)
`tests/test_bootstrap_propose.py`(A/C) + `tests/test_tui_actions.py` 추가(B):
1. **에이전트 제안:** `inquiry_propose_bootstrap(seed, cq)` → bootstraps[id] status='proposed', proposed_by=agent, frame 반영.
2. **사람 accept로 inquiry 생성:** 위 제안을 `Commands.accept_bootstrap` → state.inquiry 생성, frame 반영.
3. **accept는 여전히 사람 전용:** agent actor로 BootstrapAccepted replay 거부(불변).
4. **TUI pre-inquiry 목록:** inquiry 없고 proposed bootstrap 있을 때 TUI Details/맵에 seed·central_question 노출.
5. **TUI accept:** `app._dispatch('accept <BT-id>')`(inquiry 없음) → **`state.inquiry` 생성됨**(critic N5: 가설 0개라 nodes는 여전히 []; "inquiry 없음"이 아니라 "inquiry 있고 가설 없음" 메시지로 전환). "nodes 생김"으로 단언하지 말 것.
6. **TUI reject:** `reject <BT-id>` → status rejected, 상태 불변(inquiry 없음).
7. **seeded(frame無) accept 거부:** 사람 seed만 있고 frame 없으면 TUI accept가 안내하고 미생성.
8. **INQUIRY_DIR:** env 설정 시 `--dir` 생략해도 그 폴더 사용(cli 단위테스트).
9. **회귀:** 기존 A5 human-seed 경로·op/branch proposal accept/reject·전체 스위트 그린. (A5 `test_agent_cannot_seed`는 **정책 변경 반영해 갱신** — agent 제안 허용.)

## 5. 작업 순서(TDD) — critic N1: 2개 PR로 분리
**PR-1(도메인+MCP+CLI, Textual 무관):**
1. red: propose_bootstrap·accept 흐름 → 실패.
2. green: replay 완화(BootstrapSeeded human|agent, 1줄) + **IngestService.propose_bootstrap(새 코드: 자체 bid 생성, `_commit` 2-arg, allow_new=True, [BootstrapSeeded, BootstrapFrameProposed] 방출)** + MCP `inquiry_propose_bootstrap`(append_activity 포함) + `import os`로 `--dir` 기본 `INQUIRY_DIR`.
3. 테스트 갱신: tool 집합 8개, `test_agent_cannot_seed`→정책 반영(agent 제안 허용, accept 불가 유지), stale 주석/hint 갱신(replay.py:290-291, service.py:112-113, commands.py:84, mcp_server status hint).
4. 전체 스위트 그린, 커밋, PR, 머지.

**PR-2(TUI pre-inquiry 수락 UI):**
5. 빈 분기에서 `state.inquiry is None` AND 대기 bootstrap이면 **정적(비선택) 목록** 렌더(critic N2: self.nodes/self.sel 재사용 금지, `accept <BT-id>` 명시 id). inquiry 있고 가설 0개면 기존 메시지.
6. `_dispatch` accept/reject를 `state.inquiry is None`에서 `_accept_bootstrap(rest)`/`_reject_bootstrap(rest)`로(reject에 rest 전달).
7. TDD: no-inquiry 픽스처(신규 — 기존 TUI 테스트는 전부 inquiry 존재, critic G4). accept→`state.inquiry` 생성 단언(N5). 커밋, PR, 머지.

## 6. 위험/주의
- **게이트 불변식**: accept(InquiryCreated)=human 전용 유지가 핵심. 완화는 BootstrapSeeded(제안 originator)에만. 테스트3로 고정.
- **A5 테스트 갱신**: `test_agent_cannot_seed`는 이제 정책상 허용 → 갱신(삭제 아닌 의미 변경: "agent는 제안 가능, accept는 불가").
- **TUI accept/reject 중의성**: pre-inquiry(bootstrap) vs post-inquiry(proposal)를 `state.inquiry`로 분기(겹침 없음 — pre엔 proposal 없음).
- **등록 tool 집합**: `inquiry_propose_bootstrap` 추가로 8개 → test_build_server_registers_tools 갱신.
- 에이전트가 seed를 초안하므로 "엉뚱한 주제 생성" 가능 → 사람 accept 게이트가 방어. reject로 재제안 유도.
