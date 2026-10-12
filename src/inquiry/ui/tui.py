"""M2-6 TUI: Git-log 지도 + 키보드 ↑/↓ 선택 → Details, 명령 입력 → 연산.

Textual 기반(ADR-D7 Gate B 항목4 선정).
- 읽기: 저장된 inquiry를 compact 표로, 하이라이트 가설 상세를 Details에.
- 쓰기: 하단 명령으로 start(상태전이)·deepen/challenge(모델 연산)를 실행.
  모델 연산은 취소 가능한 thread 워커로 돌리고(협조적 cancelled), 결과는
  사람이 accept/reject로 확정한다(ADR-D5 human-approval).
"""
import os

# 한글 IME 보존: Textual의 kitty 키보드 프로토콜은 iTerm2에서 키를 raw 이벤트로
# 보고해 macOS IME 조합을 우회한다(자모가 낱개로 들어옴). textual import 전에
# 기본으로 끈다(사용자 env 설정이 있으면 존중). 진단: 2026-10-10 ime-diag 로그.
os.environ.setdefault("TEXTUAL_DISABLE_KITTY_KEY", "1")

from rich import box
from rich.cells import cell_len
from rich.table import Table
from rich.text import Text
from textual import constants as _textual_constants
from textual import work
from textual.worker import get_current_worker

# env가 늦게 설정돼도(다른 모듈이 textual을 먼저 import) 확실히 끈다 —
# 드라이버는 이 상수를 시작 시점(런타임)에 읽는다.
_textual_constants.DISABLE_KITTY_KEY = True
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Footer, Header, Input, Static

from inquiry.commands import Commands
from inquiry.ui.graphlog import graph_rows
from inquiry.features.operation.service import OperationsService
from inquiry.store.store import Store
from inquiry.domain.replay import replay
from inquiry import monitor

SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"   # 모델 연산 실행 중 애니메이션 프레임
SPINNER_ASCII = "|/-\\"       # --ascii 모드 스피너(유니코드 braille 대체)


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
# --ascii fallback: 동일 키, 순수 ASCII 기호(유니코드 미지원 터미널·접근성).
STATUS_ASCII = {
    'suggested': ('o', 'Suggested'),
    'exploring': ('O', 'Exploring'),
    'supported': ('*', 'Supported'),
    'contested': ('%', 'Contested'),
    'suspended': ('-', 'Suspended'),
    'refuted': ('x', 'Refuted'),
    'synthesized': ('#', 'Synthesized'),
    'human-closed': ('X', 'Closed'),
}
# 표시 레이어 유니코드→ASCII 치환(그래프 엣지·노드·마크·주석 글리프). graphlog 로직/cells는 유니코드 유지.
ASCII_GLYPHS = {'│': '|', '╲': '\\', '╱': '/', '◆': '#', '•': '+',
                '⚠': '!', '◀': '<', '⟶': '->'}
STATUS_STYLE = {
    'suggested': 'grey62',
    'exploring': 'bright_cyan',
    'supported': 'bold green',
    'contested': 'yellow',
    'suspended': 'grey62',
    'refuted': 'bold red',
    # magenta는 Textual 다크 테마에서 red와 같은 RGB(#f4005f)로 매핑돼 Refuted와
    # 구분이 안 된다 — 테마를 거치지 않는 non-ANSI 색을 쓴다(2026-10-10 검증 발견).
    'synthesized': 'bold medium_purple1',
    'human-closed': 'grey50',
}
# GRAPH 열 레인(브랜치)별 색 — 분기되면 머지 전까지 레인마다 다른 색.
# bright_magenta도 테마에서 bright_red와 동일 RGB라 non-ANSI medium_orchid로 대체.
LANE_COLORS = ("bright_white", "bright_cyan", "medium_orchid", "bright_green",
               "bright_yellow", "bright_blue", "bright_red", "orange1")
