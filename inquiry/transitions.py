"""Pure hypothesis state transition guards from ADR-D5."""

STATES = frozenset({'suggested', 'exploring', 'supported', 'contested',
                    'suspended', 'refuted', 'synthesized', 'human-closed'})

_HUMAN_TARGETS = {
    'suggested': {'exploring', 'human-closed'},
    'exploring': {'supported', 'contested', 'suspended', 'refuted'},
    'supported': {'contested', 'synthesized', 'human-closed'},
    'contested': {'exploring', 'supported', 'refuted', 'synthesized'},
    'suspended': {'exploring'},
    'refuted': {'exploring'},
    'human-closed': {'exploring'},
    'synthesized': set(),
}
_AGENT_EDGES = frozenset({('exploring', 'contested'),
                          ('supported', 'contested'),
                          ('contested', 'exploring')})


class TransitionError(ValueError):
    """A state change lacks permission or required decision metadata."""


def _nonempty_string(value):
    return isinstance(value, str) and bool(value.strip())


def validate_transition(from_state, to_state, actor, *, reason='',
                        evidence_snapshot=None, reopen_if=None,
                        synthesis_target=None) -> None:
    """Validate final transitions; callers verify evidence and reopen conditions."""
    if (not isinstance(from_state, str) or from_state not in STATES
            or not isinstance(to_state, str) or to_state not in STATES):
        raise TransitionError('Both states must be valid hypothesis states.')
    if not isinstance(actor, str):
        raise TransitionError('Actor must identify a human or agent.')
    role, separator, name = actor.partition(':')
    if role not in {'human', 'agent'} or not separator or not name.strip():
        raise TransitionError('Actor must be human:<name> or agent:<name>.')
    if to_state not in _HUMAN_TARGETS[from_state]:
        raise TransitionError(f'Transition {from_state!r} -> {to_state!r} is not allowed.')
    if role == 'agent' and (from_state, to_state) not in _AGENT_EDGES:
        raise TransitionError('This transition requires human confirmation.')
    if not _nonempty_string(reason):
        raise TransitionError('Every transition requires a nonempty reason.')
    if to_state in {'refuted', 'human-closed'}:
        if (not isinstance(evidence_snapshot, dict)
                or set(evidence_snapshot) != {'items', 'note'}
                or not isinstance(evidence_snapshot['items'], list)
                or not _nonempty_string(evidence_snapshot['note'])):
            raise TransitionError('Closure requires an evidence snapshot with items and note.')
        if not _nonempty_string(reopen_if):
            raise TransitionError('Closure requires a nonempty reopen condition.')
    if to_state == 'synthesized' and not _nonempty_string(synthesis_target):
        raise TransitionError('Synthesis requires a target hypothesis ID.')
