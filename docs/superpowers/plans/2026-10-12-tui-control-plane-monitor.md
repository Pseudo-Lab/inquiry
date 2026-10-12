# TUI Control-Plane Monitor — git-graph TUI를 모니터로 통합

> 피벗(ADR-D12) 모니터링을 **기존 git-graph TUI(`inquiry tui`)로 통합**한다. TUI는 평문 `monitor`의 상위집합(전부 + 드릴다운·그래프·결정)이므로 **사람용 평문 `monitor`는 제거**하고, TUI를 사람용 단일 모니터로 둔다. 기계/orca용 **`status`·`review`는 JSON만** 남긴다.

**격리:** 이 작업은 **별도 worktree `/Users/minahkim/orca/workspaces/inquiry/tui-monitor`**(브랜치 `feat/tui-control-plane`, origin/main 기반)에서 진행한다. puffin 워크트리(`fix/inquiry-add-evidence`)와 충돌 없음.

**Status:** 2026-10-12 설계 → critic 1회차 CHANGES NEEDED → 데이터출처 정정·결정 descope·상태줄 분리·read-only 반영해 개정(2026-10-13). 미착수.

**critic 반영 요지:**
- **데이터 출처:** `assessment`·near-duplicate = **state**(events 불필요). **saturation·제안 agent 귀속 = events 필요**. `_reload_state`에 `Store.read_all()` 추가 로드.
- **결정 descope(사용자 확정):** 현재 TUI엔 `start`만 있고 support/contest/refute/suspend/close 동사가 **없다**. 이번 슬라이스는 **단서만**(결정 대기 배지 + `n` 점프), 실제 결정은 **CLI**(`inquiry support …`). in-TUI 결정 UX는 후속.
- **상태줄:** `#status`는 스피너/피드백 전용 유지 → control-plane 요약은 **신규 위젯**(`#summary`).
- **read-only:** 현 `tui`는 항상 op_factories 주입 → `--read-only` 플래그로 순수 모니터 진입(openai는 lazy라 미설정이어도 TUI는 뜸).

## 문제 / 배경

피벗 모니터링을 Phase 2에서 **평문 텍스트 대시보드**(`monitor.render_text`)로 만들었는데, 사용자가 이미 만든 **git-graph TUI**(`inquiry tui`: `graphlog` 지도 + ↑/↓ 선택 + Details 패널 + `:` 결정 명령)와 별개다. 사용자 기대 = "그래프 보면서 ↑/↓로 상세 확인 + 실시간". 기존 TUI가 그 토대를 이미 갖췄으므로 **확장**이 맞다.

**기존 TUI 자산(재사용):**
- `InquiryTUI(App)` + `GraphView`(focusable, ↑/↓·k/j → `_move_selection`) + `#details`/`#status`/`#cmd`.
- `graphlog.graph_rows` git-log 지도, `_order` 정렬, ROOT/`_Proxy` 가상 루트.
- `_detail_text(h, state)` — 상태·주장·부모·전제·반증조건·사유·**근거**·Actions.
- `_reload_state()` = `Commands(root).state()` 재로드(연산 후 호출). `:` 명령으로 결정/연산.

**빠진 것(= 이번 작업):** 에이전트 귀속 표시 · **외부 push 실시간 반영** · control-plane 상세(제안 agent·assessment·중복/포화) · 사람 게이트 시각 단서.

## 선행 결정 (사용자 확정 2026-10-13)
- **기존 `InquiryTUI` 확장**(새 TUI 안 만듦). graphlog·선택·Details 재사용.
- **평문 `monitor` 제거 → TUI가 사람용 단일 모니터.** TUI가 상위집합이라 평문 텍스트 뷰는 중복. `monitor` CLI 명령 + `monitor.render_text`/`render_review`(사람용 텍스트 렌더러) 삭제.
- **`status`·`review`는 JSON만 유지**(기계/orca/자동화용). 순수 집계 함수 `monitor.summary`/`review`/`compute_saturation`/`find_near_duplicates`는 **유지**(TUI·JSON 둘 다 사용).
- **실시간 갱신 기본 ON:** Textual `set_interval`로 `Store.signature()` 폴링(의존성 없음, Phase 1 재사용) → 변경 시 `_reload_state()` + 재렌더. 명령 입력/연산 대기 중엔 폴링 일시중지(조작 방해 금지).
- **선택 안정성:** 리로드 시 인덱스가 아니라 **가설 id 기준**으로 선택 복원(외부 push로 노드가 추가돼도 보던 노드 유지).
- **읽기 전용 안전:** 갱신은 lock-free read(기존 `read_all`). 쓰기 없음.

