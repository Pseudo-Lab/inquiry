"""Pure framing protocol checks; duplicate checks do not assess semantic novelty."""

from inquiry.llm.adapter import _object, _string


def _strict_object(properties):
    return dict(type='object', properties=properties, required=list(properties),
                additionalProperties=False)


def _text_schema():
    return dict(type='string', minLength=1, pattern=r'\S')


def _texts_schema(minimum=0):
    return dict(type='array', items=_text_schema(), minItems=minimum)


CONTROL_SCHEMA = _strict_object({
    'mode': dict(type='string', enum=['explore', 'decide', 'test']),
    'mode_rationale': _text_schema(),
    'done': dict(type='boolean'),
    'question_rationale': dict(type='string'),
    'questions': dict(_texts_schema(), maxItems=3, uniqueItems=True),
})

FRAME_SCHEMA = _strict_object({
    'central_question': _text_schema(),
    'purpose': _text_schema(),
    'use_context': _text_schema(),
    'current_belief': _text_schema(),
    'criteria': _texts_schema(1),
    'scope': _strict_object({'include': _texts_schema(1), 'exclude': _texts_schema()}),
    'open_questions': _texts_schema(),
    'hypotheses': dict(type='array', minItems=2, maxItems=4, items=_strict_object({
        key: _text_schema() for key in ('candidate_id', 'title', 'claim', 'difference')
    })),
})


def _fields(value, schema):
    if type(value) is not dict or set(value) != set(schema['required']):
        raise ValueError('invalid framing fields')


def _texts(value, minimum=0):
    if type(value) is not list or len(value) < minimum:
        raise ValueError('invalid framing text list')
    for text in value:
        _string(text)


def validate_questions(payload, asked: int) -> dict:
    """Validate one control batch against the number of questions already asked."""
    if type(asked) is not int or not 0 <= asked <= 5:
        raise ValueError('invalid prior question count')
    value = _object(payload)
    _fields(value, CONTROL_SCHEMA)
    if value['mode'] not in ('explore', 'decide', 'test'):
        raise ValueError('invalid framing mode')
    _string(value['mode_rationale'])
    if type(value['done']) is not bool:
        raise ValueError('invalid completion flag')
    questions = value['questions']
    _texts(questions)
    if len(set(questions)) != len(questions):
        raise ValueError('duplicate questions')
    if value['done']:
        if asked < 3 or questions or value['question_rationale'] != '':
            raise ValueError('invalid completed question batch')
    else:
        _string(value['question_rationale'])
        minimum, maximum = (3, 3) if asked == 0 else (1, min(2, 5 - asked))
        if not minimum <= len(questions) <= maximum:
            raise ValueError('invalid question batch size')
    return value


def validate_frame(payload) -> dict:
    """Return a detached eight-field frame, rejecting normalized exact duplicates."""
    value = _object(payload)
    _fields(value, FRAME_SCHEMA)
    for key in ('central_question', 'purpose', 'use_context', 'current_belief'):
        _string(value[key])
    _texts(value['criteria'], 1)
    _texts(value['open_questions'])
    _fields(value['scope'], FRAME_SCHEMA['properties']['scope'])
    _texts(value['scope']['include'], 1)
    _texts(value['scope']['exclude'])
    hypotheses = value['hypotheses']
    if type(hypotheses) is not list or not 2 <= len(hypotheses) <= 4:
        raise ValueError('invalid hypothesis count')
    schema = FRAME_SCHEMA['properties']['hypotheses']['items']
    for hypothesis in hypotheses:
        _fields(hypothesis, schema)
        for text in hypothesis.values():
            _string(text)
    for key in ('candidate_id', 'title', 'claim'):
        values = [hypothesis[key] for hypothesis in hypotheses]
        if key != 'candidate_id':
            values = [' '.join(text.split()).casefold() for text in values]
        if len(set(values)) != len(values):
            raise ValueError('duplicate hypothesis field')
    return value
