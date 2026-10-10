from dataclasses import asdict
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from inquiry.adapter import RunRequest, RunSignal, unknown_usage
from inquiry.runs import Runner
from inquiry.store import Store, StoreError
from inquiry.replay import replay, ReplayError
from tests.fakes import FakeAdapter


def usage(inputs=12, outputs=4):
    return dict(status='known', input_tokens=inputs, output_tokens=outputs, est_cost=None, price_ref=None)


class CloseErrorAdapter:
    def __init__(self, close_error, signal=None):
        self.close_error = close_error
        self.signal = signal or RunSignal('succeeded', proposal={'value': 1})

    def run(self, request):
        return self

    def __iter__(self):
        return self

    def __next__(self):
        if isinstance(self.signal, BaseException):
            raise self.signal
        return self.signal

    def close(self):
        raise self.close_error


class RunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runner = Runner(self.root)

    def request(self, identity='R-1'):
        return RunRequest(inquiry_id='I-1', run_id=identity, operation='framing.questions',
                          model='fake-model', context={'seed': 'secret-context-marker'}, timeout=10)

    def test_cleanup_error_preserves_persisted_success_and_redacts_diagnostics(self):
        result = self.runner.execute(self.request(), CloseErrorAdapter(RuntimeError('secret-key')))
        self.assertEqual(result.status, 'succeeded')
        self.assertEqual(Runner(self.root).get('R-1'), result)
        self.assertEqual(self.runner.cleanup_errors, {'R-1': 'RuntimeError'})
        self.assertNotIn('secret-key', Store(self.root).path.read_text())
        self.assertEqual(len(Store(self.root).read_all()), 3)

    def test_cleanup_error_preserves_primary_store_error(self):
        original = Store.append
        failure = StoreError('primary persistence failure')
        def fail_terminal(store, record, expected_seq):
            if record['changes'][0]['kind'] == 'RunSucceeded':
                raise failure
            return original(store, record, expected_seq)
        with patch.object(Store, 'append', fail_terminal), self.assertRaises(StoreError) as caught:
            self.runner.execute(self.request(), CloseErrorAdapter(RuntimeError('secret-key')))
        self.assertIs(caught.exception, failure)
        self.assertEqual(self.runner.get('R-1').status, 'started')
        self.assertEqual(self.runner.cleanup_errors, {'R-1': 'RuntimeError'})

    def test_cleanup_error_preserves_primary_process_exit(self):
        failure = SystemExit(7)
        with self.assertRaises(SystemExit) as caught:
            self.runner.execute(self.request(), CloseErrorAdapter(RuntimeError('secret-key'), failure))
        self.assertIs(caught.exception, failure)
        self.assertEqual(self.runner.cleanup_errors, {'R-1': 'RuntimeError'})

    def test_process_ending_cleanup_error_propagates(self):
        failure = SystemExit(9)
        with self.assertRaises(SystemExit) as caught:
            self.runner.execute(self.request(), CloseErrorAdapter(failure))
        self.assertIs(caught.exception, failure)
        self.assertEqual(self.runner.get('R-1').status, 'succeeded')

    def test_success_persists_proposal_and_usage_atomically_without_graph_change(self):
        adapter = FakeAdapter([RunSignal('progress', text='partial', provider_request_id='p1'),
                               RunSignal('heartbeat'), RunSignal('usage', usage=usage()),
                               RunSignal('succeeded', proposal={'questions': ['question']}, usage=usage())])
        result = self.runner.execute(self.request(), adapter)
        self.assertEqual(result.status, 'succeeded')
        self.assertEqual(result.proposal, {'questions': ['question']})
        self.assertTrue(adapter.closed)
        self.assertEqual(self.runner.totals()['input_tokens'], 12)
        history = Store(self.root).read_all()
        self.assertEqual(history[-1]['changes'][0]['kind'], 'RunSucceeded')
        self.assertEqual(history[-1]['changes'][0]['proposal'], result.proposal)
        self.assertEqual(history[-1]['changes'][0]['usage'], usage())
        self.assertNotIn('secret-context-marker', Store(self.root).path.read_text())
        state = replay(history)
        self.assertIsNone(state.inquiry)
        self.assertFalse(state.hypotheses)
        self.assertEqual(Runner(self.root).get('R-1'), result)
        with self.assertRaises(ValueError):
            self.runner.execute(self.request(), adapter)
        self.assertEqual(len(adapter.calls), 1)

    def test_pre_dispatch_cancel_is_zero_and_does_not_call_adapter(self):
        stop = threading.Event()
        stop.set()
        adapter = FakeAdapter([])
        result = self.runner.execute(self.request(), adapter, cancelled=stop.is_set)
        self.assertEqual(result.status, 'cancelled')
        self.assertEqual(result.usage['status'], 'not-started')
        self.assertEqual(result.usage['input_tokens'], 0)
        self.assertFalse(adapter.calls)

    def test_cancel_after_progress_and_timeout_are_unknown_not_zero(self):
        stop = threading.Event()
        adapter = FakeAdapter([RunSignal('progress', text='partial'),
                               RunSignal('succeeded', proposal={'value': 'late'})],
                              on_signal=lambda i, request: stop.set() if i == 1 else None)
        result = self.runner.execute(self.request(), adapter, cancelled=stop.is_set)
        self.assertEqual(result.status, 'cancelled')
        self.assertIsNone(result.proposal)
        self.assertEqual(result.usage['status'], 'unknown')
        self.assertIsNone(result.usage['input_tokens'])
        clock = [0.0]
        adapter = FakeAdapter([RunSignal('succeeded', proposal={'value': 'late'})],
                              on_signal=lambda i, request: clock.__setitem__(0, 20.0))
        result = Runner(self.root, clock=lambda: clock[0]).execute(self.request('R-2'), adapter)
        self.assertEqual(result.status, 'cancelled')
        self.assertEqual(result.reason, 'timeout')

    def test_process_exit_recovery_is_explicit_idempotent_and_does_not_retry(self):
        adapter = FakeAdapter([RunSignal('progress', text='partial'), SystemExit(7)])
        with self.assertRaises(SystemExit):
            self.runner.execute(self.request(), adapter)
        before = Store(self.root).path.read_bytes()
        self.assertEqual(self.runner.get('R-1').status, 'started')
        self.assertEqual(Store(self.root).path.read_bytes(), before)
        fresh = Runner(self.root)
        self.assertEqual(fresh.recover(), ['R-1'])
        self.assertEqual(fresh.get('R-1').reason, 'process-interrupted')
        self.assertEqual(fresh.get('R-1').usage['status'], 'unknown')
        after = Store(self.root).path.read_bytes()
        self.assertEqual(fresh.recover(), [])
        self.assertEqual(Store(self.root).path.read_bytes(), after)
        self.assertEqual(len(adapter.calls), 1)

    def test_provider_success_before_local_append_is_unknown_after_restart(self):
        original = Store.append
        def crash(store, record, expected_seq):
            if record['changes'][0]['kind'] == 'RunSucceeded':
                raise SystemExit('crash before persistence')
            return original(store, record, expected_seq)
        with patch.object(Store, 'append', crash), self.assertRaises(SystemExit):
            self.runner.execute(self.request(), FakeAdapter([RunSignal('succeeded', proposal={'value': 1}, usage=usage())]))
        self.runner.recover()
        result = self.runner.get('R-1')
        self.assertEqual(result.status, 'failed')
        self.assertEqual(result.provider_outcome, 'unknown')
        self.assertIsNone(result.proposal)
        self.assertIsNone(result.usage['input_tokens'])

    def test_persisted_success_survives_missing_return(self):
        original = Store.append
        def crash(store, record, expected_seq):
            original(store, record, expected_seq)
            if record['changes'][0]['kind'] == 'RunSucceeded':
                raise SystemExit('crash after persistence')
        with patch.object(Store, 'append', crash), self.assertRaises(SystemExit):
            self.runner.execute(self.request(), FakeAdapter([RunSignal('succeeded', proposal={'value': 1}, usage=usage())]))
        self.assertEqual(Runner(self.root).recover(), [])
        self.assertEqual(Runner(self.root).get('R-1').status, 'succeeded')
        self.assertEqual(self.runner.totals()['output_tokens'], 4)

    def test_late_usage_is_counted_once_and_conflict_preserves_bytes(self):
        self.runner.execute(self.request(), FakeAdapter([RuntimeError('sensitive-provider-error')]))
        self.assertEqual(self.runner.totals()['unknown_runs'], 1)
        self.runner.report_usage('R-1', usage(), provider_request_id='p1')
        before = Store(self.root).path.read_bytes()
        self.runner.report_usage('R-1', usage(), provider_request_id='p1')
        self.assertEqual(Store(self.root).path.read_bytes(), before)
        for value in (usage(13), unknown_usage(), usage(True)):
            with self.assertRaises(ValueError):
                self.runner.report_usage('R-1', value)
            self.assertEqual(Store(self.root).path.read_bytes(), before)
        with self.assertRaises(ValueError):
            self.runner.report_usage('R-1', usage(), provider_request_id='another-request')
        self.assertEqual(self.runner.totals()['unknown_runs'], 0)
        self.assertEqual(self.runner.totals()['input_tokens'], 12)
        self.assertNotIn('sensitive-provider-error', Store(self.root).path.read_text())

    def test_known_usage_survives_interruption(self):
        with self.assertRaises(SystemExit):
            self.runner.execute(self.request(), FakeAdapter([RunSignal('usage', usage=usage()), SystemExit()]))
        self.runner.recover()
        self.assertEqual(self.runner.get('R-1').usage, usage())

    def test_missing_terminal_signal_and_bad_signal_fail_without_proposal(self):
        for index, signals in enumerate(([], [RunSignal('succeeded', proposal={})])):
            result = self.runner.execute(self.request(f'R-{index}'), FakeAdapter(signals))
            self.assertEqual(result.status, 'failed')
            self.assertIsNone(result.proposal)

    def test_exit_after_started_before_dispatch_is_conservatively_unknown(self):
        original = Store.append
        adapter = FakeAdapter([])
        def crash(store, record, expected_seq):
            original(store, record, expected_seq)
            if record['changes'][0]['kind'] == 'RunStarted':
                raise SystemExit('started persisted')
        with patch.object(Store, 'append', crash), self.assertRaises(SystemExit):
            self.runner.execute(self.request(), adapter)
        self.assertFalse(adapter.calls)
        self.assertFalse(self.runner.get('R-1').dispatched)
        self.runner.recover()
        self.assertEqual(self.runner.get('R-1').usage['status'], 'unknown')

    def test_actual_subprocess_exit_then_recovery(self):
        script = """
import sys
from inquiry.adapter import RunRequest, RunSignal
from inquiry.runs import Runner
from tests.fakes import FakeAdapter
Runner(sys.argv[1]).execute(RunRequest('I-1','R-child','framing.frame','fake',{}),
                           FakeAdapter([RunSignal('progress',text='partial'),SystemExit(7)]))
"""
        result = subprocess.run([sys.executable, '-c', script, str(self.root)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertEqual(self.runner.get('R-child').status, 'started')
        self.assertEqual(self.runner.recover(), ['R-child'])
        self.assertEqual(self.runner.get('R-child').usage['status'], 'unknown')

    def test_unfinished_run_blocks_new_dispatch_and_wrong_inquiry_has_no_writes(self):
        with self.assertRaises(SystemExit):
            self.runner.execute(self.request(), FakeAdapter([SystemExit()]))
        before = Store(self.root).path.read_bytes()
        adapter = FakeAdapter([])
        with self.assertRaises(ValueError):
            self.runner.execute(self.request('R-2'), adapter)
        self.assertEqual(Store(self.root).path.read_bytes(), before)
        self.assertFalse(adapter.calls)
        self.runner.recover()
        before = Store(self.root).path.read_bytes()
        wrong = RunRequest('OTHER', 'R-2', 'test', 'fake', {})
        with self.assertRaises(ValueError):
            self.runner.execute(wrong, adapter)
        self.assertEqual(Store(self.root).path.read_bytes(), before)

    def test_zero_usage_is_known_and_duplicate_usage_signal_is_not_counted_twice(self):
        result = self.runner.execute(self.request(), FakeAdapter([
            RunSignal('usage', usage=usage(0, 0)), RunSignal('usage', usage=usage(0, 0)),
            RunSignal('succeeded', proposal={'value': 1})]))
        self.assertEqual(result.usage['status'], 'known')
        self.assertEqual(self.runner.totals(), dict(input_tokens=0, output_tokens=0, unknown_runs=0))
        changes = [c for e in Store(self.root).read_all() for c in e['changes']]
        self.assertEqual(sum(c['kind'] == 'RunUsageReported' for c in changes), 1)

    def test_reading_and_recovering_missing_project_creates_nothing(self):
        path = self.root / 'not-created'
        runner = Runner(path)
        self.assertEqual(runner.recover(), [])
        self.assertEqual(runner.totals()['unknown_runs'], 0)
        self.assertFalse(path.exists())

    def test_terminal_run_rejects_forged_progress(self):
        self.runner.execute(self.request(), FakeAdapter([RunSignal('succeeded', proposal={'value': 1})]))
        history = Store(self.root).read_all()
        record = dict(history[-1], event_id='forged', seq=len(history) + 1,
                      changes=[dict(kind='RunProgress', run_id='R-1', text='after terminal', provider_request_id=None)])
        before = Store(self.root).path.read_bytes()
        with Store(self.root) as store, self.assertRaises(ReplayError):
            store.append(record, expected_seq=len(history))
        self.assertEqual(Store(self.root).path.read_bytes(), before)
