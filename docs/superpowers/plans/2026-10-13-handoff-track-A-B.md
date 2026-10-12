# 핸드오프 — Track A(피벗 후속) · Track B(M3 잔여)

> **새 세션용 단일 진입점.** 이 문서만 읽으면 현황·관례·할 일·순서를 알 수 있다. 각 항목은 "목표 / 관련 파일 / 접근 / 수용 기준 / 우선순위"로 적었다. 항목별 상세 설계는 **착수 시 plan→critic→TDD 구현** 루프로 직접 세운다(아래 "작업 방식" 참조).

## 0. 프로젝트 현황 (2026-10-13 기준)

**inquiry**는 사람과 여러 AI 에이전트가 공유하는 **구조화된 탐구 그래프**다. 2026-10-12 **방향 전환([ADR-D12](../../decisions/ADR-D12-monitor-control-plane.md))**: inquiry는 스스로 LLM을 호출하는 agent runner가 아니라, **외부 harness 에이전트(Claude Code/Codex가 MCP로 push)의 산출물을 모니터링하는 control-plane**이다. 생성은 harness가, inquiry는 수용·모니터·사람 결정.

**이미 완료(머지됨):**
- 코어: 이벤트 소싱(D1)·그래프 DAG(D2)·confidence(D3)·agent-adapter(D4)·상태머신(D5)·spend cap(D6).
- M3: **다중 actor 역할 에이전트(D10)** — `agent:<name>` 귀속, persona. **saturation/dedup(D11)** — 토큰 Jaccard 중복·포화 신호.
- 피벗(D12) Phase 0–3: **MCP 인제스천 서버**(`inquiry mcp --agent <name>`, 실제 Claude Code stdio 연동 검증됨), **IngestService**(agent 귀속 push), **control-plane TUI**(`inquiry tui` = git-graph 지도 + ↑↓ 드릴다운 + 실시간 갱신 + 에이전트 귀속/recency + 결정대기 배지), `status`/`review`(기계용 JSON).
- 견고성: 동시 쓰기 자동 재시도(`store.retry_on_contention`), 로그 변경 감지(`Store.signature`).

**핵심 모듈 지도:**
- `domain/`: `events.py`(이벤트 검증·CHANGE_FIELDS) · `replay.py`(state projection) · `model.py`(dataclass) · `transitions.py`(상태 전이·`is_agent_actor`·`_AGENT_EDGES`).
- `features/`: `ingest/service.py`(agent push) · `assessment/`(D3 채점) · `branch/`·`operation/`(생성 연산, self-run) · `agents/profiles.py`(역할).
- `monitor.py`(control-plane 집계·순수 헬퍼) · `saturation.py`(dedup/포화) · `mcp_server.py`(MCP tool, lazy) · `store/store.py`(append-only JSONL).
- `ui/`: `tui.py`(control-plane TUI) · `cli.py`(명령) · `graphlog.py`(git-graph 렌더).
- `docs/decisions/`(ADR D1–D12) · `docs/superpowers/plans/`(구현 계획들, 읽어볼 것).

## 1. ⚠️ 반드시 지킬 관례 (새 세션 필독)

