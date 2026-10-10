"""Weekly reflection: a seven-day read-only projection of the event log.

Not a managed object — every section is recomputed from events and the
replayed state (PRODUCT-CONCEPT §13). The focus is how thinking changed,
not activity volume.
"""
from datetime import datetime, timedelta, timezone

STATUS_LABELS = {
    'suggested': '제안됨', 'exploring': '탐구 중', 'supported': '지지됨',
    'contested': '반박 경합', 'suspended': '보류', 'refuted': '반증됨',
    'human-closed': '사람 종료', 'synthesized': '통합됨',
}


def _moment(text):
    return datetime.fromisoformat(text.replace('Z', '+00:00'))


def build(events, state, *, days=7, now=None):
    """Aggregate one window of changes plus the current open questions."""
    if state.inquiry is None:
        raise ValueError('Initialize an inquiry first.')
    now = now or datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    created, transitions, evidence_ids = [], [], []
    for event in events:
        if _moment(event['at']) < start:
            continue
        for change in event['changes']:
            kind = change['kind']
            if kind == 'HypothesisCreated':
                created.append(change['hypothesis_id'])
            elif kind == 'HypothesisStateChanged':
                transitions.append(change)
            elif kind == 'EvidenceCreated':
                evidence_ids.append(change['evidence_id'])
    relations = {}
    for link in state.evidence_links:
        relations.setdefault(link.evidence_id, []).append((link.relation, link.hypothesis_id))
    evidence = [{'id': identity, 'type': state.evidence[identity].type,
                 'content': state.evidence[identity].content,
                 'uri': state.evidence[identity].uri,
                 'links': relations.get(identity, [])} for identity in evidence_ids]
    actions_done = [action for action in state.actions.values()
                    if action.done and action.done_at and _moment(action.done_at) >= start]
    actions_open = [action for action in state.actions.values() if not action.done]
    transitions = [{**change, 'title': state.hypotheses[change['hypothesis_id']].title}
                   for change in transitions]
    frame = state.inquiry.frame
    return {
        'inquiry_id': state.inquiry_id,
        'through_event': state.last_seq,
        'generated_at': now.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'question': frame.get('central_question') or frame.get('question') or state.inquiry.seed,
        'start': start.strftime('%Y-%m-%d'),
        'end': now.strftime('%Y-%m-%d'),
        'created': [state.hypotheses[identity] for identity in created],
        'transitions': transitions,
        'evidence': evidence,
        'actions_done': actions_done,
        'actions_open': actions_open,
        'contested': [node for node in state.hypotheses.values() if node.status == 'contested'],
        'suggested': [node for node in state.hypotheses.values() if node.status == 'suggested'],
    }


def _transition_line(change):
    arrow = '{} → {}'.format(STATUS_LABELS.get(change['from'], change['from']),
                             STATUS_LABELS.get(change['to'], change['to']))
    line = f"{change['hypothesis_id']}: {arrow} ({change['trigger']})"
    if change['reason']:
        line += f" — {change['reason']}"
    if change['synthesis_target']:
        line += f" → {change['synthesis_target']}"
    return line


def _evidence_line(item):
    links = ', '.join(f"{'지지' if relation == 'supports' else '반박'} {target}"
                      for relation, target in item['links']) or '연결 없음'
    content = ' '.join(item['content'].split())
    if len(content) > 80:
        content = content[:77] + '...'
    line = f"{item['id']} [{links}] {item['type']}: {content}"
    if item['uri']:
        line += f" ({item['uri']})"
    return line


def _sections(report):
    yield '새로 생긴 가설', [f'{node.id} {node.title} — {STATUS_LABELS.get(node.status, node.status)}'
                             for node in report['created']]
    yield '상태 변화', [_transition_line(change) for change in report['transitions']]
    yield '새 근거', [_evidence_line(item) for item in report['evidence']]
    yield '완료한 Actions', [f'[x] {action.id} {action.title} ({action.hypothesis_id})'
                             for action in report['actions_done']]
    yield '남은 Actions', [f'[ ] {action.id} {action.title} ({action.hypothesis_id})'
                           for action in report['actions_open']]
    yield '미해결 논쟁 (contested)', [f'{node.id} {node.title}' for node in report['contested']]
    yield '다음 탐색 후보 (suggested)', [f'{node.id} {node.title}' for node in report['suggested']]


def render_text(report):
    lines = [f"Weekly — {report['start']} ~ {report['end']}",
             f"중심 질문: {report['question']}"]
    for title, items in _sections(report):
        lines.append('')
        lines.append(title)
        if items:
            lines.extend(f'  {item}' for item in items)
        else:
            lines.append('  (없음)')
    return '\n'.join(lines)


def _cell(text):
    """표 셀 안전화 — 파이프 이스케이프, 공백 정규화."""
    return ' '.join(str(text).split()).replace('|', '\\|') or '-'


def _table(lines, header, rows):
    lines.append('| ' + ' | '.join(header) + ' |')
    lines.append('|' + '---|' * len(header))
    lines.extend('| ' + ' | '.join(_cell(cell) for cell in row) + ' |' for row in rows)


def render_markdown(report):
    """표 중심 Markdown. 빈 섹션은 생략, 머리에는 §14 추적 가능성 frontmatter."""
    lines = ['---', 'generated_from:', f"  inquiry: {report['inquiry_id']}",
             f"  through_event: {report['through_event']}",
             f"  generated_at: {report['generated_at']}",
             'status: draft', '---', '',
             f"# Weekly — {report['start']} ~ {report['end']}", '',
             f"중심 질문: **{report['question']}**"]

    def section(title):
        lines.extend(('', f'## {title}', ''))

    if report['created']:
        section('새로 생긴 가설')
        _table(lines, ('ID', '제목', '현재 상태'),
               [(node.id, node.title, STATUS_LABELS.get(node.status, node.status))
                for node in report['created']])
    if report['transitions']:
        section('상태 변화')
        rows = []
        for change in report['transitions']:
            arrow = '{} → {}'.format(STATUS_LABELS.get(change['from'], change['from']),
                                     STATUS_LABELS.get(change['to'], change['to']))
            if change['synthesis_target']:
                arrow += f" ({change['synthesis_target']}로 통합)"
            rows.append((f"{change['hypothesis_id']} {change.get('title', '')}",
                         arrow, change['trigger'], change['reason']))
        _table(lines, ('가설', '변화', '트리거', '사유'), rows)
    if report['evidence']:
        section('새 근거')
        rows = []
        for item in report['evidence']:
            links = ', '.join(f"{'지지' if relation == 'supports' else '반박'} {target}"
                              for relation, target in item['links']) or '연결 없음'
            content = item['content'] + (f" ({item['uri']})" if item['uri'] else '')
            rows.append((item['id'], links, item['type'], content))
        _table(lines, ('ID', '관계', '유형', '내용'), rows)
    if report['actions_done'] or report['actions_open']:
        section('Actions')
        lines.extend(f'- [x] {action.id} {action.title} ({action.hypothesis_id})'
                     for action in report['actions_done'])
        lines.extend(f'- [ ] {action.id} {action.title} ({action.hypothesis_id})'
                     for action in report['actions_open'])
    if report['contested']:
        section('미해결 논쟁 (contested)')
        lines.extend(f'- {node.id} {node.title}' for node in report['contested'])
    if report['suggested']:
        section('다음 탐색 후보 (suggested)')
        lines.extend(f'- {node.id} {node.title}' for node in report['suggested'])
    lines.append('')
    return '\n'.join(lines)
