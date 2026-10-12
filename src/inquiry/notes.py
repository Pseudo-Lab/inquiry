"""Read-only markdown exports from the event log — research note & decision record.

Siblings of weekly.py (B3). A research note is a *current snapshot* of evidence and
exploration; a decision record is the *full chronological log* of state decisions. Like
weekly, nothing is a managed object: every section is recomputed from events + replayed
state, with the §14 traceability frontmatter so an export can be traced to its source.
"""
from datetime import datetime, timezone

from inquiry import monitor
from inquiry.weekly import STATUS_LABELS, _cell, _table, _moment

ACTIVE_STATES = ('exploring', 'supported', 'contested')


def _meta(state, now):
    now = now or datetime.now(timezone.utc)
    frame = state.inquiry.frame
    return {
        'inquiry_id': state.inquiry_id,
        'through_event': state.last_seq,
        'generated_at': now.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'question': frame.get('central_question') or frame.get('question') or state.inquiry.seed,
        'purpose': frame.get('purpose'),
    }


def _frontmatter(report, title):
    return ['---', 'generated_from:', f"  inquiry: {report['inquiry_id']}",
            f"  through_event: {report['through_event']}",
            f"  generated_at: {report['generated_at']}",
            'status: draft', '---', '',
            f"# {title}", '',
            f"중심 질문: **{report['question']}**"]


def _evidence_rows(state):
    """All evidence with its relation links, shaped for a catalog table (weekly parity)."""
    relations = {}
    for link in state.evidence_links:
        relations.setdefault(link.evidence_id, []).append((link.relation, link.hypothesis_id))
    rows = []
    for identity, ev in state.evidence.items():
        links = ', '.join(f"{'지지' if rel == 'supports' else '반박'} {hid}"
                          for rel, hid in relations.get(identity, [])) or '연결 없음'
        content = ev.content + (f" ({ev.uri})" if ev.uri else '')
        rows.append((identity, links, ev.type, content))
    return rows


# --- research note (근거·탐색 요약, 현재 스냅샷) ---

def build_research_note(events, state, *, now=None):
    if state.inquiry is None:
        raise ValueError('Initialize an inquiry first.')
    report = _meta(state, now)
    links_by_h = {}
    for link in state.evidence_links:
        links_by_h.setdefault(link.hypothesis_id, []).append(link)
    active = []
    for node in state.hypotheses.values():
        if node.status not in ACTIVE_STATES:
            continue
        evidence = []
        for link in links_by_h.get(node.id, []):
            ev = state.evidence.get(link.evidence_id)
            if ev:
                evidence.append((link.relation, ev.id, ev.content))
        active.append({'node': node, 'confidence': monitor.assessment_summary(node) or '-',
                       'evidence': evidence})
    report['active'] = active
    report['evidence_rows'] = _evidence_rows(state)
    report['open'] = [node for node in state.hypotheses.values() if node.status == 'suggested']
    return report


def render_research_note(report):
    lines = _frontmatter(report, 'Research note')
    if report['purpose']:
        lines.append(f"목적: {report['purpose']}")
    if report['active']:
        lines.extend(('', '## 활성 가설', ''))
        _table(lines, ('ID', '제목', '상태', 'confidence'),
               [(a['node'].id, a['node'].title, STATUS_LABELS.get(a['node'].status, a['node'].status),
                 a['confidence']) for a in report['active']])
        for a in report['active']:
            if a['evidence']:
                lines.extend(('', f"### {a['node'].id} {a['node'].title}", ''))
                lines.append(f"주장: {a['node'].claim}")
                lines.extend(f"- [{'지지' if rel == 'supports' else '반박'}] {eid}: "
                             f"{' '.join(content.split())[:80]}" for rel, eid, content in a['evidence'])
    if report['evidence_rows']:
        lines.extend(('', '## 근거 카탈로그', ''))
        _table(lines, ('ID', '관계', '유형', '내용'), report['evidence_rows'])
    if report['open']:
        lines.extend(('', '## 탐색 후보 (suggested)', ''))
        lines.extend(f'- {node.id} {node.title}' for node in report['open'])
    lines.append('')
    return '\n'.join(lines)


# --- decision record (상태 전이·결정 사유, 전체 로그) ---

def build_decision_record(events, state, *, now=None):
    if state.inquiry is None:
        raise ValueError('Initialize an inquiry first.')
    report = _meta(state, now)
    decisions = []
    for event in events:
        for change in event['changes']:
            if change['kind'] != 'HypothesisStateChanged':
                continue
            node = state.hypotheses.get(change['hypothesis_id'])
            decisions.append({
                'hypothesis_id': change['hypothesis_id'],
                'title': node.title if node else '',
                'from': change['from'], 'to': change['to'], 'trigger': change['trigger'],
                'reason': change['reason'], 'actor': change['actor'], 'at': change['at'],
                'evidence_ids': change['evidence_ids'], 'reopen_if': change['reopen_if'],
            })
    report['decisions'] = decisions
    return report


def render_decision_record(report):
    lines = _frontmatter(report, 'Decision record')
    decisions = report['decisions']
    lines.extend(('', '## 결정', ''))
    if not decisions:
        lines.append('(결정 없음)')
        lines.append('')
        return '\n'.join(lines)
    rows = []
    for d in decisions:
        arrow = '{} → {}'.format(STATUS_LABELS.get(d['from'], d['from']),
                                 STATUS_LABELS.get(d['to'], d['to']))
        cited = ', '.join(d['evidence_ids']) or '-'
        rows.append((f"{d['hypothesis_id']} {d['title']}", arrow, d['trigger'], d['actor'],
                     cited, d['reason']))
    _table(lines, ('가설', '변화', '트리거', '행위자', '근거', '사유'), rows)
    reopen = [d for d in decisions if d['reopen_if']]
    if reopen:
        lines.extend(('', '## 재개 조건 (종결 결정)', ''))
        lines.extend(f"- {d['hypothesis_id']} ({STATUS_LABELS.get(d['to'], d['to'])}): {d['reopen_if']}"
                     for d in reopen)
    lines.append('')
    return '\n'.join(lines)