- **tests/는 gitignored·로컬 전용**(CI 없음). 커밋해도 안 올라간다. `python -m unittest discover -s tests`로 실행. **worktree엔 tests/가 없으므로** puffin의 tests를 복사해오거나 새로 작성(복사: `cp -r <puffin>/tests <worktree>/tests`).
- **venv**: puffin `.venv`에 textual·mcp(2.3.0)·openai 설치됨. worktree 코드 실행은 `PYTHONPATH=<worktree>/src /Users/minahkim/orca/workspaces/inquiry/puffin/.venv/bin/python -m inquiry …`.
- **격리(중요)**: 사용자가 puffin에서 동시 작업할 수 있으므로 **puffin에서 브랜치 따지 말 것.** 반드시 **별도 git worktree**: `git worktree add /Users/minahkim/orca/workspaces/inquiry/<name> -b <branch> origin/main`. 작업 후 `git worktree remove --force`.
- **gh**: `export GH_CONFIG_DIR=/Users/minahkim/.gh-config` (없으면 ~/.config 권한 문제).
- **작업 방식(루프)**: ① 항목 **plan** 문서화 → ② **critic**(general-purpose 에이전트를 띄워 plan을 실제 코드와 대조, 차단이슈·빈틈·잘못된 가정 찾기) → ③ **TDD 구현**(red→green, 각 단계 전체 테스트 그린 유지) → ④ 커밋 → ⑤ `gh pr create` → ⑥ 머지(사용자=sole contributor, auto-merge 허용) → ⑦ worktree 정리.
- **문서는 한국어**, ADR 주도. 커밋 메시지 끝에 `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **MCP 주의**: `mcp`는 optional/lazy. mcp **2.x**는 `FastMCP`가 아니라 `from mcp.server.mcpserver import MCPServer`, Tool 속성은 `input_schema`(snake, not camelCase). 핸들러는 dep-free로 테스트, transport는 `build_server`/`serve` 분리.
- **사람-에이전트 경계**: 에이전트는 `_AGENT_EDGES` 내 제안/탐색만, 터미널 결정(refute/close/synthesize)은 사람(human:local). 이 불변식을 깨지 말 것.

---

## 2. Track A — 피벗(ADR-D12) 직접 후속

> 피벗을 끝까지 쓸모 있게. 우선순위 순.

### A1. in-TUI 결정 UX  ★ 최우선
- **목표:** 사람이 TUI 안에서 `support/contest/refute/suspend/close`를 실행(지금은 `start`만 있고, 나머지는 CLI로 나가야 함). reason·evidence 입력 흐름 포함.
- **관련:** `ui/tui.py` — `:` 명령 dispatch(현재 `start`만), `_transition`(reason/evidence 없이 호출), `#cmd` Input. `commands.py` `decide`(reason/evidence_id 인자). `cli.py`의 CLI decide는 `support/contest/refute`에 `--reason`·`--evidence` required.
- **접근:** TUI에 결정 동사 추가 → 선택 노드에 대해 `:support` 등 입력 시, reason은 `#cmd`로 받고 evidence는 그 가설에 링크된 evidence 목록에서 선택(Details에 이미 근거 표시됨). `refute/close`는 `reopen_if`도 필요. `_transition`을 동사별로 확장하고 required 인자 수집 UX(2단계 입력 or 전용 패널).
- **수용:** TUI에서 exploring+evidence 가설을 support/refute까지 완결, 상태머신 검증 통과, 실시간 반영. 사람 전용 경계 유지.
- **우선순위:** 높음(사람이 모니터 안에서 CLI 왕복 없이 결정).

### A2. MCP tool 확장
- **목표:** 에이전트가 더 많은 연산을 push — (a) **assessment push**(D3 채점 결과), (b) **agent-허용 전이**(예: contested 표시, `_AGENT_EDGES` 내).
- **관련:** `mcp_server.py`(tool 추가) · `ingest/service.py`(agent 귀속 커밋) · `assessment/`(HypothesisAssessed 이벤트) · `transitions.py`(`_AGENT_EDGES`).
- **접근:** `inquiry_assess`(축별 범위 push → HypothesisAssessed, agent actor) · `inquiry_contest`(exploring/supported→contested, agent 허용 edge). 터미널 전이는 **노출 금지**(사람 전용). dep-free 핸들러 + build_server 등록.
- **수용:** 에이전트가 MCP로 assessment·contested를 push하고 TUI/replay에 반영. 사람 전용 전이는 tool로 불가.
- **우선순위:** 중.

### A3. MCP structured_content
- **목표:** tool 반환을 구조화 출력(structured_content)으로(현재 text JSON — Claude는 읽지만 덜 깔끔). 에러도 구조화(이미 add_evidence는 error+allowed 반환 패턴 있음).
- **관련:** `mcp_server.py` — mcp 2.x `@server.tool(structured_output=...)` 또는 반환 타입 annotation으로 스키마 생성.
- **수용:** tool 결과가 structured_content로 전달. 기존 핸들러 테스트 유지.
- **우선순위:** 낮음(polish).

### A4. 외부 사용량/비용 보고 (harness→inquiry)
- **목표:** harness가 토큰/비용을 inquiry에 보고 → 모니터에 노출(피벗 모드의 spend 가시성). D6 spend cap은 self-run 한정이므로 pivot은 "모니터".
- **관련:** `mcp_server.py`(usage 보고 tool) · `monitor.py`(요약에 usage) · `tui.py`(요약 바).
- **접근:** `inquiry_report_usage(agent, input_tokens, output_tokens, ...)` tool → 이벤트로 기록 → 모니터 집계. 또는 add_* tool 호출 시 usage를 선택 인자로.
- **수용:** 에이전트가 보고한 사용량이 모니터에 집계·표시.
- **우선순위:** 중~낮.

### A5. 에이전트 inquiry 부트스트랩
- **목표:** 지금은 사람이 `init`해야 에이전트가 push 가능. 에이전트가 inquiry를 시작(또는 없으면 안내)하게.
- **관련:** `ingest/service.py`(현재 inquiry 선행 요구) · `mcp_server.py`.
- **접근:** `inquiry_init` tool(seed/question) 또는 IngestService가 inquiry 없으면 생성 옵션. 단, 공유 그래프라 "누가 부트스트랩하나" 정책 결정 필요(사람 확정 vs 에이전트).
- **우선순위:** 낮(사용자 결정 필요 — 정책).

