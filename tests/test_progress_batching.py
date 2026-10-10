"""Batching/performance regressions with synthetic logs and fake provider events."""
import json
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from inquiry.adapter import RunRequest, unknown_usage
from inquiry.framing import FramingService
from inquiry.openai_adapter import OpenAIAdapter
from inquiry.runs import Runner
from inquiry.store import Store
from tests.test_framing_schema import control


def delta(text):
    return {'type': 'response.output_text.delta', 'delta': text}


def terminal(payload, kind='response.completed'):
    return {'type': kind, 'response': {
        'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(payload)}]}],
        'usage': {'input_tokens': 11, 'output_tokens': 7}}}


class Stream:
    def __init__(self, events):
        self.events = events
        self.response = SimpleNamespace(headers={'x-request-id': 'req-batch'})
        self.closed = False

    def __iter__(self):
        return iter(self.events)

    def close(self):
        self.closed = True


def adapter_for(events, clock=None):
    stream = Stream(events)
    client = SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs: stream), closed=False)
    client.close = lambda: setattr(client, 'closed', True)
    kwargs = {'client_factory': lambda **options: client}
    if clock is not None:
        kwargs['clock'] = clock
    return OpenAIAdapter(SimpleNamespace(api_key='sk-batch-fake-only', model='fake'), **kwargs), stream, client


def request():
    return RunRequest('I-test', 'R-test', 'framing.control', 'fake',
                      {'system': 'system', 'output_schema': {}, 'seed': 'seed', 'qa': []})


def seed_history(root, count=1700):
    """Only synthetic fixture data, written once before exercising the real Store."""
    changes = [dict(kind='RunStarted', run_id='old', operation='diagnostic', model='fake',
                    target_ids=[], session_id=None, max_output_tokens=1000, timeout=60),
               dict(kind='RunDispatched', run_id='old')]
    changes += [dict(kind='RunProgress', run_id='old', text='ab', provider_request_id=None) for _ in range(count)]
    changes += [dict(kind='RunSucceeded', run_id='old', proposal={'ok': True},
                     usage=unknown_usage(), provider_request_id=None)]
    events = [dict(schema_version=1, event_id=f'e-{i}', seq=i, inquiry_id='I-test',
                   actor='agent:runner', at='2026-09-20T00:00:00Z', type='changes-committed', changes=[c])
              for i, c in enumerate(changes, 1)]
    path = Store(root).path
    path.parent.mkdir()
    path.write_text(''.join(json.dumps(e) + '\n' for e in events), encoding='utf-8')


