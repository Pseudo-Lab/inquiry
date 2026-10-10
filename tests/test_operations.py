import tempfile
import unittest

from inquiry.adapter import RunSignal
from inquiry.commands import Commands
from inquiry.operations import OperationsService
from inquiry.runs import Runner
from inquiry.store import Store
from tests.fakes import FakeAdapter
from tests.operation_fixtures import challenge_output, deepen_output, supported_pair, synthesis_output


def known_usage():
    return dict(status='known', input_tokens=12, output_tokens=7, est_cost=None, price_ref=None)


class OperationsServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name
        self.commands = Commands(self.root)
        self.commands.initialize('seed', {'question': 'question'})
        self.hid = self.commands.add_hypothesis('title', 'claim')
        self.service = OperationsService(self.root)

    def adapter(self, output=None, signals=None):
        return FakeAdapter(signals or [RunSignal('succeeded', proposal=output or deepen_output(),
                                                  usage=known_usage())])

    def propose(self):
        return self.service.propose('deepen', [self.hid], self.adapter())

    def test_deepen_approval_preserves_identity_and_replays(self):
        before = self.commands.state().hypotheses[self.hid]
        proposal = self.propose()
        self.assertEqual(self.service.state().hypotheses[self.hid], before)
        self.assertEqual(self.service.accept(proposal['id']), self.hid)
        node = OperationsService(self.root).state().hypotheses[self.hid]
        self.assertEqual((node.id, node.title, node.claim, node.parent_ids, node.status),
                         (before.id, before.title, before.claim, before.parent_ids, before.status))
        self.assertEqual(node.assumptions, tuple(deepen_output()['assumptions']))
        saved = Store(self.root).path.read_bytes()
        self.assertEqual(self.service.accept(proposal['id']), self.hid)
        self.assertEqual(Store(self.root).path.read_bytes(), saved)

    def test_context_is_minimal_sorted_and_snapshot_is_local(self):
        adapter = self.adapter()
        proposal = self.service.propose('deepen', [self.hid], adapter)
        request = adapter.calls[0]
        self.assertEqual(set(request.context), {'system', 'output_schema', 'inquiry_frame', 'parents'})
        self.assertEqual(request.target_ids, (self.hid,))
        self.assertEqual([p['id'] for p in request.context['parents']], [self.hid])
        self.assertEqual(proposal['target_ids'], [self.hid])
        self.assertTrue(proposal['id'].startswith('OP-'))

    def test_pending_is_offline_stale_and_rejection_is_the_only_write(self):
        proposal = self.propose()
        def forbidden():
            self.fail('pending proposal must not resolve provider')
        self.assertEqual(self.service.propose('deepen', [self.hid], adapter_factory=forbidden)['id'], proposal['id'])
        self.commands.decide(self.hid, 'start')
        self.assertTrue(self.service.view(proposal['id'])['stale'])
        self.assertTrue(self.service.propose('deepen', [self.hid], adapter_factory=forbidden)['stale'])
        before = Store(self.root).path.read_bytes()
        with self.assertRaises(ValueError):
            self.service.accept(proposal['id'])
        self.assertEqual(Store(self.root).path.read_bytes(), before)
        rejected = self.service.reject(proposal['id'], 'source changed')
        self.assertEqual(rejected['status'], 'rejected')
        self.assertGreater(len(Store(self.root).path.read_bytes()), len(before))
        self.assertEqual(self.service.state().hypotheses[self.hid].status, 'exploring')
        with self.assertRaises(ValueError):
            self.service.reject(proposal['id'], 'again')

    def test_duplicate_noop_invalid_output_and_future_operations_leave_graph_unchanged(self):
        original = self.service.state().hypotheses[self.hid]
        invalid = [
            {'assumptions': [], 'falsified_if': [], 'reason': 'noop'},
        ]
        self.commands = Commands(self.root)
        duplicate = self.commands.add_hypothesis('other', 'other', assumptions=('Already there',))
        invalid.append({'assumptions': [' already   THERE '], 'falsified_if': [], 'reason': 'duplicate'})
        for index, output in enumerate(invalid):
            target = duplicate if index == 1 else self.hid
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, 'invalid-proposal'):
                self.service.propose('deepen', [target], self.adapter(output))
        for operation in ('synthesize',):
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                self.service.propose(operation, [self.hid], self.adapter())
        state = self.service.state()
        self.assertFalse(state.operation_proposals)
        self.assertEqual(state.hypotheses[self.hid], original)

    def test_failure_cancellation_and_known_usage_do_not_mutate_hypothesis(self):
        before = self.service.state().hypotheses[self.hid]
        for adapter, cancelled in ((FakeAdapter([RuntimeError('private detail')]), None),
                                   (FakeAdapter([]), lambda: True)):
            with self.assertRaises(ValueError) as caught:
                self.service.propose('deepen', [self.hid], adapter, cancelled=cancelled)
            self.assertNotIn('private detail', str(caught.exception))
        self.assertEqual(self.service.state().hypotheses[self.hid], before)
        self.assertFalse(self.service.state().operation_proposals)
        self.assertEqual(list(self.service.state().runs.values())[-1].usage['status'], 'not-started')
        proposal = self.propose()
        run = self.service.state().runs[proposal['run_id']]
        self.assertEqual(run.usage, known_usage())

    def test_invalid_requests_do_not_resolve_factory_and_interrupted_run_requires_recovery(self):
        calls = []
        def forbidden():
            calls.append(True)
        for operation, targets in [('unknown', [self.hid]), ('deepen', []), ('deepen', ['missing'])]:
            with self.subTest(operation=operation, targets=targets), self.assertRaises(ValueError):
                self.service.propose(operation, targets, adapter_factory=forbidden)
        self.assertFalse(calls)
        with self.assertRaises(SystemExit):
            self.service.propose('deepen', [self.hid], FakeAdapter([SystemExit()]))
        with self.assertRaises(ValueError):
            self.service.propose('deepen', [self.hid], adapter_factory=forbidden)
        self.assertFalse(calls)
        self.assertEqual(len(Runner(self.root).recover()), 1)

    def test_factory_source_change_is_caught_before_dispatch(self):
        adapter = self.adapter()
        def changing_factory():
            self.commands.decide(self.hid, 'start')
            return adapter, 'fake'
        with self.assertRaises(ValueError):
            self.service.propose('deepen', [self.hid], adapter_factory=changing_factory)
        self.assertFalse(adapter.calls)
        self.assertFalse(self.service.state().runs)

    def test_list_and_notes_are_detached_and_notes_remain_empty_for_this_slice(self):
        proposal = self.propose()
        listed = self.service.list_proposals('deepen')
        self.assertEqual([item['id'] for item in listed], [proposal['id']])
        listed[0]['output']['reason'] = 'mutated'
        self.assertEqual(self.service.view(proposal['id'])['output']['reason'], deepen_output()['reason'])
        self.assertEqual(self.service.notes(self.hid), [])
        with self.assertRaises(ValueError):
            self.service.notes('missing')

    def test_synthesis_acceptance_creates_child_and_transitions_all_parents_atomically(self):
        self.temp.cleanup()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name
        first, second = supported_pair(self.root)
        service = OperationsService(self.root)
        proposal = service.propose('synthesize', [second, first], FakeAdapter([
            RunSignal('succeeded', proposal=synthesis_output(), usage=known_usage())]))

        before = service.state()
        result_id = service.accept(proposal['id'])
        after = service.state()

        self.assertEqual(after.hypotheses[result_id].parent_ids, tuple(sorted([first, second])))
        self.assertEqual(after.hypotheses[result_id].status, 'suggested')
        for hypothesis_id in (first, second):
            self.assertEqual(before.hypotheses[hypothesis_id].status, 'supported')
            self.assertEqual(after.hypotheses[hypothesis_id].status, 'synthesized')
            self.assertEqual(after.hypotheses[hypothesis_id].synthesis_target, result_id)
        changes = Store(self.root).read_all()[-1]['changes']
        self.assertEqual([change['kind'] for change in changes], [
            'OperationAccepted', 'HypothesisCreated',
            'HypothesisStateChanged', 'HypothesisStateChanged'])

    def test_interrupted_operations_require_explicit_recovery_without_domain_mutation(self):
        for operation in ('deepen', 'challenge', 'synthesize'):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as root:
                if operation == 'synthesize':
                    targets = supported_pair(root)
                else:
                    commands = Commands(root)
                    commands.initialize('seed', {'question': 'question'})
                    targets = (commands.add_hypothesis('title', 'claim'),)
                service = OperationsService(root)
                before = service.state()
                with self.assertRaises(SystemExit):
                    service.propose(operation, targets, FakeAdapter([SystemExit('interrupted')]))
                paused = service.state()
                self.assertEqual(paused.hypotheses, before.hypotheses)
                self.assertFalse(paused.operation_proposals)
                self.assertEqual(Runner(root).recover(), [next(iter(paused.runs))])
                recovered = service.state()
                self.assertEqual(recovered.hypotheses, before.hypotheses)
                self.assertFalse(recovered.operation_proposals)
                self.assertEqual(Runner(root).totals()['unknown_runs'], 1)

    def test_evidence_added_after_proposal_does_not_make_operation_stale(self):
        proposal = self.propose()
        self.commands.add_evidence(self.hid, 'supports', 'human-judgment', '후속 메모',
                                   '2026-09-25T00:00:00Z')
        self.assertFalse(self.service.view(proposal['id'])['stale'])

    def test_terminal_failures_never_persist_an_operation_proposal(self):
        cases = (
            ('refusal', lambda: FakeAdapter([RunSignal('failed', reason='refusal')])),
            ('invalid-output', lambda: FakeAdapter([RunSignal('succeeded', proposal={})])),
            ('adapter-error', lambda: FakeAdapter([RuntimeError('provider failure')])),
        )
        for operation in ('deepen', 'challenge', 'synthesize'):
            for label, adapter_factory in cases:
                with self.subTest(operation=operation, failure=label), tempfile.TemporaryDirectory() as root:
                    if operation == 'synthesize':
                        targets = supported_pair(root)
                    else:
                        commands = Commands(root)
                        commands.initialize('seed', {'question': 'question'})
                        targets = (commands.add_hypothesis('title', 'claim'),)
                    service = OperationsService(root)
                    before = service.state().hypotheses
                    with self.assertRaises(ValueError):
                        service.propose(operation, targets, adapter_factory())
                    state = service.state()
                    self.assertEqual(state.hypotheses, before)
                    self.assertFalse(state.operation_proposals)


if __name__ == '__main__':
    unittest.main()