## 파일과 책임 (worktree 내 상대경로)
| 파일 | 책임 |
|---|---|
| 새 `ui/tui_monitor.py` 또는 `monitor.py` 확장 | 순수 헬퍼: `creators(events)`(hyp→제안 agent), control-plane detail 보강, status 요약. **TUI와 분리해 테스트 가능하게** |
| 수정 `ui/tui.py` | (1) 실시간 폴링 타이머 + 선택 id 보존 리로드, (2) Details에 제안 agent·assessment·중복 피어·"결정 대기" 추가, (3) 상태줄에 control-plane 요약, (4) 그래프 행에 agent/중복 표식(경량), (5) 사람 게이트: review-그룹 노드 하이라이트 + 다음 대기 노드로 이동 키 |
| 수정 `ui/cli.py` | `tui`에 `--read-only`(op_factories 없이 순수 모니터)·`--no-follow`. **`monitor` 명령 제거**, `status`·`review`는 **JSON만**(review `--json` 기본화, 텍스트 경로 삭제). 삭제 전 `tests/`에서 `render_text`/`render_review`/`monitor` 소비처 grep 전수 확인 |
| 수정 `monitor.py` | 순수 집계(`summary`·`review`·`_creators`) **유지**. 사람용 텍스트 렌더러 `render_text`·`render_review` **삭제** |

## Tasks
1. **귀속·상세 헬퍼(순수)** — `_creators(events)`(hyp→제안 agent) + control-plane detail/status 요약 빌더. **데이터 출처 명시:** 제안 agent·saturation = **events**, assessment·near-dup = **state**. 단위 테스트.
2. **`_reload_state` 확장 + Details/요약 통합** — `_reload_state`에 `self.events = Store(root).read_all()` 추가(현재 `Commands().state()`만), `self._creators`·saturation 캐시. **최적화(선택):** `replay(self.events)`로 state를 직접 만들어 replay 1회로 합침. `_detail_text`에 제안 agent·assessment 범위(`h.assessment.*.low/high`)·near-dup 피어·"결정 대기" 추가. control-plane 요약은 **`#status`가 아닌 신규 `#summary` 위젯**(스피너/피드백과 충돌 방지).
3. **실시간 갱신** — `set_interval`→ **분리된 `_poll()` 메서드**(pilot 테스트가 수동 호출 가능)에서 signature 변경 시 리로드·재렌더. **폴링 가드**: `self.pending` / `self._op_worker`(미완) / `#cmd` 포커스 중이면 skip. 리로드는 **`self._current_hid` 저장→`_find`로 복원**(기존 tui.py:413-483 재사용), 사라졌으면 인덱스 clamp. `--no-follow`로 끔.
4. **사람 게이트 단서(결정은 CLI)** — `monitor.review` 그룹(triage/decide/resolve) 노드에 시각 배지 + "다음 대기 노드" 이동 키(`n`). **실제 결정은 CLI**(`inquiry support/refute …`) — in-TUI 결정 동사 추가는 범위 밖(현재 TUI엔 `start`만 존재).
5. **그래프 행 표식(경량)** — 노드 행에 제안 agent 약칭/중복 ⚠. 과하지 않게.
6. **CLI 배선 + 평문 monitor 제거** — `tui --read-only/--no-follow`. `monitor` 명령·`render_text`·`render_review` 삭제, `status`·`review` JSON만. 소비처 grep 후 테스트 정리.

## 검증 전략
- **순수 헬퍼는 unittest**(`_creators`·detail builder·요약·선택 id 복원·폴링 가드 판정).
- **TUI 상호작용은 Textual `App.run_test()`(pilot)**: 키(↑/↓/n)·`_poll()` **수동 호출**로 "signature 변경→리로드→선택 보존"을 결정론적으로 검증(타이머 타이밍 의존 금지).
- 테스트는 프로젝트 관례상 `tests/` 로컬 비추적.

## 리스크 / 주의
- **Textual 테스트 난이도** → 로직을 순수 헬퍼로 최대한 빼고, pilot은 핵심 상호작용만.
- **조작 방해 금지** → 폴링은 명령 입력/연산 대기 중 중지. 갱신이 사용자의 선택/스크롤을 튕기지 않게(id 기준 복원 + follow-scroll 유지).
- **선택 id 보존** → 외부 push로 노드 순서/수 변동 시에도 보던 가설 유지, 사라졌으면 근처로.
- **worktree venv** → tui-monitor에 textual·mcp 필요. puffin `.venv`를 `PYTHONPATH=<worktree>/src`로 재사용하거나 전용 venv. (구현 착수 시 확정)

## 범위 밖 (후속)
- **in-TUI 결정 UX** — support/contest/refute/suspend/close 동사 + reason·evidence 입력 흐름(현재 TUI엔 `start`만). 이번엔 단서만, 결정은 CLI.
- TUI 안에서 에이전트에게 지시(역방향: 사람→에이전트).
- 리치 멀티패널(evidence 전용 창 등) — Details 확장으로 시작.
- true inotify 기반 push(현재 signature 폴링).
