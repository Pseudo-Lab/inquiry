"""M2-6 TUI: Git-log 지도 + 키보드 ↑/↓ 선택 → Details, 명령 입력 → 연산.

Textual 기반(ADR-D7 Gate B 항목4 선정).
- 읽기: 저장된 inquiry를 compact 표로, 하이라이트 가설 상세를 Details에.
- 쓰기: 하단 명령으로 start(상태전이)·deepen/challenge(모델 연산)를 실행.
  모델 연산은 취소 가능한 thread 워커로 돌리고(협조적 cancelled), 결과는
  사람이 accept/reject로 확정한다(ADR-D5 human-approval).
"""
from rich import box
from rich.cells import cell_len
from rich.table import Table
from rich.text import Text
from textual import work
from textual.worker import get_current_worker
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Footer, Header, Input, Static

from .commands import Commands
from .graphlog import lane_rows
from .operations import OperationsService

SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"   # 모델 연산 실행 중 애니메이션 프레임


def _pad(text, width):
    """CJK 폭(cell_len) 기준 패딩/절단 — 한글 열 정렬."""
    out = ""
    for ch in text:
        if cell_len(out + ch) > width:
            break
        out += ch
    return out + " " * (width - cell_len(out))

# STATUS 열 기호 — scale.py(m1b)와 동일 세트. GRAPH 열 노드 점은 '*'로 통일.
STATUS = {
    'suggested': ('◌', 'Suggested'),
    'exploring': ('◉', 'Exploring'),
    'supported': ('●', 'Supported'),
    'contested': ('◐', 'Contested'),
    'suspended': ('∙', 'Suspended'),
    'refuted': ('×', 'Refuted'),
    'synthesized': ('◆', 'Synthesized'),
    'human-closed': ('⊘', 'Closed'),
}
STATUS_STYLE = {
    'suggested': 'grey62',
    'exploring': 'bright_cyan',
    'supported': 'bold green',
    'contested': 'yellow',
    'suspended': 'grey62',
    'refuted': 'bold red',
    'synthesized': 'bold magenta',
    'human-closed': 'grey50',
}
# GRAPH 열 레인(브랜치)별 색 — 분기되면 머지 전까지 레인마다 다른 색.
LANE_COLORS = ("bright_white", "bright_cyan", "bright_magenta", "bright_green",
               "bright_yellow", "bright_blue", "bright_red", "orange1")
MODEL_OPS = ('deepen', 'challenge')
LEGEND = "  ".join(f"{sym} {label}" for sym, label in STATUS.values())
HELP = ("명령: start · deepen · challenge · fork · mark · synthesize · "
        "accept · reject · cancel · find <ID> · legend · quit")


def _order(state):
    """표시 순서: 루트에서 DFS로 부모 바로 아래 자식을 모은다(계보 그룹화).

    생성 순서는 부모·자식이 흩어져 레인이 지저분하고 대각선이 안 그려진다.
    DFS 토폴로지(부모가 모두 그려진 뒤에만 자식을 그림)로 바꾸면 fork가 부모
    바로 밑에 붙어 ╲/╱ 커넥터가 깔끔하게 나온다.
    """
    nodes = state.hypotheses
    ids = list(nodes)  # 생성 순서(루트·형제 순서 보존)
    children = {i: [] for i in ids}
    remaining = {}
    for i in ids:
        parents = [p for p in nodes[i].parent_ids if p in nodes]
        remaining[i] = len(parents)
        for p in parents:
            children[p].append(i)
    order, emitted = [], set()

    def emit(i):
        order.append(i)
        emitted.add(i)
        for c in children[i]:
            remaining[c] -= 1
        for c in children[i]:
            if remaining[c] == 0 and c not in emitted:
                emit(c)

    for i in ids:
        if remaining[i] == 0 and i not in emitted:
            emit(i)
    for i in ids:  # 안전망(순환 등 예외)
        if i not in emitted:
            order.append(i)
    return [nodes[i] for i in order]


