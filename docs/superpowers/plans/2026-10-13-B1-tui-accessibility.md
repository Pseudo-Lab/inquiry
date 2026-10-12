# B1 — TUI 컬러/애니메이션 + ASCII fallback (plan)

> 핸드오프 Track B / B1(★, OSS Exit 접근성 기준). `--no-color`·`--no-animation`·`--ascii` 지원.
> 기존 유니코드 글리프·Rich 색·스피너를 끄거나 ASCII로 대체해도 **깨지지 않게**.

## 1. 목표 / 범위
- **목표:** `inquiry tui`에 세 플래그 추가 → 무색/정적/ASCII 모드. 환경변수 `NO_COLOR`도 존중.
- **범위 밖:** 진짜 heartbeat 애니(§10, M4로 이연 — 현재 "애니"는 모델 연산 중 스피너뿐, 가짜 진행률 아님). B2 NOW/NEXT/LATER.

## 2. 현황 (코드 근거)
- 유니코드 글리프: `STATUS`(◌◉●◐∙×◆⊘, tui.py:52), GRAPH 노드 `*`/`◆`/마크 `•`(`_node_cell`), 엣지 `│╲╱`(graphlog `graph_rows` cells).
- 색: `STATUS_STYLE`·`LANE_COLORS`(Rich 스타일 문자열), 선택행 `on grey30`, 타이틀 부가색(agent/dup/pending), CSS 테마색($accent 등).
- 스피너: `SPINNER`(braille) + `set_interval(0.1, _tick_spinner)` — **모델 연산 실행 중에만**(real work, 가짜 아님).
- `_detail_text`(모듈 함수, tui.py:121)도 `STATUS` 글리프 사용.
- CLI: `tui` 파서(cli.py:144) → `run_tui(root, op_factories, follow)`(tui.py:912) → `InquiryTUI.__init__`.

## 3. 접근
플래그 3개를 `InquiryTUI`/`run_tui`/CLI로 관통. 글리프·스타일을 **모드 의존 헬퍼**로 라우팅.

