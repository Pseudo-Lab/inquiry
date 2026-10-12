"""Read-only monitor summary across the shared inquiry graph (control-plane view).

Aggregates the event log + state projection into a status snapshot: hypotheses by
state, contributing agents, saturation signal, near-duplicates, and recent activity.
Pure — no mutation, no provider calls.
"""
from inquiry import saturation


def summary(events, state, window=3, threshold=0.5, recent=10):
    by_status = {}
    for hypothesis in state.hypotheses.values():
        by_status[hypothesis.status] = by_status.get(hypothesis.status, 0) + 1
    agents = sorted({event['actor'] for event in events
                     if str(event.get('actor', '')).startswith('agent:')})
    activity = [dict(seq=event['seq'], at=event['at'], actor=event['actor'],
                     kinds=[change['kind'] for change in event['changes']])
                for event in events[-recent:]]
    return dict(
        inquiry_id=state.inquiry_id,
        hypotheses=len(state.hypotheses),
        by_status=by_status,
        agents=agents,
        saturation=saturation.compute_saturation(events, window),
        duplicates=saturation.find_near_duplicates(state, threshold),
        recent_activity=activity,
    )


_STATUS_ORDER = ('suggested', 'exploring', 'supported', 'contested',
                 'suspended', 'refuted', 'synthesized', 'human-closed')


def render_text(data) -> str:
    """Human-readable control-plane dashboard from a `summary()` dict."""
    if not data.get('inquiry_id'):
        return 'No inquiry yet — the human bootstraps it with `inquiry init`.'
    lines = [f"Inquiry {data['inquiry_id']}  —  {data['hypotheses']} hypotheses"]

    by_status = data['by_status']
    ordered = [name for name in _STATUS_ORDER if name in by_status]
    ordered += [name for name in by_status if name not in _STATUS_ORDER]
    status_line = ' · '.join(f'{name} {by_status[name]}' for name in ordered) or '(none)'
    lines.append(f"Status:  {status_line}")
    lines.append(f"Agents:  {', '.join(data['agents']) or '(none)'}")

    sat = data['saturation']
    if sat['saturated']:
        lines.append(f"Saturation:  ⚠ SATURATED — {'; '.join(sat['reasons'])}")
    else:
        lines.append(f"Saturation:  ok (runs {sat['runs_in_window']}/{sat['window']}, "
                     f"new-info {sat['new_info']})")

    dups = data['duplicates']
    lines.append(f"Near-duplicates ({len(dups)}):"
                 + ('' if dups else ' none'))
    for dup in dups:
        lines.append(f"  - {dup['a']} ~ {dup['b']}  ({dup['score']})")

    lines.append("Recent:" + ('' if data['recent_activity'] else ' (no activity)'))
    for entry in data['recent_activity']:
        lines.append(f"  seq {entry['seq']:>3}  {entry['actor']:<18} {', '.join(entry['kinds'])}")
    return '\n'.join(lines)


def _creators(events):
    """Map hypothesis_id -> the actor whose event created it."""
    out = {}
    for event in events:
        for change in event['changes']:
            if change.get('kind') == 'HypothesisCreated':
                out[change['hypothesis_id']] = event['actor']
    return out


def review(events, state, threshold=0.5):
    """Human-gate triage: what agent output awaits a human decision, grouped by action.

    Agents only propose/explore (D5 _AGENT_EDGES); terminal decisions are the human's.
    This surfaces where that judgment is now due, with the proposing agent + evidence.
    """
    creators = _creators(events)
    dup_ids = set()
    for pair in saturation.find_near_duplicates(state, threshold):
        dup_ids.update((pair['a'], pair['b']))
    evidence_by_hyp = {}
    for link in state.evidence_links:
        evidence_by_hyp.setdefault(link.hypothesis_id, []).append(
            dict(evidence_id=link.evidence_id, relation=link.relation))

    groups = {'triage': [], 'decide': [], 'resolve': []}
    for hypothesis in state.hypotheses.values():
        evidence = evidence_by_hyp.get(hypothesis.id, [])
        item = dict(id=hypothesis.id, title=hypothesis.title, claim=hypothesis.claim,
                    status=hypothesis.status, proposed_by=creators.get(hypothesis.id),
                    evidence=evidence, near_duplicate=hypothesis.id in dup_ids)
        if hypothesis.status == 'suggested':
            item['suggested_actions'] = ['start', 'close']
            groups['triage'].append(item)
        elif hypothesis.status == 'exploring' and evidence:
            item['suggested_actions'] = ['support', 'contest', 'refute', 'suspend']
            groups['decide'].append(item)
        elif hypothesis.status == 'contested':
            item['suggested_actions'] = ['support', 'refute', 'synthesize', 'continue']
            groups['resolve'].append(item)
    return groups


_REVIEW_HEADERS = (
    ('triage', 'Triage (agent-proposed, decide to start or close)'),
    ('decide', 'Decide (exploring with evidence — support / contest / refute)'),
    ('resolve', 'Resolve (contested — needs human resolution)'),
)


def render_review(groups) -> str:
    """Human-readable triage surface from a `review()` dict."""
    if not any(groups.values()):
        return 'Nothing awaits a human decision.'
    lines = []
    for key, header in _REVIEW_HEADERS:
        items = groups[key]
        if not items:
            continue
        lines.append(f"{header}  [{len(items)}]")
        for item in items:
            flag = ' ⚠dup' if item['near_duplicate'] else ''
            by = f" by {item['proposed_by']}" if item['proposed_by'] else ''
            lines.append(f"  {item['id']} [{item['status']}]{by}  evidence={len(item['evidence'])}{flag}")
            lines.append(f"      {item['claim']}")
            lines.append(f"      → {' / '.join(item['suggested_actions'])}")
    return '\n'.join(lines)