def _detail_text(h, state):
    sym, label = STATUS.get(h.status, ('?', h.status))
    lines = [f"[b]{h.id}[/b]  {sym} {label}", "", f"[b]주장[/b] {h.claim}"]
    if h.parent_ids:
        lines.append(f"[b]부모[/b] {', '.join(h.parent_ids)}")
    if h.synthesis_target:
        lines.append(f"[b]통합 대상[/b] {h.synthesis_target}")
    if h.assumptions:
        lines.append("[b]전제[/b]")
        lines += [f"  · {a}" for a in h.assumptions]
    if h.falsified_if:
        lines.append("[b]반증 조건[/b]")
        lines += [f"  · {f}" for f in h.falsified_if]
    if h.reason:
        lines.append(f"[b]사유[/b] {h.reason}")
    if h.reopen_if:
        lines.append(f"[b]재개 조건[/b] {h.reopen_if}")
    linked = [l for l in state.evidence_links if l.hypothesis_id == h.id]
    if linked:
        lines.append("[b]근거[/b]")
        for l in linked:
            ev = state.evidence.get(l.evidence_id)
            if ev:
                lines.append(f"  · [{l.relation}] {ev.type}: {ev.content[:80]}")
    return "\n".join(lines)


class GraphView(Static):
    """포커스 가능한 git-log 지도 — Rich Table을 렌더하고 ↑/↓(k/j)로 선택 이동."""
    can_focus = True
    BINDINGS = [
        Binding("up,k", "move(-1)", "위", show=False),
        Binding("down,j", "move(1)", "아래", show=False),
    ]

    def action_move(self, delta: int):
        self.app._move_selection(delta)


