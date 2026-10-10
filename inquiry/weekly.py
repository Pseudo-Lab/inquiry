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
    frame = state.inquiry.frame
    return {
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


def render_markdown(report):
    lines = [f"# Weekly — {report['start']} ~ {report['end']}", '',
             f"중심 질문: **{report['question']}**"]
    for title, items in _sections(report):
        lines.append('')
        lines.append(f'## {title}')
        lines.append('')
        if items:
            lines.extend(f'- {item}' for item in items)
        else:
            lines.append('- (없음)')
    lines.append('')
    return '\n'.join(lines)
