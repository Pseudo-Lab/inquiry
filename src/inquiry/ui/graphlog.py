"""순수 DAG 레인 배치 — git log --graph 식 세로 그래프를 실제 parent_ids에서 계산.

위→아래가 계보(부모가 위, 자식이 아래, PRODUCT-CONCEPT §9). git log는 상하가
반대(최신이 위)지만 레인 배정 규칙은 동일하게 적용한다.

git log --graph 규칙 (2026-10 조사: git-scm 문서 + 실제 git 출력 관찰):
핵심 관찰 — git은 한 부모의 여러 리프 자식을 '병렬 레인'으로 펼치지 않는다.
부모 레인을 '척추(spine)'로 유지한 채, 자식 하나를 오른쪽 레인에 그리고(│╲),
그 자식의 서브트리가 끝나 레인이 비면 '다음 자식이 같은 레인을 재사용'한다.
그래서 리프가 많아도 폭은 2로 유지된다(git의 반복 `|/`를 뒤집으면 반복 `|╲`).

적용 규칙:
1. 자식이 1개면 부모 레인을 그대로 이어받아 본선이 세로로 내려간다(await).
2. 자식이 2개 이상이면 부모 레인을 척추로 남기고(spine), 자식마다 오른쪽
   레인으로 분기한다(│╲). 앞 자식의 레인이 비면 뒤 자식이 재사용한다.
3. 새 분기 레인은 항상 척추 '오른쪽'에 연다(왼쪽 빈 레인 재사용 금지).
4. 다부모(synthesis) 노드로 여러 레인이 모이면 한 열(col)로 합쳐진다
   (오른쪽에서 오면 ╱, 왼쪽에서 오면 ╲).
5. 레인이 끝나 생긴 구멍은 왼쪽으로 당겨 메운다(compaction, ╱).

graph_rows(nodes)는 git log처럼 전환 행까지 돌려준다:
- {'kind':'node', 'id', 'cells', 'col', 'merge':bool} — cells의 col 위치는 '@'
- {'kind':'fork', 'cells', 'parent'}   — 자식이 ╲ 로 분기하는 전환 행 (│╲)
- {'kind':'merge', 'cells', 'parents', 'child'} — 레인이 합쳐지는 전환 행
- {'kind':'compact', 'cells'} — 구멍을 메우려 레인이 ╱ 로 당겨지는 전환 행

레인 엔트리: None | ('await', child_id) | ['spine', parent_id, remaining]
"""


def graph_rows(nodes):
    all_ids = {n.id for n in nodes}
    childmap = {}
    for n in nodes:
        for p in n.parent_ids:
            if p in all_ids:
                childmap.setdefault(p, []).append(n.id)

    lanes = []   # None | ('await', id) | ['spine', pid, rem]
    rows = []

    def free_right(after):
        """after 오른쪽의 첫 빈 레인, 없으면 끝에 새로."""
        for i in range(after + 1, len(lanes)):
            if lanes[i] is None:
                return i
        lanes.append(None)
        return len(lanes) - 1

    def snapshot(glyphs):
        return [glyphs.get(i, '│' if lanes[i] is not None else ' ')
                for i in range(len(lanes))]

    def compact():
        while True:
            gap = next((i for i, l in enumerate(lanes)
                        if l is None and any(x is not None for x in lanes[i + 1:])), None)
            if gap is None:
                while lanes and lanes[-1] is None:
                    lanes.pop()
                return
            glyphs = {i: '╱' for i in range(gap + 1, len(lanes)) if lanes[i] is not None}
            rows.append({'kind': 'compact', 'cells': snapshot(glyphs)})
            del lanes[gap]

    def set_children(col, node_id):
        """노드를 그린 뒤 그 자식들을 레인에 예약한다."""
        kids = childmap.get(node_id, [])
        if not kids:
            lanes[col] = None
        elif len(kids) == 1:
            lanes[col] = ('await', kids[0])        # 규칙 1: 단일 자식은 레인 계승
        else:
            lanes[col] = ['spine', node_id, len(kids)]   # 규칙 2: 척추 유지

    for n in nodes:
        await_cols = [i for i, l in enumerate(lanes)
                      if isinstance(l, tuple) and l[1] == n.id]
        spine_cols = [i for i, l in enumerate(lanes)
                      if isinstance(l, list) and l[1] in n.parent_ids]
        is_merge = len(await_cols) >= 2 or (bool(await_cols) and bool(spine_cols))

        if await_cols:
            col = await_cols[0]
        elif spine_cols:
            col = free_right(spine_cols[0])        # 규칙 3: 척추 오른쪽에 분기
        else:
            col = len(lanes)                       # 루트/팁: 오른쪽 끝 새 레인
            lanes.append(None)

        if is_merge:
            # 규칙 4: 여러 레인이 col로 합류. await 여분은 닫고, 척추는 유지한 채 연결.
            glyphs = {col: '│'}
            for i in await_cols:
                if i != col:
                    glyphs[i] = '╱' if i > col else '╲'
                    lanes[i] = None
            for i in spine_cols:
                glyphs[i] = '│'                    # 척추는 남는다(자식 더 있음)
            rows.append({'kind': 'merge', 'cells': snapshot(glyphs),
                         'parents': [p for p in n.parent_ids if p in all_ids],
                         'child': n.id})
        elif spine_cols:
            # 규칙 2·3: 척추에서 자식 하나가 오른쪽으로 분기(│╲).
            glyphs = {i: '│' for i in spine_cols}
            glyphs[col] = '╲'
            rows.append({'kind': 'fork', 'cells': snapshot(glyphs),
                         'parent': lanes[spine_cols[0]][1]})

        # 척추에서 자식 하나를 소비 — rem 감소, 0이면 척추 종료(col 자신은 제외).
        for i in spine_cols:
            lanes[i][2] -= 1
            if lanes[i][2] <= 0 and i != col:
                lanes[i] = None

        cells = ['@' if i == col else ('│' if lanes[i] is not None else ' ')
                 for i in range(len(lanes))]
        rows.append({'kind': 'node', 'id': n.id, 'cells': cells, 'col': col,
                     'merge': is_merge})

        set_children(col, n.id)
        compact()

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
