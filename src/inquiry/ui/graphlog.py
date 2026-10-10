"""순수 DAG 레인 배치 — git log --graph 식 세로 그래프를 실제 parent_ids에서 계산.

위→아래가 계보(부모가 위, 자식이 아래, PRODUCT-CONCEPT §9). 각 노드는 하나의
레인(열)을 차지하고, 활성 레인은 세로 바 │로 이어진다.

graph_rows(nodes)는 git log --graph처럼 **전환 행까지** 돌려준다:
- {'kind':'node', 'id', 'cells', 'col', 'merge':bool} — cells의 col 위치는 '@'
- {'kind':'fork', 'cells', 'parent'}   — 새 레인이 ╲ 로 열리는 전환 행 (│╲)
- {'kind':'merge', 'cells', 'parents', 'child'} — 레인이 ╱ 로 닫히는 전환 행 (│╱)

레인 모델: lanes[i] = 그 레인이 '다음에 그릴 것으로 기다리는' 노드 id(또는 None).
부모를 그릴 때 자식마다 레인을 예약한다 — 첫 자식은 부모 레인 재사용, 나머지는
새 레인(fork 전환 행). 다중 부모 자식은 여러 레인이 기다리다가 그 노드 직전에
merge 전환 행으로 왼쪽 레인에 합쳐진다.
"""


def graph_rows(nodes):
    all_ids = {n.id for n in nodes}
    childmap = {}
    for n in nodes:
        for p in n.parent_ids:
            if p in all_ids:
                childmap.setdefault(p, []).append(n.id)

    lanes = []  # 기다리는 노드 id 또는 None
    rows = []

    def free_slot():
        for i, a in enumerate(lanes):
            if a is None:
                return i
        lanes.append(None)
        return len(lanes) - 1

    def snapshot(glyphs=None):
        cells = []
        for i, owner in enumerate(lanes):
            if glyphs and i in glyphs:
                cells.append(glyphs[i])
            elif owner is not None:
                cells.append('│')
            else:
                cells.append(' ')
        return cells

    for n in nodes:
        awaiting = [i for i, a in enumerate(lanes) if a == n.id]
        col = awaiting[0] if awaiting else free_slot()
        merge = len(awaiting) > 1

        if merge:
            # │╱ 전환 행: 닫히는 레인들이 col 쪽으로 합쳐진다
            glyphs = {i: '╱' for i in awaiting[1:]}
            glyphs[col] = '│'
            rows.append({'kind': 'merge', 'cells': snapshot(glyphs),
                         'parents': [p for p in n.parent_ids if p in all_ids],
                         'child': n.id})
            for i in awaiting[1:]:
                lanes[i] = None

        cells = []
        for i, owner in enumerate(lanes):
            cells.append('@' if i == col else ('│' if owner is not None else ' '))
        rows.append({'kind': 'node', 'id': n.id, 'cells': cells,
                     'col': col, 'merge': merge})

        kids = childmap.get(n.id, [])
        if kids:
            lanes[col] = kids[0]
            opened = []
            for kid in kids[1:]:
                slot = free_slot()
                lanes[slot] = kid
                opened.append(slot)
            if opened:
                # │╲ 전환 행: 부모 레인은 이어지고 새 레인이 대각선으로 열린다.
                # 재사용된 빈 레인이 부모 왼쪽일 수 있다 — 그때는 ╱ (git log처럼
                # 방향을 따라 긋지 않으면 분기가 끊겨 보인다, EXT-S1 관찰).
                glyphs = {i: ('╲' if i > col else '╱') for i in opened}
                glyphs[col] = '│'
                rows.append({'kind': 'fork', 'cells': snapshot(glyphs),
                             'parent': n.id})
        else:
            lanes[col] = None

    return rows


def lane_rows(nodes):
    """하위호환: 노드 행만 (cells, col)로 돌려준다."""
    return [(r['cells'], r['col']) for r in graph_rows(nodes) if r['kind'] == 'node']


def render_row(cells, col, symbol):
    """cells/col + 기호 → 한 줄 그래프 문자열. 각 레인은 '글리프 ' 2칸."""
    out = []
    for i, ch in enumerate(cells):
        out.append(symbol if i == col else (' ' if ch == '@' else ch))
        out.append(' ')
    return ''.join(out).rstrip() or symbol