MODEL_OPS = ('deepen', 'challenge')
# 결정 동사 → {evidence: 근거 선택 수집(CLI 관례), reopen_if: 재개 조건(refute/close 도메인 필수)}.
# reason은 모든 결정에 필수. start는 기본 reason이 주입되므로 별도 경로(_transition)로 둔다.
DECISION_VERBS = {
    'support':  {'evidence': True,  'reopen_if': False},
    'contest':  {'evidence': True,  'reopen_if': False},
    'refute':   {'evidence': True,  'reopen_if': True},
    'suspend':  {'evidence': False, 'reopen_if': False},
    'continue': {'evidence': False, 'reopen_if': False},
    'reopen':   {'evidence': True,  'reopen_if': False},
    'close':    {'evidence': False, 'reopen_if': True},
}
LEGEND = "  ".join(f"{sym} {label}" for sym, label in STATUS.values())


def resolve_no_color(flag, env=None):
    """--no-color 플래그 또는 NO_COLOR 환경변수(비어있지 않으면) 중 하나라도 참이면 무색."""
    if env is None:
        env = os.environ
    return bool(flag) or bool(env.get("NO_COLOR"))


HELP = ("명령: start · support · contest · refute · suspend · continue · reopen · "
        "close · deepen · challenge · fork · mark · synthesize · accept · reject · "
        "cancel · action <제목> · check/uncheck <ID> · find <ID> · legend · quit")


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


def _detail_text(h, state, glyphs=STATUS):
    sym, label = glyphs.get(h.status, ('?', h.status))
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
    acts = [a for a in sorted(state.actions.values(), key=lambda a: a.id)
            if a.hypothesis_id == h.id]
    if acts:
        lines.append("[b]Actions[/b]")
        lines += [f"  \\[{'x' if a.done else ' '}] {a.id} {a.title}" for a in acts]
    return "\n".join(lines)


class _Root:
    """표시 전용 루트 노드 — 탐구 자체. 모든 루트 가설의 가상 부모."""
    id = 'ROOT'
    parent_ids = ()
    status = 'root'

    def __init__(self, title):
        self.title = title or '(탐구)'


class _Proxy:
    """루트 가설에 가상 부모 ROOT를 붙이는 표시용 래퍼."""
    parent_ids = ('ROOT',)

    def __init__(self, node):
        self._node = node

    def __getattr__(self, name):
        return getattr(self._node, name)


class IMEInput(Input):
    """IME 커서 위치가 정확한 Input.

    Textual Input은 커서가 끝에 있을 때 셀 오프셋에 +1을 더해(_cursor_offset)
    실제 터미널 커서(IME 조합 글자 위치)가 한 칸 오른쪽에 뜬다. 한글 조합에서만
    보이는 off-by-one이라 여기서 +1 없이 계산한다(2026-10-10 사용자 보고).
    """

    @property
    def cursor_screen_offset(self):
        from textual.geometry import Offset
        x, y, _w, _h = self.content_region
        scroll_x, _ = self.scroll_offset
        return Offset(x + self._position_to_cell(self.cursor_position) - scroll_x, y)


