"""Offline contract tests for the bounded OpenAI Responses adapter."""
import json
import logging
import os
import unittest
from unittest.mock import patch

from inquiry.adapter import RunRequest
from inquiry.config import OpenAISettings


def request(**changes):
    value = dict(inquiry_id='I-1', run_id='R-1', operation='framing.control',
                 model='test-model', context=dict(system='system prompt', seed='seed', qa=[],
                 output_schema=dict(type='object', properties=dict(answer=dict(type='string')),
                                    required=['answer'], additionalProperties=False)),
                 timeout=8.0)
    value.update(changes)
    return RunRequest(**value)


class FakeStream:
    def __init__(self, events, request_id='req-offline'):
        self.events = events
        self.response = type('Response', (), {'headers': {'x-request-id': request_id}})()
        self.closed = False

    def __iter__(self):
        return iter(self.events)

    def close(self):
        self.closed = True


class FakeClient:
    def __init__(self, stream):
        self.responses = type('Responses', (), {'create': self.create})()
        self.stream = stream
        self.calls = []
        self.closed = False

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.stream

    def close(self):
        self.closed = True


def completed(payload, *, input_tokens=3, output_tokens=2):
    return {'type': 'response.completed', 'response': {
        'status': 'completed', 'output': [{'type': 'message', 'content': [
            {'type': 'output_text', 'text': json.dumps(payload)}]}],
        'usage': {'input_tokens': input_tokens, 'output_tokens': output_tokens}}}


