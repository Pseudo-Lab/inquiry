import copy
import unittest

from inquiry.transitions import STATES, TransitionError, validate_transition


HUMAN_EDGES = {
    ('suggested', 'exploring'), ('suggested', 'human-closed'),
    ('exploring', 'supported'), ('exploring', 'contested'),
    ('exploring', 'suspended'), ('exploring', 'refuted'),
    ('supported', 'contested'), ('supported', 'synthesized'),
    ('supported', 'human-closed'), ('contested', 'exploring'),
    ('contested', 'supported'), ('contested', 'refuted'),
    ('contested', 'synthesized'), ('suspended', 'exploring'),
    ('refuted', 'exploring'), ('human-closed', 'exploring'),
}
AGENT_EDGES = {('exploring', 'contested'), ('supported', 'contested'),
               ('contested', 'exploring')}


def metadata():
    return {'reason': 'Reviewed evidence.',
            'evidence_snapshot': {'items': [], 'note': 'No evidence recorded.'},
            'reopen_if': 'New evidence arrives.', 'synthesis_target': 'H-merged'}


class TransitionTests(unittest.TestCase):
    def test_exact_states_and_exhaustive_actor_transition_matrix(self):
        self.assertEqual(STATES, frozenset(('suggested', 'exploring', 'supported',
                                         'contested', 'suspended', 'refuted',
                                         'synthesized', 'human-closed')))
        for actor, allowed in [('human:local', HUMAN_EDGES),
                               ('agent:reviewer', AGENT_EDGES),
                               ('system:local', set()), ('unknown', set())]:
            for source in STATES:
                for target in STATES:
                    with self.subTest(actor=actor, source=source, target=target):
                        if (source, target) in allowed:
                            self.assertIsNone(validate_transition(
                                source, target, actor, **metadata()))
                        else:
                            with self.assertRaises(TransitionError):
                                validate_transition(source, target, actor, **metadata())

    def test_rejects_malformed_states_and_actors(self):
        for source, target, actor in [
            ('missing', 'exploring', 'human:a'),
            ('suggested', None, 'human:a'), ([], 'exploring', 'human:a'),
            ('suggested', 'exploring', None),
            *[('suggested', 'exploring', actor)
              for actor in ('human:', 'human:  ', 'agent:', 'Human:a', 'a')],
        ]:
            with self.subTest(actor=actor), self.assertRaises(TransitionError):
                validate_transition(source, target, actor, **metadata())

    def test_every_transition_requires_reason(self):
        for source, target in HUMAN_EDGES:
            for reason in ('', '  ', None, 3):
                data = metadata()
                data['reason'] = reason
                with self.subTest(source=source, target=target, reason=reason):
                    with self.assertRaises(TransitionError):
                        validate_transition(source, target, 'human:a', **data)

    def test_closure_requires_snapshot_and_reopen_condition(self):
        invalid_snapshots = [None, [], {}, {'items': []},
                             {'items': [], 'note': ''},
                             {'items': (), 'note': 'No evidence'},
                             {'items': [], 'note': 'No evidence', 'extra': True},
                             {'items': [], 'note': None}]
        for target in ('refuted', 'human-closed'):
            source = 'contested' if target == 'refuted' else 'suggested'
            for field, values in [('evidence_snapshot', invalid_snapshots),
                                  ('reopen_if', [None, '', ' ', 1])]:
                for value in values:
                    data = metadata()
                    data[field] = value
                    with self.subTest(target=target, field=field, value=value):
                        with self.assertRaises(TransitionError):
                            validate_transition(source, target, 'human:a', **data)

    def test_synthesis_requires_target(self):
        for target in (None, '', ' ', 1):
            with self.subTest(target=target), self.assertRaises(TransitionError):
                validate_transition('supported', 'synthesized', 'human:a',
                                    reason='Merge', synthesis_target=target)

    def test_normal_transition_needs_no_closure_metadata(self):
        validate_transition('suggested', 'exploring', 'human:a', reason='Start')

    def test_does_not_mutate_snapshot(self):
        data = metadata()
        data['evidence_snapshot']['items'] = [{'id': 'E-1', 'source': {'x': 1}}]
        before = copy.deepcopy(data)
        validate_transition('exploring', 'refuted', 'human:a', **data)
        self.assertEqual(data, before)
