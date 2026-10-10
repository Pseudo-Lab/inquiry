"""Real SDK SSE parsing through an in-memory HTTP transport; never the network."""
import importlib.util
from importlib.metadata import version
import json
import logging
import os
import tempfile
import unittest
from unittest.mock import patch

SDK_AVAILABLE = (importlib.util.find_spec('openai') is not None and
                 tuple(int(part) for part in version('openai').split('.')[:2]) >= (2, 48))


@unittest.skipUnless(SDK_AVAILABLE, 'OpenAI SDK >=2.48 is required for transport verification')
class OpenAITransportTests(unittest.TestCase):
    def test_ambient_auth_and_routing_headers_cannot_reach_sdk_transport(self):
        import httpx
        from openai import OpenAI
        from inquiry.config import OpenAISettings
        from inquiry.openai_adapter import OpenAIAdapter
        from tests.test_openai_adapter import completed, request

        calls, factories = [], []
        event = completed({'answer': 'ok'})
        data = 'event: response.completed\ndata: ' + json.dumps(event) + '\n\n'
        def respond(outbound):
            calls.append(outbound)
            return httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=data)
        def factory(**kwargs):
            factories.append(True)
            return OpenAI(**kwargs, http_client=httpx.Client(
                transport=httpx.MockTransport(respond), trust_env=False, follow_redirects=False))
        settings = OpenAISettings('sk-project-header-test-only', 'test-model')
        with patch.dict(os.environ, {'OPENAI_CUSTOM_HEADERS': ''}):
            adapter = OpenAIAdapter(settings, client_factory=factory)
            self.assertEqual(list(adapter.run(request()))[-1].kind, 'succeeded')
        self.assertEqual(calls[0].headers['authorization'], 'Bearer ' + settings.api_key)
        for value in ('Authorization: Bearer sk-environment-test-only',
                      'OpenAI-Organization: org-foreign', 'OpenAI-Project: proj-foreign',
                      'Host: foreign.invalid'):
            with self.subTest(header=value.split(':')[0]), patch.dict(
                    os.environ, {'OPENAI_CUSTOM_HEADERS': value}):
                with self.assertRaises(ValueError) as error:
                    OpenAIAdapter(settings, client_factory=factory)
                self.assertNotIn(value, str(error.exception))
                # An adapter constructed before the environment changed is also blocked.
                signals = list(adapter.run(request()))
                self.assertEqual((signals[-1].kind, signals[-1].reason), ('failed', 'invalid-request'))
                self.assertEqual(os.environ['OPENAI_CUSTOM_HEADERS'], value)
                self.assertEqual(len(calls), 1)
                self.assertEqual(len(factories), 1)

    def test_invalid_unicode_output_preserves_reported_usage(self):
        from inquiry.config import OpenAISettings
        from inquiry.framing import FramingService
        from inquiry.openai_adapter import OpenAIAdapter
        from tests.test_openai_adapter import FakeClient, FakeStream, completed

        client = FakeClient(FakeStream([completed({'value': '\ud800'})]))
        adapter = OpenAIAdapter(OpenAISettings('sk-offline-unicode', 'test-model'),
                                client_factory=lambda **kwargs: client)
        with tempfile.TemporaryDirectory() as root:
            service = FramingService(root)
            identity = service.start('bad output')
            with self.assertRaises(ValueError):
                service.advance(identity, adapter, model='test-model')
            run = next(iter(service.state().runs.values()))
            self.assertEqual(run.status, 'failed')
            self.assertEqual(run.usage['status'], 'known')
            self.assertEqual(run.usage['input_tokens'], 3)
            self.assertIsNone(service.state().inquiry)

    def test_http_failures_do_not_retry_or_expose_provider_error(self):
        import httpx
        from openai import OpenAI
        from inquiry.adapter import RunRequest
        from inquiry.config import OpenAISettings
        from inquiry.openai_adapter import OpenAIAdapter
        from inquiry.framing_schema import CONTROL_SCHEMA

        key = 'sk-offline-http-error-canary'
        class Capture(logging.Handler):
            def __init__(self):
                super().__init__()
                self.messages = []
            def emit(self, record):
                self.messages.append(self.format(record))
        reasons = {401: 'authentication-error', 429: 'rate-limited', 500: 'provider-error',
                   None: 'connection-error', 'timeout': 'timeout'}
        for status in reasons:
            with self.subTest(status=status):
                requests, clients = [], []
                def respond(request):
                    requests.append(request)
                    if status is None:
                        raise httpx.ConnectError(key, request=request)
                    if status == 'timeout':
                        raise httpx.ReadTimeout(key, request=request)
                    return httpx.Response(status, headers={'x-request-id': 'req_error'},
                                          json={'error': {'message': key, 'type': 'test_error'}})
                def factory(**kwargs):
                    previous = kwargs.pop('http_client', None)
                    if previous is not None:
                        previous.close()
                    client = OpenAI(**kwargs, http_client=httpx.Client(
                        transport=httpx.MockTransport(respond), trust_env=False, follow_redirects=False))
                    clients.append(client)
                    return client
                handler = Capture()
                logger = logging.getLogger('openai')
                original_level = logger.level
                logger.setLevel(logging.DEBUG)
                logger.addHandler(handler)
                try:
                    adapter = OpenAIAdapter(OpenAISettings(key, 'test-model'), client_factory=factory)
                    request = RunRequest('I', 'R', 'framing.control', 'test-model',
                                         {'system': 'system', 'seed': 'seed', 'qa': [],
                                          'output_schema': CONTROL_SCHEMA})
                    signals = list(adapter.run(request))
                finally:
                    logger.removeHandler(handler)
                    logger.setLevel(original_level)
                self.assertEqual(len(requests), 1)
                self.assertEqual(signals[-1].kind, 'failed')
                self.assertEqual(signals[-1].reason, reasons[status])
                self.assertNotIn(key, repr(signals))
                self.assertNotIn(key, '\n'.join(handler.messages))
                self.assertTrue(all(client.is_closed() for client in clients))

    def test_sdk_stream_runs_through_framing_and_saves_usage(self):
        import httpx
        from openai import OpenAI
        from inquiry.config import OpenAISettings
        from inquiry.framing import FramingService
        from inquiry.openai_adapter import OpenAIAdapter
        from inquiry.store import Store
        from tests.test_framing_schema import control

        requests = []
        clients = []
        key = 'sk-offline-transport-canary'
        payload = control()
        response = dict(id='resp_test', object='response', created_at=0, status='completed',
                        model='test-model', output=[dict(type='reasoning', id='rs_test', summary=[]),
                        dict(type='message', id='msg_test',
                        role='assistant', status='completed', content=[dict(type='output_text',
                        text=json.dumps(payload), annotations=[])])],
                        usage=dict(input_tokens=13, output_tokens=7, total_tokens=20))
        started = dict(response, status='in_progress', output=[], usage=None)
        events = [dict(type='response.created', response=started, sequence_number=0),
                  dict(type='response.queued', response=started, sequence_number=1),
                  dict(type='response.in_progress', response=started, sequence_number=1),
                  dict(type='response.reasoning_text.delta', delta='private reasoning',
                       item_id='rs_test', output_index=0, content_index=0, sequence_number=2),
                  dict(type='response.reasoning_text.done', text='private reasoning',
                       item_id='rs_test', output_index=0, content_index=0, sequence_number=3),
                  dict(type='response.reasoning_summary_part.done',
                       part=dict(type='summary_text', text='summary'), item_id='rs_test',
                       output_index=0, summary_index=0, sequence_number=4),
                  dict(type='response.output_item.added', sequence_number=2, output_index=0,
                       item=dict(type='message', id='msg_test', role='assistant', status='in_progress', content=[])),
                  dict(type='response.output_text.delta', delta=' ', item_id='msg_test',
                       output_index=0, content_index=0, sequence_number=0),
                  dict(type='response.completed', response=response, sequence_number=1)]
        data = ''.join('event: ' + e['type'] + '\ndata: ' + json.dumps(e) + '\n\n' for e in events)

        def respond(request):
            requests.append(request)
            return httpx.Response(200, headers={'content-type': 'text/event-stream',
                                               'x-request-id': 'req_test'}, content=data)

        def factory(**kwargs):
            previous = kwargs.pop('http_client', None)
            if previous is not None:
                previous.close()
            client = OpenAI(**kwargs, http_client=httpx.Client(
                transport=httpx.MockTransport(respond), trust_env=False, follow_redirects=False))
            clients.append(client)
            return client

        with tempfile.TemporaryDirectory() as root:
            service = FramingService(root)
            identity = service.start('offline SDK test')
            view = service.advance(identity, OpenAIAdapter(OpenAISettings(key, 'test-model'),
                                                          client_factory=factory), model='test-model')
            self.assertEqual(len(view['outstanding_questions']), 3)
            run = next(iter(service.state().runs.values()))
            self.assertEqual(run.status, 'succeeded')
            self.assertEqual(run.provider_request_id, 'req_test')
            self.assertEqual(run.usage['input_tokens'], 13)
            self.assertEqual(run.usage['output_tokens'], 7)
            self.assertNotIn(key, Store(root).path.read_text())
            self.assertIsNone(service.state().inquiry)
        self.assertEqual(len(requests), 1)
        self.assertEqual(str(requests[0].url), 'https://api.openai.com/v1/responses')
        self.assertEqual(requests[0].headers['authorization'], 'Bearer ' + key)
        body = json.loads(requests[0].content)
        self.assertFalse(body['store'])
        self.assertTrue(body['stream'])
        self.assertEqual(body['model'], 'test-model')
        self.assertTrue(all(client.is_closed() for client in clients))
