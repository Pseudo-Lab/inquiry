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
