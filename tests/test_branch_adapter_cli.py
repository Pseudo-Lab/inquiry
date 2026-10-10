import contextlib
import importlib.util
from importlib.metadata import version
import io
import json
import tempfile
import unittest
from unittest.mock import patch

from inquiry.branch import BranchService
from inquiry.cli import main
from inquiry.commands import Commands
from tests.branch_fixtures import branch_output
from tests.test_framing_flow import QueueAdapter


class BranchCLITests(unittest.TestCase):
    def test_production_binding_discloses_branch_context_and_pending_is_offline(self):
        from inquiry.config import OpenAISettings
        with tempfile.TemporaryDirectory() as root:
            commands = Commands(root)
            commands.initialize('seed', {'central_question': 'question'})
            parent = commands.add_hypothesis('parent', 'parent claim')
            adapter = QueueAdapter(branch_output())
            with patch('inquiry.config.load_openai_settings', return_value=OpenAISettings('sk-test-only', 'test-model')), \
                 patch('inquiry.openai_adapter.OpenAIAdapter', return_value=adapter), \
                 patch('importlib.metadata.version', return_value='2.54.0'), \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as error:
                main(['--dir', root, 'branch', 'propose', parent])
            self.assertIn('selected hypothesis content', error.getvalue())
            self.assertNotIn('answered Q&A', error.getvalue())
            self.assertNotIn('sk-test-only', error.getvalue())
            with patch('inquiry.config.load_openai_settings', side_effect=AssertionError('No key lookup')), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                main(['--dir', root, 'branch', 'propose', parent])
            self.assertEqual(json.loads(output.getvalue())['status'], 'pending')
            self.assertEqual(len(adapter.calls), 1)

    def test_propose_show_accept_and_idempotent_restart(self):
        with tempfile.TemporaryDirectory() as root:
            commands = Commands(root)
            commands.initialize('seed', {'central_question': 'question'})
            parent = commands.add_hypothesis('parent', 'parent claim')
            adapter = QueueAdapter(branch_output())
            def command(*args):
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    main(['--dir', root, 'branch', *args], adapter=adapter)
                return json.loads(out.getvalue())
            proposal = command('propose', parent, '--model', 'test-model', '--max-output-tokens', '1234')
            self.assertEqual(proposal['status'], 'pending')
            self.assertEqual(adapter.calls[0].operation, 'hypothesis.fork')
            self.assertEqual(adapter.calls[0].max_output_tokens, 1234)
            self.assertEqual(command('show', proposal['id'])['id'], proposal['id'])
            mapping = command('accept', proposal['id'], 'C-1', 'C-3')
            self.assertEqual(len(mapping), 2)
            self.assertEqual(command('accept', proposal['id'], 'C-3', 'C-1'), mapping)
            self.assertEqual(len(adapter.calls), 1)
            self.assertEqual(len(BranchService(root).state().hypotheses), 3)

    def test_branch_resume_missing_project_is_offline(self):
        with tempfile.TemporaryDirectory() as root, contextlib.redirect_stdout(io.StringIO()) as out:
            main(['--dir', root, 'branch', 'resume'])
            self.assertEqual(json.loads(out.getvalue())['recovered'], [])


SDK_AVAILABLE = (importlib.util.find_spec('openai') is not None and
                 tuple(int(p) for p in version('openai').split('.')[:2]) >= (2, 48))


@unittest.skipUnless(SDK_AVAILABLE, 'OpenAI >=2.48 required for SDK transport verification')
class BranchSDKTests(unittest.TestCase):
    def test_real_sdk_only_transmits_declared_parent_context(self):
        import httpx
        from openai import OpenAI
        from inquiry.config import OpenAISettings
        from inquiry.openai_adapter import OpenAIAdapter

        captured = []
        response = dict(id='resp_branch', object='response', created_at=0, model='test-model',
            status='completed', usage=dict(input_tokens=10, output_tokens=8, total_tokens=18),
            output=[dict(type='message', id='msg_branch', role='assistant', status='completed',
                         content=[dict(type='output_text', text=json.dumps(branch_output()), annotations=[])])])
        event = {'type': 'response.completed', 'response': response, 'sequence_number': 0}
        data = 'event: response.completed\ndata: ' + json.dumps(event) + '\n\n'
        def handle(request):
            captured.append(json.loads(request.content))
            return httpx.Response(200, headers={'content-type': 'text/event-stream', 'x-request-id': 'req_branch'},
                                  content=data)
        def factory(**kwargs):
            return OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handle),
                                                           trust_env=False, follow_redirects=False))
        with tempfile.TemporaryDirectory() as root:
            commands = Commands(root)
            commands.initialize('seed', {'central_question': 'question'})
            parent = commands.add_hypothesis('parent', 'parent claim', assumptions=['assumption'])
            commands.decide(parent, 'start', reason='PRIVATE-HISTORY-MARKER')
            adapter = OpenAIAdapter(OpenAISettings('sk-offline-branch-only', 'test-model'), client_factory=factory)
            result = BranchService(root).propose(parent, adapter, model='test-model')
            self.assertEqual(result['status'], 'pending')
            self.assertEqual(len(captured), 1)
            payload = json.loads(captured[0]['input'])
            self.assertEqual(set(payload), {'inquiry_frame', 'parent'})
            self.assertEqual(set(payload['parent']),
                             {'id', 'title', 'claim', 'parent_ids', 'status', 'assumptions', 'falsified_if'})
            self.assertNotIn('PRIVATE-HISTORY-MARKER', json.dumps(captured))
            self.assertNotIn('sk-offline-branch-only', json.dumps(captured))
            item_schema = captured[0]['text']['format']['schema']['properties']['candidates']['items']
            self.assertIn('title', item_schema['properties'])
            run = BranchService(root).state().runs[result['run_id']]
            self.assertEqual(run.usage['input_tokens'], 10)
            self.assertEqual(run.provider_request_id, 'req_branch')
