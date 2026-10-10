import tempfile
import unittest
from unittest.mock import patch

from inquiry.adapter import RunRequest, RunSignal
from inquiry.runs import Runner
from inquiry.store import Store, StoreError
from tests.fakes import FakeAdapter


class RunHookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runner = Runner(self.temp.name)
        self.request = RunRequest('I-hook', 'R-hook', 'test', 'fake', {})
        self.usage = dict(status='known', input_tokens=7, output_tokens=3,
                          est_cost=None, price_ref=None)

    def adapter(self):
        return FakeAdapter([RunSignal('succeeded', proposal={'value': 1}, usage=self.usage)])

    def test_preflight_rejection_does_not_start_or_dispatch(self):
        adapter = self.adapter()
        def reject(state):
            raise ValueError('stale application state')
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.runner.execute(self.request, adapter, preflight=reject)
        self.assertFalse(adapter.calls)
        self.assertEqual(Store(self.temp.name).read_all(), [])

    def test_hook_sees_uncommitted_success_and_keeps_normal_run_contract(self):
        observed = []
        def changes(state, request, proposal):
            observed.append((state.runs[request.run_id].status, proposal))
            return []
        run = self.runner.execute(self.request, self.adapter(), success_changes=changes)
        self.assertEqual(observed, [('started', {'value': 1})])
        self.assertEqual(run.status, 'succeeded')
        self.assertEqual(len(Store(self.temp.name).read_all()), 3)

    def test_bad_output_is_failed_but_actual_usage_is_preserved(self):
        def invalid(state, request, proposal):
            raise ValueError('private model content')
        run = self.runner.execute(self.request, self.adapter(), success_changes=invalid)
        self.assertEqual((run.status, run.reason, run.provider_outcome),
                         ('failed', 'invalid-proposal', 'succeeded'))
        self.assertEqual(run.usage, self.usage)
        self.assertIsNone(run.proposal)
        self.assertNotIn('private model content', Store(self.temp.name).path.read_text())

    def test_hook_cannot_automatically_commit_domain_changes(self):
        run = self.runner.execute(self.request, self.adapter(), success_changes=lambda *args: [
            dict(kind='InquiryCreated', seed='unauthorized', frame={})])
        self.assertEqual(run.reason, 'invalid-proposal')
        self.assertIsNone(self.runner.state().inquiry)

    def test_process_and_store_errors_are_not_misclassified_as_invalid_output(self):
        for error in (SystemExit(7), StoreError('disk failure')):
            with self.subTest(error=type(error).__name__):
                def crash(*args):
                    raise error
                with self.assertRaises(type(error)):
                    self.runner.execute(self.request, self.adapter(), success_changes=crash)
                self.assertEqual(self.runner.get(self.request.run_id).status, 'started')
                self.runner.recover()
                self.request = RunRequest('I-hook', self.request.run_id + 'x', 'test', 'fake', {})

    def test_append_failure_does_not_attempt_a_second_terminal_write(self):
        original = Store.append
        terminals = []
        def fail(store, event, expected_seq):
            if event['changes'][0]['kind'] in ('RunSucceeded', 'RunFailed'):
                terminals.append(event['changes'][0]['kind'])
                raise StoreError('uncertain')
            original(store, event, expected_seq)
        with patch.object(Store, 'append', fail), self.assertRaises(StoreError):
            self.runner.execute(self.request, self.adapter(), success_changes=lambda *args: [])
        self.assertEqual(terminals, ['RunSucceeded'])