> **M4로 합의된 것(여기 범위 아님):** 에이전트 실시간 presence/heartbeat(연결됐지만 idle인 세션). 현재는 이벤트 recency 프록시(`agent_last_seen`).

---

## 3. Track B — 원래 M3 범위 중 미완 (MILESTONES §M3)

### B1. 컬러/애니메이션 + fallback  ★
- **목표:** 컬러 상태 표현, 저속 활동 애니메이션(진짜 heartbeat 기반, §10), `--no-color`/`--no-animation`/ASCII fallback.
- **관련:** `ui/tui.py`(`STATUS_STYLE`·`LANE_COLORS` 이미 색 사용) · `ui/cli.py`(플래그) · `ui/graphlog.py`.
- **접근:** `--no-color`→Rich color 비활성(NO_COLOR 환경 또는 Console(no_color=True)), `--no-animation`→스피너/heartbeat 끔, ASCII fallback→유니코드 글리프(◉◌●◐·│╲╱) 대신 ASCII(o,*,x,|,\,/) 대체 세트. heartbeat는 §10(가짜 진행률 금지 — 진짜 활동 기반)에 유의.
- **수용:** `--no-color`로 무색, `--no-animation`으로 정적, ASCII 모드에서 깨지지 않음.
- **우선순위:** 높음(접근성·OSS Exit 기준).

### B2. NOW/NEXT/LATER
- **목표:** 시간축을 `NOW/NEXT/LATER` 중심으로 표현(§20 "프로젝트 관리 도구 과확장 금지" — 캘린더/스프린트 아님).
- **관련:** `model.py` Action(done/created_at) · `ui/`(뷰) · 가설/Action 연결.
- **접근:** Action/가설을 NOW/NEXT/LATER로 분류·표시하는 뷰(TUI 패널 또는 CLI). 분류 기준(상태·우선순위) 설계 필요.
- **수용:** NOW/NEXT/LATER로 그룹된 뷰.
- **우선순위:** 중.

### B3. research note · decision record 템플릿
- **목표:** Weekly(이미 있음)에 더해 research note·decision record **템플릿 export**.
- **관련:** `weekly.py`(build/render_markdown 패턴 재사용) · `cli.py` `write` 명령.
- **접근:** 이벤트 로그에서 research note(근거·탐색 요약)·decision record(상태 전이·결정 사유) 마크다운 생성. weekly와 동일 패턴.
- **수용:** `inquiry write research-note`·`write decision-record`가 로그 기반 마크다운 출력.
- **우선순위:** 중.

### B4. 근거 기반 가설 제안 — 잔여분
- **목표:** 리서치 커넥터는 harness가 담당(피벗으로 해결). 남은 것은 **가설 차별성 강화** — difference 필드 표시·프롬프트 개선.
- **관련:** `features/branch/`(fork candidate에 difference 필드 이미 있음) · 프롬프트.
- **접근:** 중복(D11) 플래그와 연계해 차별성 낮은 제안을 사람이 보게(상당 부분 TUI dedup 배지로 커버됨). 추가 프롬프트/표시 개선분만.
- **수용:** 차별성 정보가 제안·모니터에 드러남.
- **우선순위:** 낮(코어는 이미 커버).

### (B 제외) Git 버전관리
- MILESTONES의 "Git 버전관리"는 이미 전 과정이 git 기반(이벤트 로그·PR 워크플로)이라 사실상 충족. 추가 요구 있으면 사용자 확인.

---

## 4. 권장 순서

1. **A1 (in-TUI 결정)** — 피벗 사람 루프 완성, 체감 가장 큼.
2. **B1 (컬러/애니/fallback)** — OSS Exit 기준(§접근성), 독립적.
3. **A2 (MCP 확장: assessment·contested push)** — 에이전트 참여 강화.
4. **B3 (템플릿)** → **B2 (NOW/NEXT/LATER)** → **A4/A3/B4** (여력 순).
5. A5는 정책 결정 후.

각 항목: **별도 worktree → plan → critic → TDD → PR → 머지 → worktree 정리.** A와 B는 서로 독립이라 병렬 worktree 가능(단 같은 파일 충돌 주의 — A1·B1 둘 다 tui.py 건드리므로 순차 권장).

## 5. C (A·B 완료 후)
- 외부인 Framing 검증 2회차(사람 참가자 필요) · `mcp` 의존성 정식화(requirements) · puffin `test_mcp_and_status.py` `inputSchema→input_schema` 수정.