class GraphView(Static):
    """포커스 가능한 git-log 지도 — Rich Table을 렌더하고 ↑/↓(k/j)로 선택 이동."""
    can_focus = True
    BINDINGS = [
        Binding("up,k", "move(-1)", "위", show=False),
        Binding("down,j", "move(1)", "아래", show=False),
        # ':'는 지도에서만 명령창 포커스로 작동 — App 전역이면 Input 포커스 중
        # ':' 문자 입력을 가로챈다.
        Binding("colon", "app.focus_cmd", "명령", key_display=":"),
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
    #summary { height: 1; color: $accent; padding: 0 1; }
    #status { height: 1; color: $text-muted; padding: 0 1; }
    #cmd { dock: bottom; border: tall $accent; }
    """
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("escape", "cancel_op", "취소"),
        Binding("n", "next_pending", "다음 결정대기"),
    ]

    def action_next_pending(self):
        """결정 대기(triage/decide/resolve) 노드로 순환 이동. 결정은 CLI로."""
        pending_ids = {item['id'] for items in self._review.values() for item in items}
        if not pending_ids or not self.nodes:
            self._set_status("결정 대기 노드가 없습니다.")
            return
        total = len(self.nodes)
        for offset in range(1, total + 1):
            index = (self.sel + offset) % total
            if self.nodes[index].id in pending_ids:
                self._rebuild_table(select=index)
                label = monitor.pending_label(self.nodes[index].id, self._review)
                self._set_status(f"{self.nodes[index].id} · {label[0]} — 결정은 CLI "
                                 f"(inquiry {label[1][0]} {self.nodes[index].id} …)")
                return

    def __init__(self, root, op_factories=None, follow=True, *,
                 no_color=False, no_animation=False, ascii_mode=False):
        super().__init__()
        self.root = root
        # op_factories: {operation: adapter_factory()->(adapter, model)}. None → 실행 불가(읽기).
        self.op_factories = op_factories or {}
        self.follow = follow           # 외부 push 실시간 반영(폴링). CLI --no-follow로 끔.
        # B1 접근성: 무색/정적/ASCII. glyphs·tr·spinner를 모드에 맞게 선택.
        self.no_color = no_color
        self.no_animation = no_animation
        self.ascii_mode = ascii_mode
        self._glyphs = STATUS_ASCII if ascii_mode else STATUS
        self._spinner = SPINNER_ASCII if ascii_mode else SPINNER
        self._last_sig = None          # 마지막으로 반영한 로그 signature
        self.pending = None            # 사람 승인 대기 중인 proposal
        self.pending_kind = None       # 'op' | 'branch'
        self._decision = None          # 진행 중인 결정 입력 마법사 상태(A1)
        self.marked = set()            # synthesize 대상으로 표시한 가설 ID
        self.sel = 0                   # 선택된 노드 인덱스
        self._op_worker = None
        self._spin_timer = None        # 연산 중 스피너 타이머
        self._spin_i = 0
        self._spin_label = ""
        self._reload_state()

    def _st(self, style):
        """no_color면 빈 스타일(무색), 아니면 원본 Rich 스타일."""
        return "" if self.no_color else style

    def _tr(self, s):
        """ascii_mode면 유니코드 글리프를 ASCII로 치환한 문자열."""
        if not self.ascii_mode or not s:
            return s
        for uni, asc in ASCII_GLYPHS.items():
            s = s.replace(uni, asc)
        return s

    def _paused(self):
        """폴링 일시중지 조건 — 사람 조작 중엔 화면을 갱신하지 않는다."""
        if self.pending is not None:
            return True
        if self._decision is not None:   # 결정 마법사 중엔 폴링이 상태를 갈아끼우지 않게
            return True
        if self._op_worker is not None and not self._op_worker.is_finished:
            return True
        try:
            if self.query_one("#cmd", Input).has_focus:
                return True
        except Exception:
            pass
        return False

    def _poll(self):
        """로그 변경 시에만 리로드·재렌더(선택은 id 기준 보존). 테스트가 직접 호출 가능."""
        if self._paused():
            return
        signature = Store(self.root).signature()
        if signature == self._last_sig:
            return
        self._last_sig = signature
        keep = self._current_hid
        self._reload_state()
        select = None
        if keep is not None:
            select = next((i for i, n in enumerate(self.nodes) if n.id == keep), None)
        self._rebuild_table(select=select)  # None이면 기존 인덱스 clamp(사라진 노드 fallback)

    def _reload_state(self):
        # Load raw events too: proposing-agent attribution and saturation need them
        # (assessment and near-duplicates come from the state projection). One replay.
        self.events = Store(self.root).read_all()
        self.state = replay(self.events)
        self._creators = monitor._creators(self.events)
        self._summary = monitor.summary(self.events, self.state)
        self._review = monitor.review(self.events, self.state)
        real = _order(self.state)
        if real:
            # scale.py처럼 맨 위에 ROOT(탐구 자체)를 두고, 루트 가설들이 여기서 분기.
            seed = self.state.inquiry.seed if self.state.inquiry else ''
            self.nodes = [_Root(seed)] + [
                _Proxy(n) if not n.parent_ids else n for n in real]
        else:
            self.nodes = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            with VerticalScroll(id="mapwrap"):
                yield GraphView(id="map")
            yield Static("", id="details")
        yield Static("", id="summary")
        yield Static(HELP, id="status")
        yield IMEInput(placeholder="명령 (: 로 포커스)", id="cmd")
        yield Footer()

    def on_mount(self):
        if self.no_color:
            # 터미널 자체 팔레트에 위임(모노크롬/NO_COLOR 터미널 존중). 컨텐츠색은 _st로 이미 제거.
            self.theme = "ansi-dark"
        frame = (self.state.inquiry.frame if self.state.inquiry else {}) or {}
        self.title = "Inquiry"
        self.sub_title = frame.get("central_question") or (
            self.state.inquiry.seed if self.state.inquiry else "(빈 탐구)")
        self.query_one("#details").border_title = "Details"
        self._rebuild_table(select=1 if len(self.nodes) > 1 else 0)
        self.query_one("#map", GraphView).focus()
        self._last_sig = Store(self.root).signature()   # 현재까지 반영됨
        if self.follow:
            self.set_interval(0.5, self._poll)           # 외부 push 실시간 반영

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
        table, sel_line = self._build_table()
        gv.update(table)
        self._update_summary()
        self._show(self.nodes[self.sel].id)
        # 대규모 그래프에서 선택이 뷰포트 밖으로 나가는 문제(m1b 18페이지 문제의
        # TUI 버전): 렌더 후 선택 행이 보이도록 지도 스크롤을 따라 붙인다.
        self.call_after_refresh(self._scroll_selection_into_view, sel_line)

    def _scroll_selection_into_view(self, line):
        wrap = self.query_one("#mapwrap", VerticalScroll)
        height = wrap.size.height
        if height <= 0 or line is None:
            return
        top = wrap.scroll_offset.y
        # HYPOTHESIS 열 줄바꿈으로 라인 추정이 어긋날 수 있어 가장자리 여유 2행.
        if line < top + 2 or line > top + height - 3:
            wrap.scroll_to(y=max(0, line - height // 2), animate=False)

    def _build_table(self):
        t = Table(box=box.ROUNDED, expand=True, pad_edge=False, padding=(0, 1),
                  border_style=self._st("grey42"), header_style=self._st("bold bright_cyan"),
                  title="Branch log", title_justify="left", title_style=self._st("bold cyan"),
                  caption=f"{len(self.nodes)} nodes", caption_justify="right",
                  caption_style=self._st("grey50"))
        t.add_column("GRAPH", no_wrap=True)
        t.add_column("ID", no_wrap=True, style=self._st("grey74"))
        t.add_column("HYPOTHESIS", ratio=1)
        t.add_column("STATUS", no_wrap=True)
        by_id = {n.id: n for n in self.nodes}
        idx = {n.id: i for i, n in enumerate(self.nodes)}
        # 표 상단 고정 라인: 제목 + 윗테두리 + 헤더 + 구분선 = 4 (box.ROUNDED+title)
        sel_line, data_row = None, 4
        for row in graph_rows(self.nodes):
            if row['kind'] == 'fork':
                t.add_row(self._edge_cell(row['cells']), "",
                          Text("Fork", style=self._st("grey50")), "")
                data_row += 1
                continue
            if row['kind'] == 'merge':
                t.add_row(self._edge_cell(row['cells']), "",
                          Text("Merge / " + " + ".join(row['parents']), style=self._st("grey50")), "")
                data_row += 1
                continue
            if row['kind'] == 'compact':
                t.add_row(self._edge_cell(row['cells']), "", "", "")
                data_row += 1
                continue
            h = by_id[row['id']]
            marked = h.id in self.marked
            selected = (idx[h.id] == self.sel)
            if selected:
                sel_line = data_row
            # GRAPH 열: 노드(*)·머지(◆)·분기선만, 레인별 색. 상태 기호 없음.
            glyph = self._tr('◆') if row['merge'] else '*'
            if h.status == 'root':
                status_cell = Text("Inquiry", style=self._st("bold cyan"))
            else:
                sym, label = self._glyphs.get(h.status, ('?', h.status))
                status_cell = Text(f"{sym} {label}",
                                   style=self._st(STATUS_STYLE.get(h.status, 'white')))
            title = Text(("▸ " if selected else "  ") + h.title)
            if h.id not in ('ROOT',):
                agent = self._creators.get(h.id)
                if agent:
                    title.append(f"  {agent.split(':', 1)[-1]}", style=self._st("grey50"))
                if monitor.duplicate_peers(self._summary['duplicates'], h.id):
                    title.append(self._tr("  ⚠dup"), style=self._st("yellow"))
                pending = monitor.pending_label(h.id, self._review)
                if pending:
                    title.append(self._tr(f"  ◀{pending[0]}"), style=self._st("bold magenta"))
            t.add_row(self._node_cell(row['cells'], row['col'], glyph, marked),
                      Text('' if h.id == 'ROOT' else h.id),
                      title,
                      status_cell,   # 상태 기호·색은 STATUS 열에만
                      style=(self._st("on grey30") if selected else None))
            data_row += 1
        return t, sel_line

    def _node_cell(self, cells, col, glyph, marked=False):
        """노드 행: col에 */◆, 나머지 활성 레인은 │ — 레인별 색(머지 전까지 유지)."""
        c = Text()
        c.append(self._tr("•") if marked else " ", style=self._st("bold yellow") if marked else "")
        for i, ch in enumerate(cells):
            color = LANE_COLORS[i % len(LANE_COLORS)]
            if i == col:
                c.append(self._tr(glyph), style=self._st(f"bold {color}"))
            elif ch == '│':
                c.append(self._tr('│'), style=self._st(color))
            else:
                c.append(' ')
            c.append(' ')
        return c

    def _edge_cell(self, cells):
        """전환 행(│╲ / │╱): 글리프를 각 레인 색으로 그대로 그린다."""
        c = Text(" ")
        for i, ch in enumerate(cells):
            color = LANE_COLORS[i % len(LANE_COLORS)]
            c.append(self._tr(ch) if ch != ' ' else ' ', style=self._st(color))
            c.append(' ')
        return c

    def _move_selection(self, delta):
        if not self.nodes:
            return
        self.sel = max(0, min(self.sel + delta, len(self.nodes) - 1))
        self._rebuild_table()

    def _show(self, hid):
        if hid == 'ROOT':
            frame = (self.state.inquiry.frame if self.state.inquiry else {}) or {}
            lines = [f"[b]ROOT[/b]  탐구",
                     "", f"[b]중심 질문[/b] {frame.get('central_question', '-')}"]
            if frame.get('purpose'):
                lines.append(f"[b]목적[/b] {frame['purpose']}")
            for c in frame.get('criteria', [])[:4]:
                lines.append(f"  · {c}")
            self.query_one("#details", Static).update("\n".join(lines))
            return
        h = self.state.hypotheses.get(hid)
        if h is not None:
            self.query_one("#details", Static).update(self._detail(h))

    def _detail(self, h):
        """Base detail + control-plane block (proposing agent, confidence, dup, gate)."""
        text = _detail_text(h, self.state, glyphs=self._glyphs)
        extra = []
        agent = self._creators.get(h.id)
        if agent:
            extra.append(f"[b]제안[/b] {agent}")
        conf = monitor.assessment_summary(h)
        if conf:
            extra.append(f"[b]confidence[/b] {conf}")
        peers = monitor.duplicate_peers(self._summary['duplicates'], h.id)
        if peers:
            extra.append(self._tr(f"[b]⚠ 중복 유사[/b] {', '.join(peers)}"))
        pending = monitor.pending_label(h.id, self._review)
        if pending:
            extra.append(self._tr(f"[b]⟶ 결정 대기[/b] {pending[0]}: {' / '.join(pending[1])}"))
        return text + ("\n" + "\n".join(extra) if extra else "")

    def _update_summary(self):
        self.query_one("#summary", Static).update(
            monitor.control_summary_text(self._summary) if self.nodes else "")

    def _set_status(self, text):
        self.query_one("#status", Static).update(text)

    # --- 연산 중 스피너 애니메이션 ---
    def _start_spinner(self, label):
        self._spin_label = label
        self._spin_i = 0
        if self.no_animation:
            # 정적: 타이머 없이 라벨 1회만. 진행 중임은 라벨로 전달(가짜 진행률 아님).
            self.query_one("#status", Static).update(
                Text.assemble((f"{self._spin_label} ", ""),
                              ("(cancel/Esc로 취소)", self._st("grey50"))))
            return
        if self._spin_timer is None:
            self._spin_timer = self.set_interval(0.1, self._tick_spinner)
        self._tick_spinner()

    def _tick_spinner(self):
        frame = self._spinner[self._spin_i % len(self._spinner)]
        self._spin_i += 1
        self.query_one("#status", Static).update(
            Text.assemble((f"{frame} ", self._st("bold cyan")), (f"{self._spin_label} ", ""),
                          ("(cancel/Esc로 취소)", self._st("grey50"))))

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
        if self._decision is not None:       # 결정 마법사 취소가 연산 취소보다 우선
            self._decision = None
            self._set_status("결정 취소됨")
            self.query_one("#map", GraphView).focus()
            return
        if self._op_worker is not None and not self._op_worker.is_finished:
            self._op_worker.cancel()
            self._set_status("연산 취소 요청됨…")
        else:
            self.query_one("#map", GraphView).focus()

    def on_input_submitted(self, event: Input.Submitted):
        text = event.value.strip()
        event.input.value = ""
        # 결정 마법사 진행 중이면 스텝으로 라우팅하고 #cmd 포커스를 유지(다음 입력 대기).
        # _decision_step이 완료/취소 시 스스로 지도로 포커스를 돌린다.
        if self._decision is not None:
            self._decision_step(text)
            return
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
        elif verb in DECISION_VERBS:
            self._begin_decision(verb)
        elif verb == "action":
            self._add_action(rest)
        elif verb in ("check", "uncheck"):
            self._check_action(rest, verb == "check")
        elif verb == "accept":
            self._accept(rest)
        elif verb == "reject":
            self._reject()
        elif verb == "cancel":
            self.action_cancel_op()
        elif verb == "find":
            self._find(rest)
        elif verb == "legend":
            self._set_status("  ".join(f"{sym} {label}" for sym, label in self._glyphs.values()))
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
        if hid is None or hid == 'ROOT':
            self._set_status('ROOT는 탐구 자체입니다 — 가설을 선택하세요.') if hid == 'ROOT' else None
            return
        try:
            Commands(self.root).decide(hid, action)
        except Exception as e:  # noqa: BLE001 — surface to status line
            self._set_status(f"{action} 실패: {e}")
            return
        self._reload_state()
        self._rebuild_table()
        self._set_status(f"{hid} → {action} 적용")

    # --- 결정 입력 마법사 (A1): reason·evidence·reopen_if를 순차 수집 ---
    def _begin_decision(self, verb):
        hid = self._current_hid
        if hid is None or hid == 'ROOT':
            self._set_status('가설을 선택한 뒤 결정하세요(ROOT는 탐구 자체).')
            return
        spec = DECISION_VERBS[verb]
        links = [l for l in self.state.evidence_links if l.hypothesis_id == hid]
        if spec['evidence'] and not links:
            # TUI 정책(CLI 관례 미러) — 도메인 강제는 아님. support/contest/refute/reopen은 근거를 먼저.
            self._set_status(f"{verb}: 먼저 근거를 링크하세요(evidence 선택 불가).")
            return
        need = ['reason']
        if spec['evidence']:
            need.append('evidence')
        if spec['reopen_if']:
            need.append('reopen_if')
        self._decision = {'verb': verb, 'hid': hid, 'need': need, 'idx': 0,
                          'got': {}, 'links': links}
        self._prompt_decision_field()
        self.query_one("#cmd", Input).focus()

    def _prompt_decision_field(self):
        d = self._decision
        field = d['need'][d['idx']]
        verb = d['verb']
        if field == 'reason':
            self._set_status(f"[{verb}] 사유(reason)를 입력하고 Enter (취소: cancel)")
        elif field == 'evidence':
            lines = [f"[{verb}] 근거 번호를 선택하세요 (취소: cancel)"]
            for i, l in enumerate(d['links'], 1):
                ev = self.state.evidence.get(l.evidence_id)
                desc = f"{ev.type}: {ev.content[:60]}" if ev else l.evidence_id
                lines.append(f"  {i}. [{l.relation}] {desc}")
            self.query_one("#details", Static).update("\n".join(lines))
            self._set_status(f"[{verb}] 근거 번호(1~{len(d['links'])}) 입력 후 Enter (취소: cancel)")
        elif field == 'reopen_if':
            self._set_status(f"[{verb}] 재개 조건(reopen_if)을 입력하고 Enter (취소: cancel)")

    def _decision_step(self, text):
        d = self._decision
        if text.strip().lower() in ('cancel', '/cancel'):
            self._decision = None
            self._set_status("결정 취소됨")
            self.query_one("#map", GraphView).focus()
            return
        field = d['need'][d['idx']]
        if field == 'reason':
            if not text.strip():
                self._set_status("사유를 입력하세요(빈 값 불가, 취소: cancel).")
                return
            d['got']['reason'] = text.strip()
        elif field == 'evidence':
            links = d['links']
            if not (text.strip().isdigit() and 1 <= int(text.strip()) <= len(links)):
                self._set_status(f"1~{len(links)} 범위의 번호를 입력하세요(취소: cancel).")
                return
            d['got']['evidence_id'] = links[int(text.strip()) - 1].evidence_id
        elif field == 'reopen_if':
            if not text.strip():
                self._set_status("재개 조건을 입력하세요(빈 값 불가, 취소: cancel).")
                return
            d['got']['reopen_if'] = text.strip()
        d['idx'] += 1
        if d['idx'] < len(d['need']):
            self._prompt_decision_field()
            return
        self._commit_decision()

    def _commit_decision(self):
        d = self._decision
        verb, hid, got = d['verb'], d['hid'], d['got']
        self._decision = None
        try:
            Commands(self.root).decide(hid, verb, reason=got.get('reason', ''),
                                       evidence_id=got.get('evidence_id'),
                                       reopen_if=got.get('reopen_if'))
        except Exception as e:  # noqa: BLE001 — surface to status line
            self._set_status(f"{verb} 실패: {e}")
            self.query_one("#map", GraphView).focus()
            return
        self._reload_state()
        self._rebuild_table()
        self._set_status(f"{hid} → {verb} 적용")
        self.query_one("#map", GraphView).focus()

    def _add_action(self, title):
        hid = self._current_hid
        if hid is None or hid == 'ROOT':
            self._set_status('가설을 선택한 뒤 action <제목> 으로 추가하세요.')
            return
        if not title:
            self._set_status('action <제목> 형식으로 입력하세요.')
            return
        try:
            aid = Commands(self.root).add_action(hid, title)
        except Exception as e:  # noqa: BLE001 — surface to status line
            self._set_status(f"action 실패: {e}")
            return
        self._reload_state()
        self._rebuild_table()
        self._set_status(f"{hid}에 {aid} 추가됨")

    def _check_action(self, aid, done):
        aid = aid.strip().upper()
        if not aid:
            self._set_status('check <A-ID> / uncheck <A-ID> 형식으로 입력하세요.')
            return
        try:
            Commands(self.root).check_action(aid, done=done)
        except Exception as e:  # noqa: BLE001 — surface to status line
            self._set_status(f"{'check' if done else 'uncheck'} 실패: {e}")
            return
        self._reload_state()
        self._rebuild_table()
        self._set_status(f"{aid} {'완료' if done else '해제'}")

    def _start_op(self, operation):
        hid = self._current_hid
        if hid is None or hid == 'ROOT':
            self._set_status('ROOT에는 연산할 수 없습니다 — 가설을 선택하세요.') if hid == 'ROOT' else None
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
        if hid is None or hid == 'ROOT':
            self._set_status('ROOT에는 연산할 수 없습니다 — 가설을 선택하세요.') if hid == 'ROOT' else None
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
        from inquiry.features.branch.service import BranchService
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
        if hid is None or hid == 'ROOT':
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
                from inquiry.features.branch.service import BranchService
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
                from inquiry.features.branch.service import BranchService
                BranchService(self.root).reject(self.pending['id'], reason="tui-reject")
            else:
                OperationsService(self.root).reject(self.pending['id'], reason="tui-reject")
        except Exception as e:  # noqa: BLE001
            self._set_status(f"reject 실패: {e}")
            return
        self.pending = None
        self.pending_kind = None
        self._set_status("제안 거부됨")


def run_tui(root, op_factories=None, follow=True, *,
            no_color=False, no_animation=False, ascii_mode=False):
    InquiryTUI(root, op_factories=op_factories, follow=follow, no_color=no_color,
               no_animation=no_animation, ascii_mode=ascii_mode).run()
