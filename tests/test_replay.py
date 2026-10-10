import copy
import unittest

from inquiry.replay import ReplayError, replay
from tests.test_events import event


class ReplayTests(unittest.TestCase):
    def test_empty_replay(self):
        state = replay([])
        self.assertEqual(state.last_seq, 0)
        self.assertIsNone(state.inquiry)
        self.assertIsNone(state.inquiry_id)

    def test_draft_before_inquiry_and_repeatable_replay(self):
        events = [event(changes=[{'kind': 'FramingStarted', 'session_id': 'S-1', 'seed': 'seed'}])]
        snapshot = copy.deepcopy(events)
        first, second = replay(events), replay(iter(events))
        self.assertEqual(first, second)
        self.assertEqual(first.last_seq, 1)
        self.assertEqual(first.inquiry_id, 'I-001')
        self.assertEqual(first.framing_sessions['S-1'].seed, 'seed')
        self.assertIsNone(first.inquiry)
        self.assertEqual(events, snapshot)
        events[0]['changes'][0]['seed'] = 'mutated'
        self.assertEqual(first.framing_sessions['S-1'].seed, 'seed')

    def test_seq_identity_and_inquiry_mixing(self):
        first = event()
        for following in [event(seq=3), event(seq=2, event_id='event-1'),
                          event(seq=2, inquiry_id='I-other')]:
            with self.subTest(following=following), self.assertRaises(ReplayError) as caught:
                replay([first, following])
            self.assertEqual(caught.exception.line, 2)

    def test_duplicate_creation_is_rejected(self):
        with self.assertRaises(ReplayError):
            replay([event(), event(seq=2)])
        change = {'kind': 'FramingStarted', 'session_id': 'S-1', 'seed': 'seed'}
        with self.assertRaises(ReplayError):
            replay([event(changes=[change, change])])

    def test_invalid_later_change_returns_no_partial_state(self):
        with self.assertRaises(ReplayError) as caught:
            replay([event(), event(seq=2, changes=[{'kind': 'unknown'}])])
        self.assertEqual(caught.exception.line, 2)


if __name__ == '__main__':
    unittest.main()
