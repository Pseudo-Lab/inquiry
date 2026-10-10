"""Cross-operation and storage failure regressions on synthetic data only."""
import json
from copy import deepcopy
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from inquiry.adapter import RunSignal
from inquiry.commands import Commands
from inquiry.operations import OperationsService
from inquiry.runs import Runner
from inquiry.store import Store
from tests.fakes import FakeAdapter
from tests.operation_fixtures import deepen_output


def memo_output():
    return {'objections': [{'claim': 'PRIVATE-MEMO-MARKER',
                            'reason': '검증이 필요하다', 'check': '독립 사례를 비교한다'}]}


class ChallengeBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name
        self.commands = Commands(self.root)
        self.commands.initialize('seed', {'question': 'question'})
        self.hid = self.commands.add_hypothesis('title', 'claim')
        self.service = OperationsService(self.root)

    def propose(self, kind):
        payload = memo_output() if kind == 'challenge' else deepen_output()
        return self.service.propose(kind, [self.hid], FakeAdapter([RunSignal('succeeded', proposal=payload)]))

    def test_memo_approval_keeps_deepen_pending_valid_but_deepen_invalidates_challenge(self):
        before = self.service.state().hypotheses[self.hid]
        deepen = self.propose('deepen')
        challenge = self.propose('challenge')
        self.service.accept(challenge['id'])
        self.assertFalse(self.service.view(deepen['id'])['stale'])
        self.assertEqual(self.service.state().hypotheses[self.hid], before)
        second = self.propose('challenge')
        self.service.accept(deepen['id'])
        self.assertTrue(self.service.view(second['id'])['stale'])
        saved = Store(self.root).path.read_bytes()
        with self.assertRaises(ValueError):
            self.service.accept(second['id'])
        self.assertEqual(Store(self.root).path.read_bytes(), saved)
        self.assertEqual(len(self.service.notes(self.hid)), 1)

    def test_memo_and_provenance_are_not_sent_in_later_generation(self):
        from inquiry.openai_adapter import OpenAIAdapter
        from tests.test_progress_batching import Stream, terminal
        self.service.accept(self.propose('challenge')['id'])
        captured = []
        stream = Stream([terminal(deepen_output())])
        def create(**kwargs):
            captured.append(kwargs)
            return stream
        client = SimpleNamespace(responses=SimpleNamespace(create=create), close=lambda: None)
        adapter = OpenAIAdapter(SimpleNamespace(api_key='sk-synthetic-only'), client_factory=lambda **kwargs: client)
        proposal = self.service.propose('deepen', [self.hid], adapter)
        self.assertEqual(proposal['status'], 'pending')
        self.assertEqual(len(captured), 1)
        sent = json.dumps(captured)
        for private in ('PRIVATE-MEMO-MARKER', 'approved_by', 'approved_at', 'review_notes', 'sk-synthetic-only'):
            self.assertNotIn(private, sent)
        payload = json.loads(captured[0]['input'])
        self.assertEqual(set(payload), {'inquiry_frame', 'parents'})

    def test_lost_ack_leaves_one_note_and_repeated_accept_does_not_append(self):
        proposal = self.propose('challenge')
        original = Store.append
        def lose_ack(store, event, expected_seq):
            result = original(store, event, expected_seq)
            if event['changes'][0]['kind'] == 'OperationAccepted':
                raise OSError('synthetic acknowledgement loss')
            return result
        with patch.object(Store, 'append', lose_ack), self.assertRaises(OSError):
            self.service.accept(proposal['id'])
        saved = Store(self.root).path.read_bytes()
        result = self.service.accept(proposal['id'])
        self.assertEqual(Store(self.root).path.read_bytes(), saved)
        self.assertEqual([note['id'] for note in self.service.notes(self.hid)], [result])

    def test_preappend_failure_preserves_pending_and_creates_no_note(self):
        proposal = self.propose('challenge')
        saved = Store(self.root).path.read_bytes()
        with patch.object(Store, 'append', side_effect=OSError('synthetic write failure')), \
             self.assertRaises(OSError):
            self.service.accept(proposal['id'])
        self.assertEqual(Store(self.root).path.read_bytes(), saved)
        self.assertEqual(self.service.view(proposal['id'])['status'], 'pending')
        self.assertFalse(self.service.notes(self.hid))

    def test_late_success_preserves_known_usage_without_proposal_or_memo(self):
        now = [0.0]
        usage = dict(status='known', input_tokens=10, output_tokens=7, est_cost=None, price_ref=None)
        def late(index, request):
            now[0] = 61
        adapter = FakeAdapter([RunSignal('succeeded', proposal=memo_output(), usage=usage)], on_signal=late)
        with patch('inquiry.operations.Runner', side_effect=lambda root: Runner(root, clock=lambda: now[0])):
            with self.assertRaisesRegex(ValueError, 'timeout'):
                self.service.propose('challenge', [self.hid], adapter)
        state = self.service.state()
        run = next(iter(state.runs.values()))
        self.assertEqual((run.status, run.provider_outcome), ('cancelled', 'succeeded'))
        self.assertEqual(run.usage, usage)
        self.assertFalse(state.operation_proposals)
        self.assertFalse(state.review_notes)
        self.assertEqual(len(state.hypotheses), 1)

    def test_closed_target_review_notes_uses_no_factory_and_does_not_write(self):
        from inquiry.interactive import run_conversation
        proposal = self.propose('challenge')
        nid = self.service.accept(proposal['id'])
        event = Store(self.root).read_all()[-1]
        note = self.service.notes(self.hid)[0]
        self.assertEqual((note['approved_by'], note['approved_at']), (event['actor'], event['at']))
        self.commands.decide(self.hid, 'close', reason='done', reopen_if='new findings')
        saved = Store(self.root).path.read_bytes()
        inputs = iter(['3', '3', '1', '2'])
        lines = []
        def read(_):
            try:
                return next(inputs)
            except StopIteration:
                raise EOFError from None
        def forbidden():
            self.fail('Review Notes must not construct a provider')
        run_conversation(self.root, adapter_factory=forbidden,
            operation_factories={'deepen': forbidden, 'challenge': forbidden}, read=read, write=lines.append)
        self.assertIn('PRIVATE-MEMO-MARKER', '\n'.join(lines))
        self.assertIn(nid, '\n'.join(lines))
        self.assertEqual(Store(self.root).path.read_bytes(), saved)

    def test_different_pending_proposal_cannot_reuse_an_existing_note_id(self):
        first = self.propose('challenge')
        first_note = self.service.accept(first['id'])
        accepted_event = Store(self.root).read_all()[-1]
        second = self.propose('challenge')
        self.assertEqual(self.service.view(second['id'])['status'], 'pending')
        forged = deepcopy(accepted_event)
        forged['event_id'] = 'forged-note-reuse'
        for change in forged['changes']:
            change['proposal_id'] = second['id']
        saved = Store(self.root).path.read_bytes()
        with Store(self.root) as store:
            count = len(store.read_all())
            forged['seq'] = count + 1
            with self.assertRaisesRegex(ValueError, 'Challenge approval'):
                store.append(forged, expected_seq=count)
        self.assertEqual(Store(self.root).path.read_bytes(), saved)
        second_note = self.service.accept(second['id'])
        self.assertNotEqual(first_note, second_note)
        self.assertEqual(len(self.service.notes(self.hid)), 2)