class OpenAIAdapterTests(unittest.TestCase):
    def adapter(self, events, request_id='req-offline'):
        from inquiry.openai_adapter import OpenAIAdapter
        stream = FakeStream(events, request_id)
        client = FakeClient(stream)
        received = []

        def factory(**kwargs):
            received.append(kwargs)
            return client

        return OpenAIAdapter(OpenAISettings('sk-test-secret', 'settings-model'),
                             client_factory=factory), client, stream, received

    def test_completed_response_uses_final_output_and_closes_resources(self):
        adapter, client, stream, factories = self.adapter([
            {'type': 'response.output_text.delta', 'delta': ' '},
            {'type': 'response.output_text.delta', 'delta': '{bad'},
            completed({'answer': 'final'})])

        signals = list(adapter.run(request()))

        self.assertEqual([signal.kind for signal in signals], ['progress', 'succeeded'])
        self.assertEqual(signals[0].text, '{bad')
        self.assertEqual(signals[1].proposal, {'answer': 'final'})
        self.assertEqual(signals[1].usage['input_tokens'], 3)
        self.assertEqual(signals[1].provider_request_id, 'req-offline')
        self.assertTrue(client.closed)
        self.assertTrue(stream.closed)
        self.assertEqual(factories[0]['api_key'], 'sk-test-secret')
        self.assertEqual(factories[0]['base_url'], 'https://api.openai.com/v1')
        self.assertEqual(factories[0]['max_retries'], 0)
        self.assertLessEqual(factories[0]['timeout'], 8.0)
        body = client.calls[0]
        self.assertEqual(body['model'], 'test-model')
        self.assertFalse(body['store'])
        self.assertTrue(body['stream'])
        self.assertNotIn('tools', body)
        self.assertNotIn('background', body)
        self.assertNotIn('previous_response_id', body)
        self.assertEqual(body['text']['format']['type'], 'json_schema')

    def test_rejected_feedback_is_included_in_framing_payload(self):
        adapter, client, _, _ = self.adapter([completed({'answer': 'final'})])
        feedback = [dict(frame={'central_question': 'q'}, reason='4번은 없애고싶어')]
        req = request(operation='framing.propose',
                      context=dict(system='s', seed='seed', qa=[], rejected=feedback,
                                   output_schema=dict(type='object',
                                                      properties=dict(answer=dict(type='string')),
                                                      required=['answer'], additionalProperties=False)))
        list(adapter.run(req))
        payload = json.loads(client.calls[0]['input'])
        self.assertEqual(payload['rejected'], feedback)

    def test_rejects_invalid_json_without_losing_completed_usage(self):
        adapter, _, _, _ = self.adapter([completed({'answer': float('nan')})])
        # json.dumps emits NaN by default: the strict decoder must reject it.
        signals = list(adapter.run(request()))
        self.assertEqual(signals[0].kind, 'failed')
        self.assertEqual(signals[0].reason, 'invalid-response')
        self.assertEqual(signals[0].usage['status'], 'known')

    def test_ignores_protocol_and_reasoning_events_before_final_message(self):
        adapter, _, _, _ = self.adapter([
            {'type': 'response.created'},
            {'type': 'response.reasoning.delta', 'delta': 'private reasoning'},
            {'type': 'response.output_item.added'},
            {'type': 'response.output_text.delta', 'delta': 'answering'},
            {'type': 'response.output_text.done'},
            completed({'answer': 'final'})])
        signals = list(adapter.run(request()))
        self.assertEqual([item.kind for item in signals], ['progress', 'succeeded'])

    def test_refusal_unknown_and_eof_are_safe_failures(self):
        cases = [
            ([{'type': 'response.refusal.delta', 'delta': 'no'}], 'refusal'),
            ([{'type': 'response.weird'}], 'invalid-response'),
            ([], 'missing-terminal-response'),
        ]
        for events, reason in cases:
            with self.subTest(reason=reason):
                adapter, _, _, _ = self.adapter(events)
                signals = list(adapter.run(request()))
                self.assertEqual([(item.kind, item.reason) for item in signals], [('failed', reason)])

    def test_malformed_duplicate_json_and_tool_output_are_rejected(self):
        malformed = {'type': 'response.completed', 'response': {
            'status': 'completed', 'usage': {'input_tokens': 5, 'output_tokens': 1},
            'output': [{'type': 'function_call', 'arguments': '{}'}]}}
        duplicate = {'type': 'response.completed', 'response': {
            'status': 'completed', 'usage': {'input_tokens': 5, 'output_tokens': 1},
            'output': [{'type': 'message', 'content': [{'type': 'output_text',
                'text': '{"answer":"one","answer":"two"}'}]}]}}
        for event in (malformed, duplicate):
            with self.subTest(event=event):
                adapter, _, _, _ = self.adapter([event])
                signal = list(adapter.run(request()))[0]
                self.assertEqual((signal.kind, signal.reason), ('failed', 'invalid-response'))
                self.assertEqual(signal.usage['input_tokens'], 5)

    def test_empty_or_overflow_json_is_rejected_before_runner_validation(self):
        for text in ('{}', '{"answer":1e999}'):
            event = {'type': 'response.completed', 'response': {
                'status': 'completed', 'usage': {'input_tokens': 5, 'output_tokens': 1},
                'output': [{'type': 'message', 'content': [
                    {'type': 'output_text', 'text': text}]}]}}
            with self.subTest(text=text):
                adapter, _, _, _ = self.adapter([event])
                signal = list(adapter.run(request()))[0]
                self.assertEqual((signal.kind, signal.reason), ('failed', 'invalid-response'))
                self.assertEqual(signal.usage['input_tokens'], 5)

    def test_schema_property_names_and_unsafe_request_ids_are_not_rewritten_or_saved(self):
        from inquiry.openai_adapter import _request_id, _server_schema
        schema = {'type': 'object', 'properties': {'title': {'type': 'string', 'title': 'label'}}}
        converted = _server_schema(schema)
        self.assertIn('title', converted['properties'])
        self.assertNotIn('title', converted['properties']['title'])
        stream = FakeStream([], request_id='sk-test-secret')
        self.assertIsNone(_request_id(stream, 'sk-test-secret'))

    def test_stream_connection_error_is_safe_and_sdk_logger_filter_covers_late_handler(self):
        from inquiry.openai_adapter import _suppress_sdk_logs
        error = type('APIConnectionError', (Exception,), {})()
        class BrokenStream(FakeStream):
            def __iter__(self):
                raise error
                yield None
        client = FakeClient(BrokenStream([]))
        from inquiry.openai_adapter import OpenAIAdapter
        adapter = OpenAIAdapter(OpenAISettings('sk-test-secret', 'test-model'),
                                client_factory=lambda **kwargs: client)
        signal = list(adapter.run(request()))[0]
        self.assertEqual((signal.kind, signal.reason), ('failed', 'connection-error'))
        messages = []
        handler = logging.Handler()
        handler.emit = lambda record: messages.append(record.getMessage())
        logger = logging.getLogger('openai._base_client')
        with _suppress_sdk_logs():
            logger.addHandler(handler)
            logger.error('private error')
            logger.removeHandler(handler)
        self.assertEqual(messages, [])

    def test_incomplete_and_failed_terminal_events_keep_reported_usage(self):
        for event_type, reason in (('response.incomplete', 'incomplete'),
                                   ('response.failed', 'provider-error')):
            event = {'type': event_type, 'response': {
                'usage': {'input_tokens': 9, 'output_tokens': 4}}}
            with self.subTest(event_type=event_type):
                adapter, _, _, _ = self.adapter([event])
                signal = list(adapter.run(request()))[0]
                self.assertEqual((signal.kind, signal.reason), ('failed', reason))
                self.assertEqual(signal.usage['input_tokens'], 9)

    def test_create_errors_have_safe_specific_reasons_and_one_attempt(self):
        for name, reason in (('AuthenticationError', 'authentication-error'),
                             ('RateLimitError', 'rate-limited'),
                             ('APITimeoutError', 'timeout')):
            calls = []
            error = type(name, (Exception,), {})()
            class Client:
                def __init__(self):
                    self.closed = False
                    self.responses = type('Responses', (), {'create': self.create})()
                def create(self, **kwargs):
                    calls.append(kwargs)
                    raise error
                def close(self): self.closed = True
            client = Client()
            from inquiry.openai_adapter import OpenAIAdapter
            adapter = OpenAIAdapter(OpenAISettings('sk-test-secret', 'test-model'),
                                    client_factory=lambda **kwargs: client)
            with self.subTest(name=name):
                signal = list(adapter.run(request()))[0]
                self.assertEqual(signal.reason, reason)
                self.assertEqual(len(calls), 1)
                self.assertTrue(client.closed)

    def test_create_keyboard_interrupt_closes_client_and_propagates(self):
        class Client:
            def __init__(self):
                self.closed = False
                self.responses = type('Responses', (), {'create': self.create})()
            def create(self, **kwargs): raise KeyboardInterrupt()
            def close(self): self.closed = True
        client = Client()
        from inquiry.openai_adapter import OpenAIAdapter
        adapter = OpenAIAdapter(OpenAISettings('sk-test-secret', 'test-model'),
                                client_factory=lambda **kwargs: client)
        with self.assertRaises(KeyboardInterrupt):
            list(adapter.run(request()))
        self.assertTrue(client.closed)

    def test_eof_and_close_error_cannot_create_a_graph_or_mask_success(self):
        from inquiry.framing import FramingService
        from inquiry.openai_adapter import OpenAIAdapter
        import tempfile
        class CloseErrorStream(FakeStream):
            def close(self):
                self.closed = True
                raise RuntimeError('cleanup')
        stream = CloseErrorStream([completed({'answer': 'final'})])
        client = FakeClient(stream)
        adapter = OpenAIAdapter(OpenAISettings('sk-test-secret', 'test-model'),
                                client_factory=lambda **kwargs: client)
        self.assertEqual(list(adapter.run(request()))[-1].kind, 'succeeded')
        self.assertTrue(client.closed)
        with tempfile.TemporaryDirectory() as root:
            service = FramingService(root)
            identity = service.start('seed')
            eof = OpenAIAdapter(OpenAISettings('sk-test-secret', 'test-model'),
                                client_factory=lambda **kwargs: FakeClient(FakeStream([])))
            with self.assertRaises(ValueError):
                service.advance(identity, eof, model='test-model')
            self.assertIsNone(service.state().inquiry)

    def test_system_exit_leaves_no_graph_and_requires_explicit_recovery(self):
        from inquiry.framing import FramingService
        from inquiry.openai_adapter import OpenAIAdapter
        from inquiry.runs import Runner
        import tempfile
        class ExitStream(FakeStream):
            def __iter__(self):
                raise SystemExit()
                yield None
        with tempfile.TemporaryDirectory() as root:
            service = FramingService(root)
            identity = service.start('seed')
            adapter = OpenAIAdapter(OpenAISettings('sk-test-secret', 'test-model'),
                                    client_factory=lambda **kwargs: FakeClient(ExitStream([])))
            with self.assertRaises(SystemExit):
                service.advance(identity, adapter, model='test-model')
            self.assertIsNone(service.state().inquiry)
            self.assertEqual(len(Runner(root).recover()), 1)

    def test_custom_header_override_blocks_construction_and_late_dispatch(self):
        from inquiry.openai_adapter import OpenAIAdapter
        with patch.dict(os.environ, {'OPENAI_CUSTOM_HEADERS': 'Authorization: evil'}, clear=False):
            with self.assertRaisesRegex(ValueError, 'custom headers'):
                OpenAIAdapter(OpenAISettings('sk-test-secret', 'test-model'))
        calls = []
        adapter = OpenAIAdapter(OpenAISettings('sk-test-secret', 'test-model'),
                                client_factory=lambda **kwargs: calls.append(kwargs))
        with patch.dict(os.environ, {'OPENAI_CUSTOM_HEADERS': 'Host: evil'}, clear=False):
            signal = list(adapter.run(request()))[0]
        self.assertEqual(signal.reason, 'invalid-request')
        self.assertEqual(calls, [])
