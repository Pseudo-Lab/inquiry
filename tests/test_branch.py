import tempfile
import unittest
from unittest.mock import patch

from inquiry.adapter import RunSignal
from inquiry.commands import Commands
from inquiry.runs import Runner
from inquiry.store import Store, StoreError
from tests.branch_fixtures import branch_output
from tests.fakes import FakeAdapter


class BranchServiceTests(unittest.TestCase):
    def setUp(self):
        from inquiry.branch import BranchService
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name
        self.commands = Commands(self.root)
        self.commands.initialize('반복 실수 줄이기', {'central_question': '지침을 어떻게 전달할까?'})
        self.parent = self.commands.add_hypothesis('지침 전달', '문맥 전달 방식을 바꾸면 실수를 줄일 수 있다')
        self.service = BranchService(self.root)

    def adapter(self, output=None):
        return FakeAdapter([RunSignal('succeeded', proposal=output or branch_output(),
            usage=dict(status='known', input_tokens=12, output_tokens=7, est_cost=None, price_ref=None))])

    def propose(self):
        return self.service.propose(self.parent, self.adapter())

    def test_subset_approval_is_atomic_durable_and_idempotent(self):
        from inquiry.branch import BranchService
        parent = self.commands.state().hypotheses[self.parent]
        proposal = self.propose()
        self.assertEqual(len(self.service.state().hypotheses), 1)
        mapping = self.service.accept(proposal['id'], ['C-3', 'C-1'])
        self.assertEqual(list(mapping), ['C-1', 'C-3'])
        state = BranchService(self.root).state()
        self.assertEqual(state.hypotheses[self.parent], parent)
        self.assertEqual(len(state.hypotheses), 3)
        self.assertFalse(state.evidence)
        for identity in mapping.values():
            self.assertEqual(state.hypotheses[identity].parent_ids, (self.parent,))
            self.assertEqual(state.hypotheses[identity].status, 'suggested')
        before = Store(self.root).path.read_bytes()
        self.assertEqual(self.service.accept(proposal['id'], ['C-1', 'C-3']), mapping)
        self.assertEqual(Store(self.root).path.read_bytes(), before)
        with self.assertRaises(ValueError):
            self.service.accept(proposal['id'], ['C-2'])
        self.assertEqual(Store(self.root).path.read_bytes(), before)
        changes = Store(self.root).read_all()[-1]['changes']
        self.assertEqual([c['kind'] for c in changes], ['BranchAccepted', 'HypothesisCreated', 'HypothesisCreated'])

    def test_pending_preview_never_resolves_provider_even_after_source_changes(self):
        proposal = self.propose()
        def forbidden():
            self.fail('Pending proposal must not call provider')
        self.assertEqual(self.service.propose(self.parent, adapter_factory=forbidden)['id'], proposal['id'])
        self.commands.decide(self.parent, 'start')
        self.assertTrue(self.service.view(proposal['id'])['stale'])
        self.assertTrue(self.service.propose(self.parent, adapter_factory=forbidden)['stale'])
        before = Store(self.root).path.read_bytes()
        with self.assertRaises(ValueError):
            self.service.accept(proposal['id'], ['C-1'])
        self.assertEqual(Store(self.root).path.read_bytes(), before)
        self.service.reject(proposal['id'], 'source changed')
        self.assertEqual(self.service.view(proposal['id'])['status'], 'rejected')

    def test_bad_selection_is_rejected_without_writes(self):
        proposal = self.propose()
        before = Store(self.root).path.read_bytes()
        for selection in ([], ['C-9'], ['C-1', 'C-1'], 'C-1', [None]):
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                self.service.accept(proposal['id'], selection)
            self.assertEqual(Store(self.root).path.read_bytes(), before)

    def test_reject_then_explicit_new_proposal_uses_new_ids(self):
        old = self.propose()
        self.service.reject(old['id'], 'another angle')
        with self.assertRaises(ValueError):
            self.service.accept(old['id'], ['C-1'])
        new = self.propose()
        self.assertNotEqual(old['id'], new['id'])
        self.assertNotEqual(old['run_id'], new['run_id'])
        self.assertEqual(len(self.service.state().hypotheses), 1)

    def test_invalid_provider_output_preserves_usage_but_not_graph(self):
        with self.assertRaisesRegex(ValueError, 'invalid-proposal'):
            self.service.propose(self.parent, self.adapter({'candidates': []}))
        state = self.service.state()
        self.assertFalse(state.branch_proposals)
        self.assertEqual(len(state.hypotheses), 1)
        self.assertEqual(next(iter(state.runs.values())).usage['input_tokens'], 12)

    def test_missing_or_inactive_parent_and_invalid_limits_do_not_resolve_provider(self):
        def forbidden():
            self.fail('Invalid request must not resolve provider')
        for args in ({'parent_id': 'missing'}, {'parent_id': self.parent, 'timeout': float('nan')},
                     {'parent_id': self.parent, 'max_output_tokens': True}):
            with self.assertRaises(ValueError):
                self.service.propose(**args, adapter_factory=forbidden)
        self.commands.decide(self.parent, 'close', reason='outside scope', reopen_if='new scope')
        with self.assertRaises(ValueError):
            self.service.propose(self.parent, adapter_factory=forbidden)
        self.assertFalse(self.service.state().runs)

    def test_failure_and_cancel_do_not_create_proposals(self):
        for adapter, cancelled in ((FakeAdapter([RuntimeError('private provider detail')]), None),
                                   (FakeAdapter([]), lambda: True)):
            with self.assertRaises(ValueError) as caught:
                self.service.propose(self.parent, adapter, cancelled=cancelled)
            self.assertNotIn('private provider detail', str(caught.exception))
        self.assertFalse(self.service.state().branch_proposals)
        self.assertEqual(len(self.service.state().hypotheses), 1)
        self.assertEqual(list(self.service.state().runs.values())[-1].usage['status'], 'not-started')

    def test_interrupted_run_needs_explicit_recovery(self):
        with self.assertRaises(SystemExit):
            self.service.propose(self.parent, FakeAdapter([SystemExit()]))
        calls = []
        with self.assertRaises(ValueError):
            self.service.propose(self.parent, adapter_factory=lambda: calls.append(True))
        self.assertFalse(calls)
        self.assertEqual(len(Runner(self.root).recover()), 1)
        self.assertEqual(self.propose()['status'], 'pending')

    def test_saved_proposal_survives_missing_display_without_recalling_model(self):
        original = Store.append
        def crash(store, event, expected_seq):
            original(store, event, expected_seq)
            if any(c['kind'] == 'BranchProposed' for c in event['changes']):
                raise SystemExit('after persistence')
        with patch.object(Store, 'append', crash), self.assertRaises(SystemExit):
            self.propose()
        adapter = self.adapter()
        result = self.service.propose(self.parent, adapter)
        self.assertEqual(result['status'], 'pending')
        self.assertFalse(adapter.calls)

    def test_uncertain_approval_append_is_not_retried(self):
        proposal = self.propose()
        original = Store.append
        calls = []
        def uncertain(store, event, expected_seq):
            calls.append(True)
            original(store, event, expected_seq)
            raise StoreError('uncertain')
        with patch.object(Store, 'append', uncertain), self.assertRaises(StoreError):
            self.service.accept(proposal['id'], ['C-1'])
        self.assertEqual(len(calls), 1)
        mapping = self.service.accept(proposal['id'], ['C-1'])
        self.assertEqual(len(mapping), 1)
        self.assertEqual(len(self.service.state().hypotheses), 2)

    def test_factory_source_change_is_caught_by_locked_preflight(self):
        adapter = self.adapter()
        def changing_factory():
            self.commands.decide(self.parent, 'start')
            return adapter, 'fake'
        with self.assertRaises(ValueError):
            self.service.propose(self.parent, adapter_factory=changing_factory)
        self.assertFalse(adapter.calls)
        self.assertFalse(self.service.state().runs)
