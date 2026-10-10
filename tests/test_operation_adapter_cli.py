"""Deepen routing with fake responses; never real credentials or network."""
import contextlib
import io
import importlib.util
from importlib.metadata import version
import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from inquiry.cli import main
from inquiry.commands import Commands
from inquiry.adapter import RunSignal
from tests.fakes import FakeAdapter
from tests.operation_fixtures import challenge_output, supported_pair, synthesis_output
from tests.test_operation_chat import output


class OperationCLITests(unittest.TestCase):
    def test_challenge_cli_is_offline_after_generation_and_uses_challenge_purpose(self):
        from inquiry.config import OpenAISettings
        with tempfile.TemporaryDirectory() as root:
            commands = Commands(root)
            commands.initialize('seed', {'question': 'q'})
            hid = commands.add_hypothesis('title', 'claim')
            adapter = FakeAdapter([RunSignal('succeeded', proposal=challenge_output())])
            with patch('inquiry.config.load_openai_settings', return_value=OpenAISettings('sk-fake', 'test')), \
                 patch('inquiry.cli._require_openai_sdk'), \
                 patch('inquiry.openai_adapter.OpenAIAdapter', return_value=adapter), \
                 contextlib.redirect_stdout(io.StringIO()) as capture, \
                 contextlib.redirect_stderr(io.StringIO()) as notice:
                main(['--dir', root, 'explore', 'propose', 'challenge', hid])
            proposal = json.loads(capture.getvalue())
            self.assertIn('Challenge generation', notice.getvalue())
            self.assertEqual(adapter.calls[0].operation, 'hypothesis.challenge')
            with patch('inquiry.config.load_openai_settings', side_effect=AssertionError('offline')):
                for args in (('show', proposal['id']), ('notes', hid), ('accept', proposal['id'])):
                    with contextlib.redirect_stdout(io.StringIO()):
                        main(['--dir', root, 'explore', *args])

    def test_propose_show_accept_and_pending_are_offline_except_generation(self):
        with tempfile.TemporaryDirectory() as root:
            commands = Commands(root)
            commands.initialize('seed', {'question': 'q'})
            hid = commands.add_hypothesis('title', 'claim')
            adapter = FakeAdapter([RunSignal('succeeded', proposal=output())])
            def command(*args):
                with contextlib.redirect_stdout(io.StringIO()) as capture:
                    main(['--dir', root, 'explore', *args], adapter=adapter)
                return json.loads(capture.getvalue())
            proposal = command('propose', 'deepen', hid, '--max-output-tokens', '1234')
            self.assertEqual(adapter.calls[0].max_output_tokens, 1234)
            self.assertEqual(adapter.calls[0].operation, 'hypothesis.deepen')
            self.assertEqual(command('propose', 'deepen', hid)['id'], proposal['id'])
            self.assertEqual(command('show', proposal['id'])['status'], 'pending')
            self.assertEqual(command('accept', proposal['id']), {'id': hid})
            self.assertEqual(command('accept', proposal['id']), {'id': hid})
            self.assertEqual(command('notes', hid), [])
            self.assertEqual(len(adapter.calls), 1)

    def test_new_purpose_notice_and_lazy_offline_rejection(self):
        from inquiry.config import OpenAISettings
        with tempfile.TemporaryDirectory() as root:
            commands = Commands(root)
            commands.initialize('seed', {'question': 'q'})
            hid = commands.add_hypothesis('title', 'claim')
            adapter = FakeAdapter([RunSignal('succeeded', proposal=output())])
            with patch('inquiry.config.load_openai_settings', return_value=OpenAISettings('sk-fake-only', 'test')), \
                 patch('inquiry.cli._require_openai_sdk'), \
                 patch('inquiry.openai_adapter.OpenAIAdapter', return_value=adapter), \
                 contextlib.redirect_stdout(io.StringIO()) as capture, \
                 contextlib.redirect_stderr(io.StringIO()) as notice:
                main(['--dir', root, 'explore', 'propose', 'deepen', hid])
            proposal = json.loads(capture.getvalue())
            self.assertIn('Deepen', notice.getvalue())
            self.assertIn('one request', notice.getvalue())
            self.assertNotIn('answered Q&A', notice.getvalue())
            self.assertNotIn('sk-fake-only', notice.getvalue())
            with patch('inquiry.config.load_openai_settings', side_effect=AssertionError('offline')), \
                 contextlib.redirect_stdout(io.StringIO()):
                main(['--dir', root, 'explore', 'reject', proposal['id'], '--reason', 'different approach'])

    def test_resume_is_offline_and_invalid_synthesis_targets_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            with contextlib.redirect_stdout(io.StringIO()) as capture:
                main(['--dir', root, 'explore', 'resume'])
            self.assertEqual(json.loads(capture.getvalue()), {'recovered': []})
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(['--dir', root, 'explore', 'propose', 'synthesize', 'H-001'])

    def test_synthesis_cli_generation_and_approval_are_offline_after_generation(self):
        with tempfile.TemporaryDirectory() as root:
            first, second = supported_pair(root)
            adapter = FakeAdapter([RunSignal('succeeded', proposal=synthesis_output())])
            def command(*args):
                with contextlib.redirect_stdout(io.StringIO()) as capture:
                    main(['--dir', root, 'explore', *args], adapter=adapter)
                return json.loads(capture.getvalue())
            proposal = command('propose', 'synthesize', second, first)
            self.assertEqual(adapter.calls[0].operation, 'hypothesis.synthesize')
            self.assertEqual(proposal['target_ids'], [first, second])
            result = command('accept', proposal['id'])
            self.assertEqual(result, {'id': 'SYN-001'})
            self.assertEqual(command('accept', proposal['id']), result)
            self.assertEqual(len(adapter.calls), 1)

    def test_adapter_transmits_only_frame_and_parent_allowlist(self):
        from inquiry.adapter import RunRequest
        from inquiry.openai_adapter import OpenAIAdapter
        from tests.test_progress_batching import Stream, terminal
        captured = []
        stream = Stream([terminal(output())])
        def create(**kwargs):
            captured.append(kwargs)
            return stream
        client = SimpleNamespace(responses=SimpleNamespace(create=create), close=lambda: None)
        adapter = OpenAIAdapter(SimpleNamespace(api_key='sk-fake-only'), client_factory=lambda **kwargs: client)
        parent = dict(id='H-001', title='t', claim='c', parent_ids=[], status='suggested',
                      assumptions=[], falsified_if=[], history=['PRIVATE'], reason='PRIVATE')
        request = RunRequest('I', 'R', 'hypothesis.deepen', 'fake',
            dict(system='sys', output_schema={}, inquiry_frame={'question': 'q'}, parents=[parent]),
            target_ids=('H-001',))
        signals = list(adapter.run(request))
        self.assertEqual(signals[-1].kind, 'succeeded')
        payload = json.loads(captured[0]['input'])
        self.assertEqual(set(payload), {'inquiry_frame', 'parents'})
        self.assertEqual(set(payload['parents'][0]),
                         {'id', 'title', 'claim', 'parent_ids', 'status', 'assumptions', 'falsified_if'})
        self.assertNotIn('PRIVATE', json.dumps(captured))
        self.assertFalse(captured[0]['store'])
        self.assertTrue(stream.closed)