### 3.1 글리프 세트 (ascii)
- 모듈 상수 `STATUS_ASCII`(동일 키, ASCII 기호: suggested=o, exploring=O, supported=*, contested=%, suspended=-, refuted=x, synthesized=#, human-closed=X).
- **문자열 변환기 `self._tr(s)`**(critic B2/G3): ascii_mode면 맵 `{'│':'|','╲':'\\','╱':'/','◆':'#','•':'+','⚠':'!','◀':'<','⟶':'->'}`의 모든 키를 치환, 아니면 원본.
  → `◆`(merge)·`•`(marked)는 cells가 아니라 `_node_cell` **직접 append**(tui.py:434,438)이므로 반드시 `self._tr(glyph)`/`self._tr('•')`로.
  → 엣지 cells(`│╲╱`)는 `_node_cell`/`_edge_cell` char 루프에서 `self._tr(ch)`. 노드 `*`는 유지.
  → 타이틀 주석 `⚠dup`(tui.py:419)·`◀{pending}`(422)·Details의 `⚠`/`⟶`(488,491)도 `self._tr`.
- `self._glyphs`(STATUS 또는 STATUS_ASCII).
- `_detail_text(h, state, glyphs=STATUS, tr=lambda s: s)`에 glyphs·tr 인자 추가 → `_detail`에서 `self._glyphs`·`self._tr` 전달(유일 호출처, tui.py:477).
- 스피너: `SPINNER_ASCII = "|/-\\"`, `self._spinner`로 선택.

### 3.2 색 (no_color)
- `self._st(style)` → `"" if self.no_color else style`. 모든 **컨텐츠** Rich 스타일을 경유
  (`_build_table` status_cell style(=`Text(..., style=self._st(...))`)·title 부가색 append·선택행 `add_row(style=self._st("on grey30"))`,
  `_node_cell`/`_edge_cell` lane color, 스피너 색 assemble, LEGEND). **Table chrome kwargs**(border_style/header_style/title_style/caption_style, tui.py:373-376)도 `self._st`로(critic N3).
- **테스트 접근 교정(critic B1):** status_cell은 생성자 style이라 `.spans`가 아닌 `.style`에 들어감 → no_color 검증은
  **`self._st()` 헬퍼 단위테스트**(returns "")와 ascii 렌더 검사로 한다. `.spans==[]` 단독 검증 금지.
- CSS 크롬색은 `on_mount`에서 `self.theme = "ansi-dark"`(터미널 자체 팔레트). **정직히:** border/header/#cmd 등 크롬은
  색터미널에서 ANSI색 유지됨 — "컨텐츠 모노, 크롬 ANSI"가 이 PR의 범위(critic G4 동의). NO_COLOR 터미널에선 Textual이 자동 strip.
- `no_color` 기본값 = CLI `--no-color` 또는 `os.environ.get("NO_COLOR")`. 순수 헬퍼 `resolve_no_color(flag, env)`로 분리해 단위테스트.

### 3.3 애니메이션 (no_animation)
- `_start_spinner`: `no_animation`이면 타이머 생성 없이 정적 라벨 1회만 표시, `_tick_spinner`/`set_interval` 생략.
- `_stop_spinner`은 타이머 None 안전(현행 유지).

### 3.4 CLI 배선
- `tui` 파서에 `--no-color`·`--no-animation`·`--ascii`(`action='store_true'`).
- `run_tui(root, op_factories, follow, *, no_color=False, no_animation=False, ascii_mode=False)`;
  **호출 2곳 모두**(cli.py:387 read-only, 396 op_factories, critic G1) kwargs 전달. no_color는 `resolve_no_color(args.no_color)`로.

## 4. 수용 기준 (TDD, tests/test_tui_actions.py 또는 신규 test_tui_accessibility.py)
1. **ascii 글리프:** `ascii_mode=True`면 렌더된 표/Details에 유니코드 글리프(◉●◆ 등) 대신 ASCII(O,*,# 등). 엣지 `|\/`.
2. **no_color 컨텐츠 무색:** status_cell/타이틀 Text에 스타일 span 없음(`Text.spans == []` 또는 style 미적용). 테마=ansi-dark.
3. **no_animation 정적:** 모델 연산 스피너가 타이머를 만들지 않음(`_spin_timer is None`), 상태줄에 라벨은 표시.
4. **NO_COLOR 환경:** `--no-color` 없이도 env `NO_COLOR=1`이면 CLI가 no_color=True로 전달(cli 레벨 단위테스트 or run_tui 인자 계산).
5. **회귀:** 기본(플래그 없음)은 기존 유니코드·색·애니 동작 그대로. 기존 TUI 테스트 전부 그린.
6. **ascii 모드에서 깨지지 않음:** ascii+no_color 동시에도 렌더 예외 없음(run_test 스모크).

## 5. 작업 순서(TDD)
1. red: ascii 글리프 테스트 → 실패.
2. green: 글리프 세트·헬퍼·배선.
3. no_color·no_animation·env 테스트 red→green.
4. 전체 스위트(기존 pre-existing 11 red만 남는지), 커밋, PR, 머지, 정리.

## 6. 위험/주의
- `no_color` 테스트: Textual 컨텐츠는 우리가 만든 Rich Text라 `.spans` 검사로 무색 확인 가능. CSS 테마색은 터미널 위임(ansi)로 처리 — 완전 모노 보장은 터미널 책임(§접근성 취지 충족).
- ascii 치환은 **표시 레이어에서만** — graphlog 로직/cells 자체는 유니코드 유지(로직 불변), 렌더 시 `self._edge`로 치환.
- A1에서 추가된 결정 마법사 상태줄/글리프와 충돌 없음(스타일 헬퍼만 경유).
