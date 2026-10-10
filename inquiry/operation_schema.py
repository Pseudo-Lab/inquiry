"""Pure schemas and target validation for hypothesis operations."""

from .adapter import _object, _string


ACTIVE_STATES = frozenset({'suggested', 'exploring', 'supported', 'contested'})


def _text_schema():
    return {'type': 'string', 'minLength': 1, 'pattern': r'\S'}


def _text_array():
    return {'type': 'array', 'minItems': 0, 'maxItems': 8, 'items': _text_schema()}


OPERATION_SCHEMAS = {
    'deepen': {
        'type': 'object', 'additionalProperties': False,
        'required': ['assumptions', 'falsified_if', 'reason'],
        'properties': {'assumptions': _text_array(), 'falsified_if': _text_array(),
                       'reason': _text_schema()},
    },
    'challenge': {
        'type': 'object', 'additionalProperties': False,
        'required': ['objections'],
        'properties': {'objections': {
            'type': 'array', 'minItems': 1, 'maxItems': 3,
            'items': {
                'type': 'object', 'additionalProperties': False,
                'required': ['claim', 'reason', 'check'],
                'properties': {key: _text_schema() for key in ('claim', 'reason', 'check')},
            },
        }},
    },
    'synthesize': {
        'type': 'object', 'additionalProperties': False,
        'required': ['title', 'claim', 'assumptions', 'falsified_if', 'reason', 'unresolved'],
        'properties': {'title': _text_schema(), 'claim': _text_schema(),
                       'assumptions': _text_array(), 'falsified_if': _text_array(),
                       'reason': _text_schema(), 'unresolved': _text_array()},
    },
}


def _normalized(value):
    return ' '.join(value.split()).casefold()


def _strings(value, field):
    if type(value) is not list or len(value) > 8:
        raise ValueError(f'{field} must be an array with at most eight items.')
    for item in value:
        _string(item)
    normalized = [_normalized(item) for item in value]
    if len(set(normalized)) != len(normalized):
        raise ValueError(f'{field} contains duplicate items.')


def validate_operation(operation, payload) -> dict:
    """Return a detached, exact operation output without semantic inference."""
    if operation not in OPERATION_SCHEMAS:
        raise ValueError('Unsupported operation.')
    value = _object(payload)
    if operation == 'deepen':
        if set(value) != {'assumptions', 'falsified_if', 'reason'}:
            raise ValueError('Invalid deepen fields.')
        _strings(value['assumptions'], 'assumptions')
        _strings(value['falsified_if'], 'falsified_if')
        _string(value['reason'])
        if not value['assumptions'] and not value['falsified_if']:
            raise ValueError('Deepen must add at least one item.')
    elif operation == 'challenge':
        if set(value) != {'objections'} or type(value['objections']) is not list \
                or not 1 <= len(value['objections']) <= 3:
            raise ValueError('Challenge requires one to three objections.')
        claims = []
        for objection in value['objections']:
            if type(objection) is not dict or set(objection) != {'claim', 'reason', 'check'}:
                raise ValueError('Invalid challenge objection fields.')
            for field in ('claim', 'reason', 'check'):
                _string(objection[field])
            claims.append(_normalized(objection['claim']))
        if len(set(claims)) != len(claims):
            raise ValueError('Challenge contains duplicate claims.')
    else:
        expected = {'title', 'claim', 'assumptions', 'falsified_if', 'reason', 'unresolved'}
        if set(value) != expected:
            raise ValueError('Invalid synthesize fields.')
        for field in ('title', 'claim', 'reason'):
            _string(value[field])
        for field in ('assumptions', 'falsified_if', 'unresolved'):
            _strings(value[field], field)
    return value


def eligible_targets(operation, hypotheses, target_ids) -> tuple:
    """Validate target count, identity, status and return canonical ID order."""
    if operation not in OPERATION_SCHEMAS:
        raise ValueError('Unsupported operation.')
    if not isinstance(target_ids, (list, tuple)):
        raise ValueError('Targets must be a list or tuple.')
    for identity in target_ids:
        _string(identity)
    targets = tuple(sorted(target_ids))
    if len(set(targets)) != len(targets):
        raise ValueError('Targets must be unique.')
    if operation in ('deepen', 'challenge') and len(targets) != 1:
        raise ValueError('Operation requires exactly one target.')
    if operation == 'synthesize' and len(targets) < 2:
        raise ValueError('Synthesis requires at least two different parents.')
    allowed = {'supported', 'contested'} if operation == 'synthesize' else ACTIVE_STATES
    if any(identity not in hypotheses or hypotheses[identity].status not in allowed for identity in targets):
        raise ValueError('Operation target is missing or ineligible.')
    return targets
