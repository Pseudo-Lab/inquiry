"""순수 DAG 레인 배치 — git log --graph 식 세로 그래프를 실제 parent_ids에서 계산.

위→아래가 계보(부모가 위, 자식이 아래, PRODUCT-CONCEPT §9). 각 노드는 하나의
레인(열)을 차지하고, 활성 레인은 세로 바 │로 이어진다. fork(부모의 자식 2+)는
새 레인을 열고, merge(자식의 부모 2+)·마지막 자식은 레인을 닫는다.

lane_rows(nodes)는 노드마다 (cells, col)을 돌려준다:
- cells[i]: 레인 i의 글리프('│' 또는 ' '), col 위치는 '@'(노드 자리표시자)
- col: 이 노드가 놓인 레인 인덱스
렌더는 '@'를 상태 기호로 치환해 문자열로 만든다.
"""


def lane_rows(nodes):
    """nodes: 부모가 먼저 오는 순서의 Hypothesis 목록. 반환: [(cells, col), …].

    레인 모델: lanes[i] = 그 레인이 '다음에 그릴 것으로 기다리는' 노드 id(또는 None).
    부모를 그릴 때 각 자식마다 기다림 레인을 예약한다 — 첫 자식은 부모 레인 재사용,
    나머지는 새 레인(fork). 자식이 여러 부모를 가지면(merge) 여러 레인이 그 자식을
    기다리게 되고, 자식을 그릴 때 왼쪽 레인만 남기고 나머지는 닫는다.
    """
    all_ids = {n.id for n in nodes}
    childmap = {}
    for n in nodes:
        for p in n.parent_ids:
            if p in all_ids:
                childmap.setdefault(p, []).append(n.id)

    def free_slot():
        return next((i for i, a in enumerate(lanes) if a is None), len(lanes))

    lanes = []            # 기다리는 노드 id 또는 None
    rows = []
    for n in nodes:
        awaiting = [i for i, a in enumerate(lanes) if a == n.id]
        if awaiting:
            col = awaiting[0]
        else:
            col = free_slot()
            if col == len(lanes):
                lanes.append(None)

        cells = []
        for i in range(len(lanes)):
            if i == col:
                cells.append('@')
            elif lanes[i] is not None:
                cells.append('│')
            else:
                cells.append(' ')
        rows.append((cells, col))

        # merge: 이 노드를 기다리던 다른 레인은 닫는다
        for i in awaiting:
            if i != col:
                lanes[i] = None
        # 자식 예약: 첫 자식은 col 재사용, 나머지는 새 레인(fork)
        kids = childmap.get(n.id, [])
        if kids:
            lanes[col] = kids[0]
            for kid in kids[1:]:
                slot = free_slot()
                if slot == len(lanes):
                    lanes.append(kid)
                else:
                    lanes[slot] = kid
        else:
            lanes[col] = None

    return rows


def render_row(cells, col, symbol):
    """cells/col + 상태 기호 → 한 줄 그래프 문자열. 각 레인은 '글리프 ' 2칸."""
    out = []
    for i, ch in enumerate(cells):
        out.append(symbol if i == col else (' ' if ch == '@' else ch))
        out.append(' ')
    return ''.join(out).rstrip() or symbol
