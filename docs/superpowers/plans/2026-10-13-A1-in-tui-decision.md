# A1 — in-TUI 결정 UX (plan)

> 핸드오프 Track A / A1(최우선). 사람이 TUI 안에서 `support/contest/refute/suspend/continue/reopen/close`를
> CLI 왕복 없이 완결한다. 백엔드(`Commands.decide`)는 이미 완성 — TUI에 **동사 + 필수 입력 수집 UX**만 추가.

## 1. 목표 / 범위

- **목표:** `ui/tui.py`에 결정 동사를 추가하고, 동사별 필수 인자(reason·evidence·reopen_if)를
  TUI 안에서 수집해 `Commands.decide`로 커밋. 실시간 반영. 사람 전용 경계 유지.
- **범위 밖:** 에이전트 push(A2), MCP, 색/애니(B1), stale 테스트(monitor/review/mcp 11건) 정리.

## 2. 현황 (코드 근거)

- `tui.py:544` `_dispatch`는 `start`만 `_transition("start")`로 연결. 나머지 결정 동사 없음.
- `tui.py:579` `_transition(action)`은 `Commands(self.root).decide(hid, action)`을 **reason/evidence 없이** 호출.
  → `start`는 `decide`가 기본 reason을 넣어줘서 동작하지만, 나머지는 도메인 검증(`transitions.py:53`)에서 실패.
- 백엔드 `Commands.decide(target, action, *, reason='', evidence_id=None, reopen_if=None)` (`commands.py:122`)는
  refute/close의 `evidence_snapshot`을 **링크된 근거에서 자동 생성**(`commands.py:38-42`). 즉 TUI는 snapshot을 만들 필요 없음.
- 동사→상태 매핑·가드: `commands.py:27-37` (`start`=suggested→exploring, `continue`=contested전용, `reopen`=suspended/refuted/closed전용).
- **도메인 강제 vs CLI 관례 (critic 교정):** 도메인(`transitions.py:53-62`)이 강제하는 것은 **① 모든 전이에 nonempty reason**,
  **② refuted/human-closed에만 evidence_snapshot + reopen_if**. support/contest/suspend/continue/reopen의 evidence는
  **CLI argparse 관례일 뿐 도메인 비강제**. evidence 선택은 `evidence_ids`(cited)로 들어가고(`commands.py:45,128`),
  refute/close의 snapshot은 선택과 무관하게 **링크된 전체 근거에서 자동 생성**(`commands.py:40-42`).
- **TUI 정책 결정:** CLI와 UX 일관성을 위해 support/contest/refute는 TUI에서도 evidence 선택을 요구(관례), reopen은 condition-evidence.
  단 이는 **TUI 정책**이며 도메인 강제가 아님(테스트/문구에서 그렇게 오인하지 않는다). 링크된 근거가 0개면 "근거를 먼저 링크" 안내하고 중단.
- 필수 입력 매트릭스(TUI 수집 기준, `cli.py:246-256` 미러):

  | verb | reason | evidence(수집) | reopen_if | 도메인 전제 상태(`_HUMAN_TARGETS`) |
  |---|---|---|---|---|
  | start | 자동 | — | — | suggested |
  | support | 필수 | 관례 | — | exploring/contested |
  | contest | 필수 | 관례 | — | exploring/supported |
  | refute | 필수 | 관례(cited) | **도메인 필수** | exploring/contested |
  | suspend | 필수 | — | — | exploring |
  | continue | 필수 | — | — | contested |
  | reopen | 필수 | 관례(condition) | — | suspended/refuted/closed |
  | close | 필수 | — | **도메인 필수** | suggested/supported **(contested→close 불가)** |

  ※ refute/close의 reopen_if·snapshot은 도메인 필수(`transitions.py:55-62`). **contested→human-closed는 금지**(`transitions.py:9-10`) — 매트릭스에 없음, 도메인 예외로 노출.
- 선택 노드에 링크된 근거는 이미 Details에 표시됨(`tui.py:138-144`, `state.evidence_links`).
- 사람 전용 경계: `decide`가 actor를 `human:local`로 고정(`commands.py:44`) — TUI는 사람 터미널이므로 불변식 유지됨.

## 3. 접근 — 결정 입력 마법사(multi-step)

단일 `#cmd` Input을 재사용하는 **순차 입력 상태기계**. 전용 패널보다 기존 구조에 최소 침습.

### 상태
- `self._decision = None` 평소. 동사 입력 시 `{'verb','hid','need':[...필드...],'got':{}}`로 세팅.
- `need`는 verb별로 `['reason','evidence','reopen_if']`의 부분집합(위 매트릭스). 순서 고정: reason→evidence→reopen_if.

### 라우팅 (critic B3 교정)
- **라우팅 분기점은 `on_input_submitted`(tui.py:524)** — `_dispatch`가 아님. 현재 이 핸들러는 Enter마다
  `#map`으로 focus를 **무조건** 빼앗고 입력을 비운 뒤 `_dispatch`. 수정: `self._decision is not None`이면
  `_decision_step(text)`로 보내고 **focus를 `#cmd`에 유지**(steal 조건부). 아니면 기존대로.

