"""M2-6 TUI: Git-log 지도 + 키보드 ↑/↓ 선택 → Details, 명령 입력 → 연산.

Textual 기반(ADR-D7 Gate B 항목4 선정).
- 읽기: 저장된 inquiry를 compact 표로, 하이라이트 가설 상세를 Details에.
- 쓰기: 하단 명령으로 start(상태전이)·deepen/challenge(모델 연산)를 실행.
  모델 연산은 취소 가능한 thread 워커로 돌리고(협조적 cancelled), 결과는
  사람이 accept/reject로 확정한다(ADR-D5 human-approval).
"""
from rich.text import Text
from textual import work
from textual.worker import get_current_worker
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DataTable, Footer, Header, Input, Static

from .commands import Commands
from .graphlog import lane_rows
from .operations import OperationsService

# 실루엣이 서로 다른 기호 — 색 없이(흑백)도 구분된다(Gate B 항목3 후속).
# 색은 기본 출력에서 상태를 한눈에 구분(기본=컬러 결정, 흑백은 기호로 폴백).
STATUS = {
    'suggested': ('○', 'Suggested'),
    'exploring': ('▷', 'Exploring'),
    'supported': ('✓', 'Supported'),
    'contested': ('!', 'Contested'),
    'suspended': ('=', 'Suspended'),
    'refuted': ('✗', 'Refuted'),
    'synthesized': ('◆', 'Synthesized'),
    'human-closed': ('■', 'Closed'),
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
MODEL_OPS = ('deepen', 'challenge')
LEGEND = "  ".join(f"{sym} {label}" for sym, label in STATUS.values())
HELP = ("명령: start · deepen · challenge · fork · mark · synthesize · "
        "accept · reject · cancel · find <ID> · legend · quit")


def _order(state):
    return list(state.hypotheses.values())


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


class InquiryTUI(App):
    CSS = """
    Screen { background: $surface; }
    #map {
        height: 1fr;
        border: round $primary;
        border-title-color: $accent;
        border-title-style: bold;
        padding: 0 1;
        background: $panel;
    }
    #map > .datatable--header { text-style: bold; color: $accent; }
    #map > .datatable--cursor { background: $accent 30%; }
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
        self._op_worker = None
        self._reload_state()

    def _reload_state(self):
        self.state = Commands(self.root).state()
        self.nodes = _order(self.state)

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield DataTable(id="map", cursor_type="row", zebra_stripes=True)
            yield Static("", id="details")
        yield Static(HELP, id="status")
        yield Input(placeholder="명령 (: 로 포커스)", id="cmd")
        yield Footer()

    def on_mount(self):
        frame = (self.state.inquiry.frame if self.state.inquiry else {}) or {}
        self.title = "Inquiry"
        self.sub_title = frame.get("central_question") or (
            self.state.inquiry.seed if self.state.inquiry else "(빈 탐구)")
        self.query_one("#map").border_title = "Branch log"
        self.query_one("#map").border_subtitle = f"{len(self.nodes)} nodes"
        self.query_one("#details").border_title = "Details"
        self._rebuild_table(select=0)
        self.query_one("#map", DataTable).focus()

    def _rebuild_table(self, select=None):
        table = self.query_one("#map", DataTable)
        keep = table.cursor_row if select is None else select
        table.clear(columns=True)
        table.add_columns("GRAPH", "ID", "HYPOTHESIS", "STATUS")
        lanes = lane_rows(self.nodes)
        for idx, h in enumerate(self.nodes):
            sym, label = STATUS.get(h.status, ('?', h.status))
            style = STATUS_STYLE.get(h.status, 'white')
            cells, col = lanes[idx]
            graph = self._graph_text(cells, col, sym, style, h.id in self.marked)
            status_cell = Text(f"{sym} {label}", style=style)
            table.add_row(graph, Text(h.id, style="grey70"), h.title, status_cell, key=h.id)
        if self.nodes:
            row = min(keep or 0, len(self.nodes) - 1)
            table.move_cursor(row=row)
            self._show(self.nodes[row].id)
        else:
            self.query_one("#details", Static).update(
                "이 탐구에는 아직 가설이 없습니다. framing으로 프레임을 승인하세요.")

    def _graph_text(self, cells, col, symbol, style, marked):
        t = Text()
        t.append("•" if marked else " ", style="bold yellow" if marked else "")
        for i, ch in enumerate(cells):
            if i == col:
                t.append(symbol, style=style)
            elif ch == '@':
                t.append(' ')
            else:
                t.append(ch, style="grey42")   # 레인 바는 흐리게
            t.append(' ')
        return t

    def _show(self, hid):
        h = self.state.hypotheses.get(hid)
        if h is not None:
            self.query_one("#details", Static).update(_detail_text(h, self.state))

    def _set_status(self, text):
        self.query_one("#status", Static).update(text)

    @property
    def _current_hid(self):
        table = self.query_one("#map", DataTable)
        row = table.cursor_row
        if self.nodes and 0 <= row < len(self.nodes):
            return self.nodes[row].id
        return None

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted):
        if event.row_key is not None and event.row_key.value is not None:
            self._show(event.row_key.value)

    # --- commands ---
    def action_focus_cmd(self):
        self.query_one("#cmd", Input).focus()

    def action_cancel_op(self):
        if self._op_worker is not None and not self._op_worker.is_finished:
            self._op_worker.cancel()
            self._set_status("연산 취소 요청됨…")
        else:
            self.query_one("#map", DataTable).focus()

    def on_input_submitted(self, event: Input.Submitted):
        text = event.value.strip()
        event.input.value = ""
        self.query_one("#map", DataTable).focus()
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
        self.query_one("#map", DataTable).move_cursor(row=match)
        self._show(self.nodes[match].id)
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
        self._set_status(f"{operation} 실행 중… (cancel/Esc로 취소)")
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
        self.pending = None
        self.pending_kind = None
        self._set_status(msg)

    def _op_done(self, operation, proposal):
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
        self._set_status("fork 실행 중… (cancel/Esc로 취소)")
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
        self._set_status(f"synthesize 실행 중… {targets} (cancel/Esc로 취소)")
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
