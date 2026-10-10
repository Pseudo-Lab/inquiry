"""Pure fork proposal validation and parent context boundaries."""
from dataclasses import asdict
import json

from .adapter import _object, _string


BRANCH_PARENT_STATES = frozenset({'suggested', 'exploring', 'supported', 'contested'})
_CANDIDATE_FIELDS = ('candidate_id', 'title', 'claim', 'difference')
BRANCH_SCHEMA = {
    'type': 'object', 'additionalProperties': False, 'required': ['candidates'],
    'properties': {'candidates': {
        'type': 'array', 'minItems': 2, 'maxItems': 4,
        'items': {'type': 'object', 'additionalProperties': False,
                  'required': list(_CANDIDATE_FIELDS),
                  'properties': {key: {'type': 'string', 'minLength': 1, 'pattern': r'\S'}
                                 for key in _CANDIDATE_FIELDS}},
    }},
}


def validate_branch(payload) -> dict:
    """Return detached JSON; exact duplicate checks do not assess semantic novelty."""
    value = _object(payload)
    if set(value) != {'candidates'}:
        raise ValueError('Invalid branch fields.')
    candidates = value['candidates']
    if type(candidates) is not list or not 2 <= len(candidates) <= 4:
        raise ValueError('Branch requires two to four candidates.')
    for candidate in candidates:
        if type(candidate) is not dict or set(candidate) != set(_CANDIDATE_FIELDS):
            raise ValueError('Invalid branch candidate fields.')
        for text in candidate.values():
            _string(text)
    for key in ('candidate_id', 'title', 'claim'):
        values = [candidate[key] for candidate in candidates]
        if key != 'candidate_id':
            values = [' '.join(text.split()).casefold() for text in values]
        if len(set(values)) != len(values):
            raise ValueError('Duplicate branch candidate field.')
    return value


def parent_snapshot(hypothesis) -> dict:
    """Freeze the complete persisted parent projection as detached JSON."""
    return _object(json.loads(json.dumps(asdict(hypothesis), allow_nan=False)))


def parent_context(snapshot) -> dict:
    """Select only the parent fields needed for candidate generation."""
    return _object({key: snapshot[key] for key in
                    ('id', 'title', 'claim', 'parent_ids', 'status', 'assumptions', 'falsified_if')})