class ProgressBatchingTests(unittest.TestCase):
    def test_saved_timeout_explains_cause_without_writing_or_calling_provider(self):
        from inquiry.interactive import run_conversation
        now = [0.0]
        def events():
            now[0] = 61
            yield delta('late')
        adapter, _, _ = adapter_for(events())
        with tempfile.TemporaryDirectory() as root:
            service = FramingService(root)
            sid = service.start('synthetic seed')
            with patch('inquiry.framing.Runner', side_effect=lambda path: Runner(path, clock=lambda: now[0])):
                service.advance(sid, adapter, timeout=60)
            before = Store(root).path.read_bytes()
            output = []
            def forbidden():
                self.fail('Resume display must not call provider')
            run_conversation(root, adapter_factory=forbidden, read=lambda _: '2', write=output.append)
            text = '\n'.join(output)
            self.assertIn('cancelled / timeout', text)
            self.assertIn('60초', text)
            self.assertIn('Usage: unknown', text)
            self.assertEqual(Store(root).path.read_bytes(), before)

    def test_thousands_of_fast_fragments_produce_few_signals_and_complete_result(self):
        payload = {'answer': 'authoritative full result'}
        adapter, stream, client = adapter_for([delta('x') for _ in range(2050)] + [terminal(payload)], clock=lambda: 0)
        signals = list(adapter.run(request()))
        progress = [s for s in signals if s.kind == 'progress']
        self.assertLessEqual(len(progress), 4)
        self.assertEqual(progress[0].text, 'x')
        self.assertEqual(signals[-1].proposal, payload)
        self.assertEqual(signals[-1].usage['input_tokens'], 11)
        self.assertTrue(stream.closed and client.closed)

    def test_first_text_is_emitted_without_waiting_for_more_provider_data(self):
        def events():
            yield delta('first')
            raise AssertionError('No look-ahead before first progress')
        adapter, stream, client = adapter_for(events())
        iterator = adapter.run(request())
        try:
            self.assertEqual(next(iterator).text, 'first')
        finally:
            iterator.close()
        self.assertTrue(stream.closed and client.closed)

    def test_size_trigger_keeps_order_and_does_not_flush_tail_before_terminal(self):
        adapter, _, _ = adapter_for([delta('first'), delta('a' * 600), delta('b' * 424),
                                     delta('tail'), terminal({'answer': 'complete'})], clock=lambda: 0)
        signals = list(adapter.run(request()))
        self.assertEqual([s.text for s in signals if s.kind == 'progress'], ['first', 'a' * 600 + 'b' * 424])
        self.assertEqual(signals[-1].kind, 'succeeded')

    def test_elapsed_provider_time_flushes_a_batch(self):
        now = [0.0]
        def events():
            yield delta('first')
            now[0] = 0.4
            yield delta('one')
            now[0] = 1.1
            yield delta('two')
            yield terminal({'answer': 'complete'})
        adapter, _, _ = adapter_for(events(), clock=lambda: now[0])
        signals = list(adapter.run(request()))
        self.assertEqual([s.text for s in signals if s.kind == 'progress'], ['first', 'onetwo'])

    def test_slow_consumer_does_not_turn_every_fragment_into_a_write(self):
        now = [0.0]
        adapter, _, _ = adapter_for([delta('first'), delta('a'), delta('b'), terminal({'answer': 'complete'})],
                                    clock=lambda: now[0])
        iterator = adapter.run(request())
        try:
            self.assertEqual(next(iterator).text, 'first')
            now[0] = 100  # Simulated consumer replay/fsync delay, not provider delay.
            result = next(iterator)
            self.assertEqual(result.kind, 'succeeded')
            self.assertEqual(result.usage['output_tokens'], 7)
        finally:
            iterator.close()

    def test_failure_terminal_retains_usage_and_closes_resources_with_buffered_tail(self):
        for kind, reason in (('response.incomplete', 'incomplete'), ('response.failed', 'provider-error')):
            with self.subTest(kind=kind):
                adapter, stream, client = adapter_for([delta('first'), delta('tail'), terminal({}, kind)], clock=lambda: 0)
                signals = list(adapter.run(request()))
                self.assertEqual([s.kind for s in signals], ['progress', 'failed'])
                self.assertEqual(signals[-1].reason, reason)
                self.assertEqual(signals[-1].usage['input_tokens'], 11)
                self.assertTrue(stream.closed and client.closed)

    def test_late_completed_usage_is_not_hidden_behind_buffered_progress(self):
        now = [0.0]
        def events():
            yield delta('first')
            yield delta('tail')
            now[0] = 61
            yield terminal(control())
        adapter, stream, client = adapter_for(events(), clock=lambda: 0)
        with tempfile.TemporaryDirectory() as root:
            service = FramingService(root)
            sid = service.start('synthetic seed')
            with patch('inquiry.framing.Runner', side_effect=lambda path: Runner(path, clock=lambda: now[0])):
                result = service.advance(sid, adapter, timeout=60)
            run = next(iter(service.state().runs.values()))
            self.assertEqual(result['status'], 'cancelled')
            self.assertEqual((run.reason, run.provider_outcome), ('timeout', 'succeeded'))
            self.assertEqual(run.usage['input_tokens'], 11)
            self.assertIsNone(service.state().inquiry)
        self.assertTrue(stream.closed and client.closed)

    def test_large_existing_log_has_bounded_progress_appends_and_preserves_prefix(self):
        with tempfile.TemporaryDirectory() as root:
            seed_history(root)
            original_bytes = Store(root).path.read_bytes()
            service = FramingService(root)
            sid = service.start('synthetic seed')
            adapter, _, _ = adapter_for([delta('ab') for _ in range(1000)] + [terminal(control())], clock=lambda: 0)
            original_append = Store.append
            progress_writes = []
            def append(store, event, expected_seq):
                if any(c['kind'] == 'RunProgress' for c in event['changes']):
                    progress_writes.append(True)
                    # Bound the regression test itself instead of spending a minute on the old bug.
                    self.assertLessEqual(len(progress_writes), 5)
                return original_append(store, event, expected_seq)
            with patch.object(Store, 'append', append):
                result = service.advance(sid, adapter, timeout=60)
            self.assertEqual(len(result['outstanding_questions']), 3)
            self.assertLessEqual(len(progress_writes), 5)
            self.assertTrue(Store(root).path.read_bytes().startswith(original_bytes))
            self.assertIsNone(service.state().inquiry)
