"""Read-only monitor summary across the shared inquiry graph (control-plane view).

Aggregates the event log + state projection into a status snapshot: hypotheses by
state, contributing agents, saturation signal, near-duplicates, and recent activity.
Pure — no mutation, no provider calls.
"""
from datetime import datetime, timezone

from inquiry import saturation


def agent_activity(events):
    """agent:<name> -> ISO timestamp of its latest event.

    A recency proxy for "which session is working now" (true connected-but-idle
    presence needs a heartbeat/lease — deferred to M4). Events are append-only in
    seq order, so the last write per agent is its latest activity.
    """
    out = {}
    for event in events:
        actor = event.get('actor', '')
        if str(actor).startswith('agent:'):
            out[actor] = event['at']
    return out


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
        agent_last_seen=agent_activity(events),
    )


# Human-readable rendering now lives in the TUI (ADR-D12); `status`/`review` emit JSON for
# machines/orca. The pure aggregation (`summary`/`review`/`_creators`/control-plane helpers)
# below is shared by both.


def _creators(events):
    """Map hypothesis_id -> the actor whose event created it (needs raw events)."""
    out = {}
    for event in events:
        for change in event['changes']:
            if change.get('kind') == 'HypothesisCreated':
                out[change['hypothesis_id']] = event['actor']
    return out


# --- Pure control-plane helpers for the TUI (data source noted per function) ---

_AXIS_SHORT = (('plausibility', 'plaus'), ('evidence_strength', 'evid'),
               ('novelty', 'novel'), ('impact', 'impact'), ('testability', 'test'))


def assessment_summary(hypothesis):
    """One-line confidence ranges from `hypothesis.assessment` (state), or None if unscored."""
    assessment = getattr(hypothesis, 'assessment', None)
    if assessment is None:
        return None
    parts = []
    for name, short in _AXIS_SHORT:
        axis = getattr(assessment, name, None)
        if axis is not None:
            parts.append(f"{short} [{axis.low}–{axis.high}]")
    return '  '.join(parts) if parts else None


_GATE_LABELS = {'triage': 'TRIAGE', 'decide': 'DECIDE', 'resolve': 'RESOLVE'}


def pending_label(hid, review_groups):
    """(GROUP, actions) if the hypothesis awaits a human decision, else None.

    review_groups = review(events, state). Decisions themselves stay in the CLI; this
    only surfaces where a human judgment is due.
    """
    for key, items in review_groups.items():
        for item in items:
            if item['id'] == hid:
                return (_GATE_LABELS[key], item['suggested_actions'])
    return None


def duplicate_peers(duplicates, hid):
    """Ids near-duplicate to hid, from a find_near_duplicates() list."""
    peers = []
    for pair in duplicates:
        if pair['a'] == hid:
            peers.append(pair['b'])
        elif pair['b'] == hid:
            peers.append(pair['a'])
    return peers


def _relative(seconds):
    if seconds < 5:
        return "방금"
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h"
    return f"{int(seconds // 86400)}d"


def _agent_recency(agent, seen, now, active_window):
    """'claude-1 ●방금' / 'codex-2 ○4m' — ● when active within the window, else ○."""
    name = agent.split(':', 1)[-1]
    at = seen.get(agent)
    if not at:
        return name
    delta = (now - datetime.fromisoformat(at.replace('Z', '+00:00'))).total_seconds()
    marker = '●' if delta <= active_window else '○'
    return f"{name} {marker}{_relative(delta)}"


def control_summary_text(data, now=None, active_window=30):
    """One-line control-plane summary for the TUI summary bar (from summary()).

    Agents carry a recency marker so you can see which session is working now: ●
    when it acted within active_window seconds (default 30s), ○ when idle.
    """
    sat = data['saturation']
    sat_txt = '⚠ SATURATED' if sat['saturated'] else 'saturation ok'
    now = now or datetime.now(timezone.utc)
    seen = data.get('agent_last_seen', {})
    agents = ', '.join(_agent_recency(a, seen, now, active_window) for a in data['agents']) or '—'
    return (f"{data['hypotheses']} hypotheses · agents: {agents} · "
            f"{sat_txt} · dup {len(data['duplicates'])}")


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


