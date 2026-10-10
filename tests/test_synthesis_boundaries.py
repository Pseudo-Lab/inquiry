"""Synthesis interruption and cross-operation boundaries on temporary logs."""
import tempfile
import unittest
from unittest.mock import patch

from inquiry.adapter import RunSignal
from inquiry.operations import OperationsService
from inquiry.runs import Runner
from inquiry.store import Store
from tests.fakes import FakeAdapter
from tests.operation_fixtures import deepen_output, supported_pair, synthesis_output


class SynthesisBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name
        self.parents = supported_pair(self.root)
        self.service = OperationsService(self.root)

    def propose(self):
        return self.service.propose('synthesize', self.parents,
            FakeAdapter([RunSignal('succeeded', proposal=synthesis_output())]))

    def test_late_success_keeps_known_usage_without_proposal_or_parent_changes(self):
        now = [0.0]
        usage = dict(status='known', input_tokens=10, output_tokens=7, est_cost=None, price_ref=None)
        adapter = FakeAdapter([RunSignal('succeeded', proposal=synthesis_output(), usage=usage)],
                              on_signal=lambda index, request: now.__setitem__(0, 61.0))
        with patch('inquiry.operations.Runner', side_effect=lambda root: Runner(root, clock=lambda: now[0])):
            with self.assertRaisesRegex(ValueError, 'timeout'):
                self.service.propose('synthesize', self.parents, adapter)
        state = self.service.state()
        run = next(iter(state.runs.values()))
        self.assertEqual((run.status, run.provider_outcome, run.usage), ('cancelled', 'succeeded', usage))
        self.assertFalse(state.operation_proposals)
        self.assertEqual([state.hypotheses[parent].status for parent in self.parents],
                         ['supported', 'supported'])
        self.assertTrue(adapter.closed)

    def test_lost_accept_ack_is_idempotent_and_stales_old_deepen_proposal(self):
        deepen = self.service.propose('deepen', [self.parents[0]],
            FakeAdapter([RunSignal('succeeded', proposal=deepen_output())]))
        synthesis = self.propose()
        original = Store.append

        def lose_ack(store, event, expected_seq):
            result = original(store, event, expected_seq)
            if event['changes'][0]['kind'] == 'OperationAccepted':
                raise OSError('synthetic acknowledgement loss')
            return result

        with patch.object(Store, 'append', lose_ack), self.assertRaises(OSError):
            self.service.accept(synthesis['id'])
        saved = Store(self.root).path.read_bytes()
        result_id = self.service.accept(synthesis['id'])
        self.assertEqual(Store(self.root).path.read_bytes(), saved)
        self.assertEqual(self.service.view(synthesis['id'])['result_id'], result_id)
        self.assertTrue(self.service.view(deepen['id'])['stale'])
        self.service.reject(deepen['id'], 'parent was synthesized')
        self.assertEqual(self.service.view(deepen['id'])['status'], 'rejected')

    def test_preappend_failure_keeps_synthesis_pending_and_preserves_bytes(self):
        proposal = self.propose()
        before = Store(self.root).path.read_bytes()
        with patch.object(Store, 'append', side_effect=OSError('synthetic write failure')), \
             self.assertRaises(OSError):
            self.service.accept(proposal['id'])
        self.assertEqual(Store(self.root).path.read_bytes(), before)
        self.assertEqual(self.service.view(proposal['id'])['status'], 'pending')
        self.assertEqual([self.service.state().hypotheses[parent].status for parent in self.parents],
                         ['supported', 'supported'])


if __name__ == '__main__':
    unittest.main()
