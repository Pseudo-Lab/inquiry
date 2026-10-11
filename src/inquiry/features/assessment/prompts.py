"""Fixed scoring prompts and output schemas for assessment runs.

The anchors below are transcribed from the `assess-hypothesis` skill, which stays
the living rubric of record (ADR-D3): this file is the prompt-content vehicle for
the runtime agent, not a competing source. Keep AXIS_ANCHORS in sync with the
skill's "축별 앵커 사다리"; the output schemas mirror `features/assessment/schema.py`.
"""
from inquiry.features.assessment.schema import AXES, INITIAL_AXES, SOURCE_RANK


SCALE = (
    'Each axis is a [low, high] range over [0,1] on a five-rung ladder: '
    'L0 0.0-0.2 (none/impossible), L1 0.2-0.4 (weak/anecdotal), '
    'L2 0.4-0.6 (mixed/partial), L3 0.6-0.8 (strong/clear), '
    'L4 0.8-1.0 (decisive/inevitable). A sure rung => that band; ambiguity between '
    'adjacent rungs => a range straddling the boundary. Range width = uncertainty; '
    'do not widen it arbitrarily.'
)

# Per-axis anchor ladders, transcribed from assess-hypothesis/SKILL.md (v0).
AXIS_ANCHORS = {
    'plausibility': (
        'plausibility — does the claim\'s causal mechanism hold, assuming zero evidence? '
        'L0 contradicts known facts; L2 plausible and counter-mechanisms roughly even; '
        'L4 near-necessary from established principles.'
    ),
    'evidence_strength': (
        'evidence_strength — how strong is the evidence actually gathered (a BALANCED axis: '
        'reflect both supporting and refuting evidence, never weight refutation alone). '
        'L0 none/speculation; L1 anecdotal/indirect; L2 multiple independent primary sources; '
        'L3 direct observation/pilot data; L4 controlled or replicated measurement. '
        'Direction (supports/challenges) lives in each evidence link\'s relation, not the score.'
    ),
    'novelty': (
        'novelty — does it add a new perspective/information absent from the current graph? '
        'L0 duplicates existing hypotheses/evidence; L2 one new premise on an existing axis; '
        'L4 a fundamentally new direction opening new territory.'
    ),
    'impact': (
        'impact — if true, how much does it move the Inquiry\'s decisions/direction? '
        'L0 changes no decision; L2 redirects one sub-inquiry; L4 redefines the whole Inquiry (go/no-go).'
    ),
    'testability': (
        'testability — can you design an experiment to support/refute it (tied to falsified_if)? '
        'L0 unfalsifiable in principle; L2 only proxy measures; '
        'L4 a decisive experiment runnable right now.'
    ),
}


def _axis_schema():
    return {
        'type': 'object', 'additionalProperties': False,
        'required': ['low', 'high', 'source', 'evidence_refs', 'unverified', 'rationale'],
        'properties': {
            'low': {'type': 'number', 'minimum': 0, 'maximum': 1},
            'high': {'type': 'number', 'minimum': 0, 'maximum': 1},
            'source': {'enum': sorted(SOURCE_RANK)},
            'evidence_refs': {'type': 'array', 'items': {'type': 'string', 'minLength': 1}},
            'unverified': {'type': 'boolean'},
            'rationale': {'type': 'string', 'minLength': 1},
        },
    }


INITIAL_AXIS_NAMES = ('plausibility', 'novelty', 'impact', 'testability')

INITIAL_OUTPUT_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'required': list(INITIAL_AXIS_NAMES),
    'properties': {name: _axis_schema() for name in INITIAL_AXIS_NAMES},
}

SINGLE_AXIS_OUTPUT_SCHEMA = _axis_schema()


def _system(intro, axes):
    return intro + ' ' + SCALE + ' Axes:\n- ' + '\n- '.join(AXIS_ANCHORS[name] for name in axes) \
        + '\nSet source to "agent-estimate".'


ASSESS_SYSTEM = _system(
    'Score this hypothesis on four ADR-D3 axes as an agent-estimate, each with a '
    'rationale. Do not score evidence_strength (no evidence yet).',
    INITIAL_AXIS_NAMES)

REASSESS_SYSTEM = _system(
    'Re-score only evidence_strength for this hypothesis from the external evidence '
    'now linked to it, returning one range with a rationale and the cited evidence_refs.',
    ('evidence_strength',))


# Guard: prompts must cover exactly the D3 axes and the initial subset.
assert set(AXIS_ANCHORS) == AXES
assert set(INITIAL_AXIS_NAMES) == INITIAL_AXES
