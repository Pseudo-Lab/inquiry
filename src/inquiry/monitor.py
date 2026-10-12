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
