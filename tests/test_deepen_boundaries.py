"""Cross-feature and interruption boundaries on temporary inquiry logs."""
import tempfile
import unittest
from unittest.mock import patch

from inquiry.adapter import RunSignal
from inquiry.branch import BranchService
from inquiry.commands import Commands
from inquiry.operations import OperationsService
from inquiry.runs import Runner
from inquiry.store import Store
from tests.branch_fixtures import branch_output
from tests.fakes import FakeAdapter
from tests.operation_fixtures import deepen_output


class DeepenBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name
        commands = Commands(self.root)
        commands.initialize('seed', {'question': 'question'})
        self.hid = commands.add_hypothesis('title', 'claim')
        self.service = OperationsService(self.root)

    def propose(self):
        return self.service.propose('deepen', [self.hid],
            FakeAdapter([RunSignal('succeeded', proposal=deepen_output())]))

    def test_deepen_approval_invalidates_saved_branch_without_mutating_it(self):
        branch = BranchService(self.root)
        proposal = branch.propose(self.hid, FakeAdapter([RunSignal('succeeded', proposal=branch_output())]))
        self.service.accept(self.propose()['id'])
        self.assertTrue(branch.view(proposal['id'])['stale'])
        before = Store(self.root).path.read_bytes()
        with self.assertRaises(ValueError):
            branch.accept(proposal['id'], ['C-1'])
        self.assertEqual(Store(self.root).path.read_bytes(), before)
        self.assertEqual(len(self.service.state().hypotheses), 1)

    def test_late_success_retains_usage_without_saving_proposal(self):
        now = [0.0]
        usage = dict(status='known', input_tokens=10, output_tokens=7, est_cost=None, price_ref=None)
        def late(index, request):
            now[0] = 61.0
        adapter = FakeAdapter([RunSignal('succeeded', proposal=deepen_output(), usage=usage)], on_signal=late)
        with patch('inquiry.operations.Runner', side_effect=lambda root: Runner(root, clock=lambda: now[0])):
            with self.assertRaisesRegex(ValueError, 'timeout'):
                self.service.propose('deepen', [self.hid], adapter)
        state = self.service.state()
        run = next(iter(state.runs.values()))
        self.assertEqual((run.status, run.provider_outcome), ('cancelled', 'succeeded'))
        self.assertEqual(run.usage, usage)
        self.assertFalse(state.operation_proposals)
        self.assertEqual(state.hypotheses[self.hid].assumptions, ())
        self.assertTrue(adapter.closed)

    def test_lost_approval_ack_reloads_as_accepted_without_duplicate_write(self):
        proposal = self.propose()
        original = Store.append
        def lose_ack(store, event, expected_seq):
            result = original(store, event, expected_seq)
            if event['changes'][0]['kind'] == 'OperationAccepted':
                raise OSError('synthetic lost acknowledgement')
            return result
        with patch.object(Store, 'append', lose_ack), self.assertRaises(OSError):
            self.service.accept(proposal['id'])
        before = Store(self.root).path.read_bytes()
        self.assertEqual(self.service.accept(proposal['id']), self.hid)
        self.assertEqual(Store(self.root).path.read_bytes(), before)
        self.assertEqual(self.service.state().hypotheses[self.hid].assumptions,
                         tuple(deepen_output()['assumptions']))

    def test_preappend_failure_does_not_claim_approval_or_change_data(self):
        proposal = self.propose()
        before = Store(self.root).path.read_bytes()
        with patch.object(Store, 'append', side_effect=OSError('synthetic write failure')), \
             self.assertRaises(OSError):
            self.service.accept(proposal['id'])
        self.assertEqual(Store(self.root).path.read_bytes(), before)
        self.assertEqual(self.service.view(proposal['id'])['status'], 'pending')
