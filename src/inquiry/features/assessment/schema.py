"""Pure form validation for ADR-D3 assessment axes.

Form only: ranges, source membership, exact fields, explicit-null rule. It does
NOT check evidence_ref existence (N1) nor source monotonicity / "upward move"
(both need prior state — a replay concern). Principle 4 is advisory here: an
unverified flag with no evidence is recorded, never rejected.
"""
from inquiry.llm.adapter import _number, _object, _string


AXES = frozenset({'plausibility', 'evidence_strength', 'novelty', 'impact', 'testability'})

# Trust hierarchy (ADR-D3): agent-estimate < human-judgment < measured-result.
SOURCE_RANK = {'agent-estimate': 0, 'human-judgment': 1, 'measured-result': 2}

_AXIS_FIELDS = frozenset({'low', 'high', 'source', 'evidence_refs', 'unverified', 'rationale'})


def _unit(value, label):
    if not _number(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f'{label} must be a finite number in [0, 1].')


def validate_axis(value):
    """Return a detached axis payload, or None for an unscored axis."""
    if value is None:
        return None
    payload = _object(value)
    if set(payload) != _AXIS_FIELDS:
        raise ValueError('Invalid axis fields.')
    _unit(payload['low'], 'low')
    _unit(payload['high'], 'high')
    if payload['low'] > payload['high']:
        raise ValueError('Axis low must not exceed high.')
    if payload['source'] not in SOURCE_RANK:
        raise ValueError('Unknown axis source.')
    if type(payload['unverified']) is not bool:
        raise ValueError('Axis unverified must be a boolean.')
    _string(payload['rationale'])
    refs = payload['evidence_refs']
    if type(refs) is not list:
        raise ValueError('evidence_refs must be a list.')
    for ref in refs:
        _string(ref)
    return payload


def validate_assessment(payload) -> dict:
    """Return a detached full snapshot; every axis key present, unscored => null."""
    value = _object(payload)
    if set(value) != AXES:
        raise ValueError('Assessment must carry every axis (unscored axes as null).')
    return {name: validate_axis(value[name]) for name in value}


# Axes scored at `suggested`; evidence_strength waits for exploring-phase evidence.
INITIAL_AXES = AXES - {'evidence_strength'}


def validate_initial_output(payload) -> dict:
    """Validate a four-axis initial scoring and return a full snapshot (evidence_strength=null)."""
    value = _object(payload)
    if set(value) != INITIAL_AXES:
        raise ValueError('Initial assessment must score exactly the four non-evidence axes.')
    snapshot = {'evidence_strength': None}
    for name in value:
        score = validate_axis(value[name])
        if score is None:
            raise ValueError('Initial assessment axes must be scored, not null.')
        snapshot[name] = score
    return snapshot
