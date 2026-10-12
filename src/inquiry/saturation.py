"""Heuristic saturation & near-duplicate detection (M3 §8). Read-only, flag-not-delete.

v0 heuristics (tunable, see ADR-D11): near-duplicate = normalized token Jaccard over
title+claim; saturation = recent agent runs producing no net-new graph content. Computed
purely over the event log / state projection — nothing is mutated.
"""

# Live hypotheses worth comparing for redundancy (= BRANCH_PARENT_STATES).
ACTIVE_STATES = frozenset({'suggested', 'exploring', 'supported', 'contested'})

# Changes that mean "new information entered the graph" (no delete events exist, so
# a Created/changed event is always net-new).
NET_NEW_KINDS = frozenset({'HypothesisCreated', 'EvidenceCreated', 'EvidenceLinked',
                           'HypothesisStateChanged', 'ConfidenceUpdated'})


def normalize_text(text) -> str:
    return ' '.join((text or '').split()).casefold()


def _tokens(text):
    return set(normalize_text(text).split())


def similarity(a, b) -> float:
    """Normalized token Jaccard. 0.0 when either side is empty."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    union = ta | tb
    return len(ta & tb) / len(union) if union else 0.0


def _text(hypothesis) -> str:
    return f'{hypothesis.title} {hypothesis.claim}'


def find_near_duplicates(state, threshold=0.5):
    """Pairs of active hypotheses whose title+claim similarity meets the threshold."""
    active = [h for h in state.hypotheses.values() if h.status in ACTIVE_STATES]
    pairs = []
    for i in range(len(active)):
        for j in range(i + 1, len(active)):
            score = similarity(_text(active[i]), _text(active[j]))
            if score >= threshold:
                pairs.append(dict(a=active[i].id, b=active[j].id, score=round(score, 3)))
    return sorted(pairs, key=lambda pair: -pair['score'])


def near_duplicate_candidates(state, candidates, parent_id, threshold=0.5):
    """Branch candidates that duplicate an existing active hypothesis (parent excluded —
    a fork legitimately derives from its parent)."""
    others = [h for h in state.hypotheses.values()
              if h.status in ACTIVE_STATES and h.id != parent_id]
    flags = []
    for candidate in candidates:
        text = f"{candidate['title']} {candidate['claim']}"
        for hypothesis in others:
            score = similarity(text, _text(hypothesis))
            if score >= threshold:
                flags.append(dict(candidate_id=candidate['candidate_id'],
                                  similar_hypothesis_id=hypothesis.id, score=round(score, 3)))
    return flags


def candidate_duplicate_ids(near_duplicates):
    """Group near_duplicate_candidates flags into {candidate_id: sorted([hypothesis_id, ...])}
    so a UI can show which existing hypotheses a fork candidate duplicates (B4)."""
    grouped = {}
    for flag in near_duplicates or ():
        grouped.setdefault(flag['candidate_id'], set()).add(flag['similar_hypothesis_id'])
    return {cid: sorted(ids) for cid, ids in grouped.items()}


def _agent_run_start_seqs(events):
    """Seqs of hypothesis.* RunStarted events (framing runs excluded)."""
    seqs = []
    for event in events:
        for change in event['changes']:
            if change.get('kind') == 'RunStarted' and str(change.get('operation', '')).startswith('hypothesis.'):
                seqs.append(event['seq'])
    return seqs


def compute_saturation(events, window=3):
    """True when the last `window` agent runs produced no net-new graph content.

    The window is a seq range (from the Nth-from-last hypothesis.* RunStarted to the end)
    so that net-new content committed by human accept events inside the window is counted.
    """
    starts = _agent_run_start_seqs(events)
    if len(starts) < window:
        return dict(saturated=False, runs_in_window=len(starts), new_info=0,
                    window=window, reasons=['insufficient agent runs'])
    window_start = starts[-window]
    window_events = [event for event in events if event['seq'] >= window_start]
    runs = len(_agent_run_start_seqs(window_events))
    new_info = sum(1 for event in window_events for change in event['changes']
                   if change.get('kind') in NET_NEW_KINDS)
    saturated = runs >= window and new_info == 0
    reasons = []
    if saturated:
        reasons.append(f'last {runs} agent runs added no new hypotheses, evidence, '
                       'links, or state/confidence changes')
    return dict(saturated=saturated, runs_in_window=runs, new_info=new_info,
                window=window, reasons=reasons)


def build_report(events, state, window=3, threshold=0.5):
    """Combined advisory report: saturation signal + near-duplicate clusters."""
    return dict(saturation=compute_saturation(events, window),
                duplicates=find_near_duplicates(state, threshold))