### 흐름
1. `_dispatch`에서 verb가 결정 동사면 `_begin_decision(verb)` 호출(첫 진입은 map-focus 상태에서 `:verb` 입력 → 기존 경로 OK).
   - hid 유효성(ROOT/None 거부) 검사. 전제 상태 불일치는 **선검사하지 않고** `decide` 예외를 상태줄에 노출(단일 진실원천=도메인).
     evidence를 수집하는 verb인데 **링크된 근거가 0개**면 즉시 안내하고 중단(TUI 정책).
2. `need`가 비어 있으면 바로 `decide` 커밋(예: 미래 확장). start는 기존 `_transition("start")` 경로 유지(중복 최소화).
3. 비어 있지 않으면 첫 필드 프롬프트를 상태줄에 띄우고 `#cmd` 포커스. 이후 Enter 입력은
   `on_input_submitted`가 `self._decision`이 있으면 `_decision_step(value)`로 라우팅(위 B3).
4. 각 스텝(`_decision_step`은 `/cancel`·`cancel` 토큰을 직접 인식 — 라우팅이 `_dispatch`를 건너뛰므로):
   - `reason`: 빈 문자열이면 재요청. 아니면 저장.
   - `evidence`: 링크된 근거를 번호 목록으로 상태줄/Details에 제시 → 사용자가 번호 입력 → `evidence_id` 저장.
     (support/contest/refute = 긍정/도전 근거 모두 선택 가능; reopen = condition-evidence.)
   - `reopen_if`: 빈 문자열이면 재요청. 아니면 저장.
   - 마지막 필드 후 `Commands.decide(hid, verb, reason=, evidence_id=, reopen_if=)` 호출.
5. 성공: `_reload_state`+`_rebuild_table`+상태줄 `{hid} → {verb} 적용`. 실패: 예외를 상태줄에 노출하고 `_decision=None`.
6. 취소: 빈 입력이 아닌 `/cancel`(또는 Esc)로 마법사 중단 → `_decision=None`, 상태줄 안내.

### Esc 처리
- `action_cancel_op`(Esc)에 결정 마법사 취소 분기 추가(연산 워커 취소보다 우선). `_paused()`도 마법사 중 폴링 멈춤에 포함.

### `_transition` 통합
- 기존 `_transition("start")`는 그대로 둠(start는 need가 비어 바로 커밋되는 특수 케이스로 `_begin_decision`에 흡수하거나,
  현행 유지). → **현행 `start` 경로 유지**하고 신규 동사만 마법사로. (중복 최소화: `_begin_decision`가 need 없으면 `decide` 직접 호출, start는 기존 `_transition` 재사용 가능 — 구현 시 택1, 테스트로 고정.)

## 4. 수용 기준 (TDD 대상)

`tests/test_tui_actions.py`에 추가(`run_test` pilot 패턴):

**스텝 주입은 `_dispatch`가 아니라 `#cmd` 제출 경로로**(critic N2/B3). 테스트 헬퍼 `_submit(app, text)`가
`Input.Submitted(cmd, text)`를 `on_input_submitted`에 전달. 첫 동사 진입만 `_dispatch` 직접 호출 허용(현행 패턴).

1. **support 완결:** suggested→start→exploring + 근거 링크 후, `support`→reason→evidence(번호)로 `supported`. `Commands.state()` 영속 확인, cited `evidence_ids`에 선택 반영.
2. **refute 완결(reason→evidence→reopen_if):** `refuted` + evidence_snapshot 자동 생성(링크 전체) 확인(replay). reopen_if 저장 확인.
3. **close(reason→reopen_if, evidence 수집 없음):** supported에서 `human-closed`.
4. **evidence 0개인데 support:** "근거를 먼저 링크" 안내, 상태 불변(**TUI 정책**이지 도메인 강제 아님을 주석에 명시).
5. **전제 위반:** suggested에 `support`(start 안 함) → 도메인 예외 상태줄 노출, 상태 불변.
6. **취소:** 마법사 중 `cancel` 입력 또는 Esc → `_decision=None`, 상태 불변.
7. **ROOT 거부:** ROOT 선택 시 결정 동사 거부.
8. **회귀:** `_paused()`가 `_decision` 중 True; 마법사 중 폴링 비반영.

전체 스위트 그린 유지(기존 pre-existing 11 red 제외 — monitor_dashboard·review_gate·mcp inputSchema).

## 5. 작업 순서(TDD)

1. red: 수용1(support happy path) 테스트 작성 → 실패 확인.
2. green: `_begin_decision`/`_decision_step`/라우팅/상태 추가 → 통과.
3. red→green 반복으로 수용2~7.
4. HELP 문자열·LEGEND에 결정 동사 추가, `_set_status` 프롬프트 문구.
5. 전체 스위트 실행(기존 11 red만 남는지 확인), 커밋, PR.

## 6. 위험/주의

- `tui.py`는 B1도 건드림 → 핸드오프 §4대로 A1 먼저 순차.
- 마법사 중 외부 push 폴링과 충돌 → `_paused()`에 포함해 방지.
- evidence 번호 입력 파싱: 링크 목록 인덱스 범위 밖/비숫자 → 재요청.
- `continue`/`reopen` 동사도 매트릭스에 포함하되, 최소 수용 테스트는 support/refute/close 중심(나머지는 동일 경로라 회귀테스트 1개씩).
