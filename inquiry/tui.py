"""M2-6 TUI: Git-log 지도 + 키보드 ↑/↓ 선택 → 하단 Details 패널.

Textual 기반(ADR-D7 Gate B 항목4에서 선정). 읽기 전용 1차 증분:
저장된 inquiry를 로드해 가설 그래프를 compact 표로 보여주고, 하이라이트된
가설의 상세(주장·전제·반증조건·근거·종료사유)를 Details에 표시한다.
연산/명령 입력 연결은 후속 증분.
"""
from dataclasses import asdict

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DataTable, Footer, Header, Static

from .commands import Commands

# 상태 → (기호, 표기). presentation.py(M1b)와 동일 눈금.
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


def _order(state):
    """표시 순서: 생성 순(replay 삽입 순) — 부모가 자식보다 먼저 나온다."""
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
    #map { height: 1fr; }
    #details { height: auto; max-height: 45%; border-top: solid $accent; padding: 0 1; }
    """
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("up", "cursor_up", "위", show=False),
        Binding("down", "cursor_down", "아래", show=False),
    ]

    def __init__(self, root):
        super().__init__()
        self.root = root
        self.state = Commands(root).state()
        self.nodes = _order(self.state)

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield DataTable(id="map", cursor_type="row", zebra_stripes=True)
            yield Static("", id="details")
        yield Footer()

    def on_mount(self):
        frame = (self.state.inquiry.frame if self.state.inquiry else {}) or {}
        self.title = "Inquiry"
        self.sub_title = frame.get("central_question") or (
            self.state.inquiry.seed if self.state.inquiry else "(빈 탐구)")
        table = self.query_one("#map", DataTable)
        table.add_columns("", "ID", "HYPOTHESIS", "STATUS")
        for h in self.nodes:
            sym, label = STATUS.get(h.status, ('?', h.status))
            table.add_row(sym, h.id, h.title, f"{sym} {label}", key=h.id)
        if self.nodes:
            table.focus()
            self._show(self.nodes[0].id)
        else:
            self.query_one("#details", Static).update(
                "이 탐구에는 아직 가설이 없습니다. framing으로 프레임을 승인하세요.")

    def _show(self, hid):
        h = self.state.hypotheses.get(hid)
        if h is not None:
            self.query_one("#details", Static).update(_detail_text(h, self.state))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted):
        if event.row_key is not None and event.row_key.value is not None:
            self._show(event.row_key.value)


def run_tui(root):
    InquiryTUI(root).run()