class InquiryTUI(App):
    CSS = """
    Screen { background: $surface; }
    #mapwrap { height: 1fr; background: $panel; }
    #map { padding: 0; background: $panel; }
    #details {
        height: auto; max-height: 42%;
        border: round $primary;
        border-title-color: $accent;
        border-title-style: bold;
        padding: 0 1;
        background: $panel;
    }
    #status { height: 1; color: $text-muted; padding: 0 1; }
    #cmd { dock: bottom; border: tall $accent; }
    """
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("colon", "focus_cmd", "명령", key_display=":"),
        Binding("escape", "cancel_op", "취소"),
    ]

    def __init__(self, root, op_factories=None):
        super().__init__()
        self.root = root
        # op_factories: {operation: adapter_factory()->(adapter, model)}. None → 실행 불가(읽기).
        self.op_factories = op_factories or {}
        self.pending = None            # 사람 승인 대기 중인 proposal
        self.pending_kind = None       # 'op' | 'branch'
        self.marked = set()            # synthesize 대상으로 표시한 가설 ID
        self.sel = 0                   # 선택된 노드 인덱스
        self._op_worker = None
        self._spin_timer = None        # 연산 중 스피너 타이머
        self._spin_i = 0
        self._spin_label = ""
        self._reload_state()

    def _reload_state(self):
        self.state = Commands(self.root).state()
        self.nodes = _order(self.state)

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            with VerticalScroll(id="mapwrap"):
                yield GraphView(id="map")
            yield Static("", id="details")
        yield Static(HELP, id="status")
        yield Input(placeholder="명령 (: 로 포커스)", id="cmd")
        yield Footer()

    def on_mount(self):
        frame = (self.state.inquiry.frame if self.state.inquiry else {}) or {}
        self.title = "Inquiry"
        self.sub_title = frame.get("central_question") or (
            self.state.inquiry.seed if self.state.inquiry else "(빈 탐구)")
        self.query_one("#details").border_title = "Details"
        self._rebuild_table(select=0)
        self.query_one("#map", GraphView).focus()

    def _connector_info(self):
        """hid → ('fork'|'merge'|None, parents): 대각선 커넥터용."""
        all_ids = {n.id for n in self.nodes}
        childmap = {}
        for n in self.nodes:
            for p in n.parent_ids:
                if p in all_ids:
                    childmap.setdefault(p, []).append(n.id)
        info = {}
        for n in self.nodes:
            parents = [p for p in n.parent_ids if p in all_ids]
            if len(parents) >= 2:
                info[n.id] = ('merge', parents)
            elif len(parents) == 1 and childmap.get(parents[0], [None])[0] != n.id:
                info[n.id] = ('fork', parents)
            else:
                info[n.id] = (None, parents)
        return info

    def _rebuild_table(self, select=None):
        if select is not None:
            self.sel = select
        gv = self.query_one("#map", GraphView)
        if not self.nodes:
            gv.update(Text("이 탐구에는 아직 가설이 없습니다. framing으로 프레임을 승인하세요.",
                           style="grey62"))
            self.query_one("#details", Static).update("아직 가설이 없습니다.")
            return
        self.sel = max(0, min(self.sel, len(self.nodes) - 1))
        gv.update(self._build_table())
        self._show(self.nodes[self.sel].id)

    def _build_table(self):
        t = Table(box=box.ROUNDED, expand=True, pad_edge=False, padding=(0, 1),
                  border_style="grey42", header_style="bold bright_cyan",
                  title="Branch log", title_justify="left", title_style="bold cyan",
                  caption=f"{len(self.nodes)} nodes", caption_justify="right",
                  caption_style="grey50")
        t.add_column("GRAPH", no_wrap=True)
        t.add_column("ID", no_wrap=True, style="grey74")
        t.add_column("HYPOTHESIS", ratio=1)
        t.add_column("STATUS", no_wrap=True)
        lanes = lane_rows(self.nodes)
        conn = self._connector_info()
        for idx, h in enumerate(self.nodes):
            cells, col = lanes[idx]
            kind, parents = conn[h.id]
            sym, label = STATUS.get(h.status, ('?', h.status))
            sstyle = STATUS_STYLE.get(h.status, 'white')
            marked = h.id in self.marked
            # GRAPH 열: 분기선(│╲╱)·노드(*)·머지(◆)만, 레인별 색. 상태 기호 없음.
            if kind == 'fork':
                t.add_row(self._graph_cell(cells, col, '╲', marked),
                          "", Text("Fork", style="grey50"), "")
            elif kind == 'merge':
                t.add_row(self._graph_cell(cells, col, '╱', marked),
                          "", Text("Merge / " + " + ".join(parents), style="grey50"), "")
            node_glyph = '◆' if kind == 'merge' else '*'
            selected = (idx == self.sel)
            t.add_row(self._graph_cell(cells, col, node_glyph, marked),
                      Text(h.id), Text(("▸ " if selected else "  ") + h.title),
                      Text(f"{sym} {label}", style=sstyle),   # 상태 기호·색은 STATUS 열에만
                      style=("on grey30" if selected else None))
        return t

    def _graph_cell(self, cells, col, glyph, marked=False):
        """레인별 색으로 분기선·노드를 그린다(브랜치마다 머지 전까지 다른 색)."""
        c = Text()
        if marked:
            c.append("•", style="bold yellow")
        for i, ch in enumerate(cells):
            color = LANE_COLORS[i % len(LANE_COLORS)]
            if i == col:
                c.append(glyph, style=f"bold {color}")
            elif ch in ('@', ' '):
                c.append(' ')
            else:
                c.append('│', style=color)
            c.append(' ')
        return c

    def _move_selection(self, delta):
        if not self.nodes:
            return
        self.sel = max(0, min(self.sel + delta, len(self.nodes) - 1))
        self._rebuild_table()

    def _show(self, hid):
        h = self.state.hypotheses.get(hid)
        if h is not None:
            self.query_one("#details", Static).update(_detail_text(h, self.state))

    def _set_status(self, text):
        self.query_one("#status", Static).update(text)

    # --- 연산 중 스피너 애니메이션 ---
    def _start_spinner(self, label):
        self._spin_label = label
        self._spin_i = 0
        if self._spin_timer is None:
            self._spin_timer = self.set_interval(0.1, self._tick_spinner)
        self._tick_spinner()

    def _tick_spinner(self):
        frame = SPINNER[self._spin_i % len(SPINNER)]
        self._spin_i += 1
        self.query_one("#status", Static).update(
            Text.assemble((f"{frame} ", "bold cyan"), (f"{self._spin_label} ", ""),
                          ("(cancel/Esc로 취소)", "grey50")))

    def _stop_spinner(self):
        if self._spin_timer is not None:
            self._spin_timer.stop()
            self._spin_timer = None

    @property
    def _current_hid(self):
        if self.nodes and 0 <= self.sel < len(self.nodes):
            return self.nodes[self.sel].id
        return None

    # --- commands ---
    def action_focus_cmd(self):
        self.query_one("#cmd", Input).focus()

    def action_cancel_op(self):
        if self._op_worker is not None and not self._op_worker.is_finished:
            self._op_worker.cancel()
            self._set_status("연산 취소 요청됨…")
        else:
            self.query_one("#map", GraphView).focus()

    def on_input_submitted(self, event: Input.Submitted):
        text = event.value.strip()
        event.input.value = ""
        self.query_one("#map", GraphView).focus()
        if text:
            self._dispatch(text)

    def _dispatch(self, text):
        verb, _, rest = text.partition(" ")
        verb, rest = verb.lower(), rest.strip()
        if verb == "quit":
            self.exit()
        elif verb in MODEL_OPS:
            self._start_op(verb)
        elif verb == "fork":
            self._start_fork()
        elif verb == "mark":
            self._toggle_mark()
        elif verb == "synthesize":
            self._start_synth()
        elif verb == "start":
            self._transition("start")
        elif verb == "accept":
            self._accept(rest)
        elif verb == "reject":
            self._reject()
        elif verb == "cancel":
            self.action_cancel_op()
        elif verb == "find":
            self._find(rest)
        elif verb == "legend":
            self._set_status(LEGEND)
        else:
            self._set_status(f"알 수 없는 명령: {verb}. {HELP}")

    def _find(self, query):
        q = query.strip().lower()
        if not q:
            self._set_status("find <ID> 형식으로 입력하세요.")
            return
        match = next((i for i, h in enumerate(self.nodes) if h.id.lower() == q), None)
        if match is None:
            match = next((i for i, h in enumerate(self.nodes)
                          if h.id.lower().startswith(q)), None)
        if match is None:
            self._set_status(f"'{query}' 노드를 찾을 수 없습니다.")
            return
        self.sel = match
        self._rebuild_table()
        self._set_status(f"{self.nodes[match].id} (행 {match + 1}/{len(self.nodes)})")

    def _transition(self, action):
        hid = self._current_hid
        if hid is None:
            return
        try:
            Commands(self.root).decide(hid, action)
        except Exception as e:  # noqa: BLE001 — surface to status line
            self._set_status(f"{action} 실패: {e}")
            return
        self._reload_state()
        self._rebuild_table()
        self._set_status(f"{hid} → {action} 적용")

    def _start_op(self, operation):
        hid = self._current_hid
        if hid is None:
            return
        if self._op_worker is not None and not self._op_worker.is_finished:
            self._set_status("다른 연산이 실행 중입니다. cancel 후 다시 시도하세요.")
            return
        factory = self.op_factories.get(operation)
        if factory is None:
            self._set_status(f"{operation} 어댑터가 설정되지 않았습니다(읽기 전용).")
            return
        self._start_spinner(f"{operation} 실행 중")
        self._op_worker = self._run_op(operation, hid, factory)

    @work(thread=True, exclusive=True, group="op")
    def _run_op(self, operation, hid, factory):
        worker = get_current_worker()
        try:
            proposal = OperationsService(self.root).propose(
                operation, [hid], adapter_factory=factory,
                cancelled=lambda: worker.is_cancelled)
        except BaseException as e:  # noqa: BLE001
            msg = "취소됨" if worker.is_cancelled else f"{operation} 실패: {e}"
            self.call_from_thread(self._op_failed, msg)
            return
        self.call_from_thread(self._op_done, operation, proposal)

    def _op_failed(self, msg):
        self._stop_spinner()
        self.pending = None
        self.pending_kind = None
        self._set_status(msg)

    def _op_done(self, operation, proposal):
        self._stop_spinner()
        self.pending = proposal
        self.pending_kind = 'op'
        self._set_status(
            f"{operation} 제안 생성 — accept 또는 reject (proposal {proposal['id']})")

    # --- fork (branch) ---
    def _start_fork(self):
        hid = self._current_hid
        if hid is None:
            return
        if self._op_worker is not None and not self._op_worker.is_finished:
            self._set_status("다른 연산이 실행 중입니다. cancel 후 다시 시도하세요.")
            return
        factory = self.op_factories.get('fork')
        if factory is None:
            self._set_status("fork 어댑터가 설정되지 않았습니다(읽기 전용).")
            return
        self._start_spinner("fork 실행 중")
        self._op_worker = self._run_fork(hid, factory)

    @work(thread=True, exclusive=True, group="op")
    def _run_fork(self, hid, factory):
        from .branch import BranchService
        worker = get_current_worker()
        try:
            proposal = BranchService(self.root).propose(
                hid, adapter_factory=factory, cancelled=lambda: worker.is_cancelled)
        except BaseException as e:  # noqa: BLE001
            msg = "취소됨" if worker.is_cancelled else f"fork 실패: {e}"
            self.call_from_thread(self._op_failed, msg)
            return
        self.call_from_thread(self._branch_done, proposal)

    def _branch_done(self, proposal):
        self._stop_spinner()
        self.pending = proposal
        self.pending_kind = 'branch'
        cands = proposal.get('candidates', [])
        lines = ["[b]fork 후보[/b] — accept [번호…] (기본 전체) 또는 reject"]
        for i, c in enumerate(cands, 1):
            lines.append(f"  {i}. {c['title']} — {c.get('difference', '')}")
        self.query_one("#details", Static).update("\n".join(lines))
        self._set_status(f"fork 제안 {len(cands)}개 — accept(전체) / accept 1 2 / reject")

    # --- synthesize (다중 선택) ---
    def _toggle_mark(self):
        hid = self._current_hid
        if hid is None:
            return
        if hid in self.marked:
            self.marked.discard(hid)
        else:
            self.marked.add(hid)
        self._rebuild_table()
        self._set_status(f"표시됨 {len(self.marked)}개: {', '.join(sorted(self.marked)) or '없음'}")

    def _start_synth(self):
        if self._op_worker is not None and not self._op_worker.is_finished:
            self._set_status("다른 연산이 실행 중입니다. cancel 후 다시 시도하세요.")
            return
        targets = sorted(self.marked)
        if len(targets) < 2:
            self._set_status("synthesize는 mark로 2개 이상 선택해야 합니다.")
            return
        factory = self.op_factories.get('synthesize')
        if factory is None:
            self._set_status("synthesize 어댑터가 설정되지 않았습니다(읽기 전용).")
            return
        self._start_spinner(f"synthesize 실행 중 {targets}")
        self._op_worker = self._run_synth(targets, factory)

    @work(thread=True, exclusive=True, group="op")
    def _run_synth(self, targets, factory):
        worker = get_current_worker()
        try:
            proposal = OperationsService(self.root).propose(
                'synthesize', targets, adapter_factory=factory,
                cancelled=lambda: worker.is_cancelled)
        except BaseException as e:  # noqa: BLE001
            msg = "취소됨" if worker.is_cancelled else f"synthesize 실패: {e}"
            self.call_from_thread(self._op_failed, msg)
            return
        self.call_from_thread(self._op_done, 'synthesize', proposal)

    def _selected_candidates(self, args):
        cands = self.pending.get('candidates', [])
        tokens = args.split()
        if not tokens:
            return [c['candidate_id'] for c in cands]
        out = []
        for t in tokens:
            if t.isdigit() and 1 <= int(t) <= len(cands):
                cid = cands[int(t) - 1]['candidate_id']
                if cid not in out:
                    out.append(cid)
        return out

    def _accept(self, args=""):
        if not self.pending:
            self._set_status("승인할 제안이 없습니다.")
            return
        try:
            if self.pending_kind == 'branch':
                selected = self._selected_candidates(args)
                if not selected:
                    self._set_status("유효한 후보 번호가 없습니다.")
                    return
                from .branch import BranchService
                BranchService(self.root).accept(self.pending['id'], selected)
            else:
                OperationsService(self.root).accept(self.pending['id'])
        except Exception as e:  # noqa: BLE001
            self._set_status(f"accept 실패: {e}")
            return
        self.pending = None
        self.pending_kind = None
        self.marked.clear()
        self._reload_state()
        self._rebuild_table()
        self._set_status("제안 승인 — 저장됨")

    def _reject(self):
        if not self.pending:
            self._set_status("거부할 제안이 없습니다.")
            return
        try:
            if self.pending_kind == 'branch':
                from .branch import BranchService
                BranchService(self.root).reject(self.pending['id'], reason="tui-reject")
            else:
                OperationsService(self.root).reject(self.pending['id'], reason="tui-reject")
        except Exception as e:  # noqa: BLE001
            self._set_status(f"reject 실패: {e}")
            return
        self.pending = None
        self.pending_kind = None
        self._set_status("제안 거부됨")


def run_tui(root, op_factories=None):
    InquiryTUI(root, op_factories=op_factories).run()