SDK_AVAILABLE = (importlib.util.find_spec('openai') is not None and
                 tuple(int(p) for p in version('openai').split('.')[:2]) >= (2, 48))


@unittest.skipUnless(SDK_AVAILABLE, 'OpenAI >=2.48 required for SDK transport verification')
class OperationSDKTests(unittest.TestCase):
    def test_real_sdk_challenge_payload_schema_without_network(self):
        import httpx
        from openai import OpenAI
        from inquiry.openai_adapter import OpenAIAdapter
        from inquiry.operations import OperationsService
        captured = []
        response = dict(id='resp_challenge', object='response', created_at=0, model='test-model',
            status='completed', usage=dict(input_tokens=11, output_tokens=9, total_tokens=20),
            output=[dict(type='message', id='msg_challenge', role='assistant', status='completed',
                content=[dict(type='output_text', text=json.dumps(challenge_output()), annotations=[])])])
        event = dict(type='response.completed', response=response, sequence_number=0)
        data = 'event: response.completed\ndata: ' + json.dumps(event) + '\n\n'
        def handle(request):
            captured.append(json.loads(request.content))
            return httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=data)
        def factory(**kwargs):
            return OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handle),
                trust_env=False, follow_redirects=False))
        with tempfile.TemporaryDirectory() as root:
            commands = Commands(root)
            commands.initialize('seed', {'question': 'q'})
            hid = commands.add_hypothesis('title', 'claim')
            commands.decide(hid, 'start', reason='PRIVATE-HISTORY')
            adapter = OpenAIAdapter(SimpleNamespace(api_key='sk-offline-challenge-only'),
                                    client_factory=factory)
            proposal = OperationsService(root).propose(
                'challenge', [hid], adapter, model='test-model')
            self.assertEqual(proposal['status'], 'pending')
            payload = json.loads(captured[0]['input'])
            self.assertEqual(set(payload), {'inquiry_frame', 'parents'})
            self.assertEqual(set(payload['parents'][0]),
                {'id', 'title', 'claim', 'parent_ids', 'status', 'assumptions', 'falsified_if'})
            self.assertNotIn('PRIVATE-HISTORY', json.dumps(captured))
            self.assertNotIn('sk-offline-challenge-only', json.dumps(captured))
            schema = captured[0]['text']['format']['schema']
            self.assertEqual(schema['required'], ['objections'])
            objections = schema['properties']['objections']
            self.assertEqual((objections['minItems'], objections['maxItems']), (1, 3))
            self.assertEqual(set(objections['items']['required']), {'claim', 'reason', 'check'})
            self.assertFalse(objections['items']['additionalProperties'])

    def test_real_sdk_deepen_payload_schema_and_usage_without_network(self):
        import httpx
        from openai import OpenAI
        from inquiry.openai_adapter import OpenAIAdapter
        from inquiry.operations import OperationsService
        captured = []
        response = dict(id='resp_deepen', object='response', created_at=0, model='test-model',
            status='completed', usage=dict(input_tokens=10, output_tokens=8, total_tokens=18),
            output=[dict(type='message', id='msg_deepen', role='assistant', status='completed',
                content=[dict(type='output_text', text=json.dumps(output()), annotations=[])])])
        event = dict(type='response.completed', response=response, sequence_number=0)
        data = 'event: response.completed\ndata: ' + json.dumps(event) + '\n\n'
        def handle(request):
            captured.append(json.loads(request.content))
            return httpx.Response(200, headers={'content-type': 'text/event-stream',
                'x-request-id': 'req_deepen'}, content=data)
        def factory(**kwargs):
            return OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handle),
                trust_env=False, follow_redirects=False))
        with tempfile.TemporaryDirectory() as root:
            commands = Commands(root)
            commands.initialize('seed', {'question': 'q'})
            hid = commands.add_hypothesis('title', 'claim')
            commands.decide(hid, 'start', reason='PRIVATE-HISTORY')
            adapter = OpenAIAdapter(SimpleNamespace(api_key='sk-offline-deepen-only'), client_factory=factory)
            service = OperationsService(root)
            proposal = service.propose('deepen', [hid], adapter, model='test-model')
            self.assertEqual(proposal['status'], 'pending')
            self.assertEqual(len(captured), 1)
            payload = json.loads(captured[0]['input'])
            self.assertEqual(set(payload), {'inquiry_frame', 'parents'})
            self.assertEqual(set(payload['parents'][0]),
                {'id', 'title', 'claim', 'parent_ids', 'status', 'assumptions', 'falsified_if'})
            self.assertNotIn('PRIVATE-HISTORY', json.dumps(captured))
            self.assertNotIn('sk-offline-deepen-only', json.dumps(captured))
            schema = captured[0]['text']['format']['schema']
            self.assertEqual(set(schema['required']), {'assumptions', 'falsified_if', 'reason'})
            self.assertFalse(schema['additionalProperties'])
            run = service.state().runs[proposal['run_id']]
            self.assertEqual(run.usage['input_tokens'], 10)
            self.assertEqual(run.provider_request_id, 'req_deepen')
