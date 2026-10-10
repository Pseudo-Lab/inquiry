"""CLI binding tests; all provider behavior is offline and injected."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from inquiry.adapter import RunSignal
from inquiry.config import OpenAISettings
from inquiry.framing import FramingService
from tests.fakes import FakeAdapter
from tests.test_framing_flow import QueueAdapter
from tests.test_framing_schema import control, frame


class OpenAICLITests(unittest.TestCase):
    def test_ambient_headers_block_new_run_but_not_saved_questions(self):
        ambient = 'Authorization: Bearer sk-ambient-cli-only\nHost: foreign.invalid'
        from inquiry.cli import main
        settings = OpenAISettings('sk-project-cli-only', 'test-model')
        with patch.dict(os.environ, {'OPENAI_CUSTOM_HEADERS': ambient}), \
             patch('importlib.metadata.version', return_value='2.48.0'), \
             patch('inquiry.config.load_openai_settings', return_value=settings), \
             patch('inquiry.openai_adapter._production_factory') as factory:
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
                main(['--dir', self.temp.name, 'framing', 'next', self.sid])
            self.assertIn('OPENAI_CUSTOM_HEADERS', stderr.getvalue())
            self.assertNotIn(ambient, stderr.getvalue())
            self.assertNotIn(settings.api_key, stderr.getvalue())
            self.assertFalse(factory.called)
            self.assertFalse(self.service.state().runs)
            self.assertEqual(os.environ['OPENAI_CUSTOM_HEADERS'], ambient)
            view = self.service.advance(self.sid, QueueAdapter(control()))
            with patch('inquiry.config.load_openai_settings') as load:
                restored, notice = self.run_cli('framing', 'next', self.sid)
                self.assertEqual(restored['outstanding_questions'], view['outstanding_questions'])
                self.assertFalse(load.called)
                self.assertEqual(notice, '')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = FramingService(self.temp.name)
        self.sid = self.service.start('private seed')

    def run_cli(self, *arguments, adapter=None):
        from inquiry.cli import main
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            main(['--dir', self.temp.name, *arguments], adapter=adapter)
        return json.loads(stdout.getvalue()), stderr.getvalue()

    def answer_all(self):
        for question in self.service.view(self.sid)['outstanding_questions']:
            self.service.answer(self.sid, question['qid'], 'unknown')

    def prepare_answered_questions(self):
        self.service.advance(self.sid, QueueAdapter(control()))
        self.answer_all()

    def test_saved_views_do_not_load_settings_or_construct_sdk_adapter(self):
        self.service.advance(self.sid, QueueAdapter(control()))
        with patch('inquiry.config.load_openai_settings') as load, \
             patch('inquiry.openai_adapter.OpenAIAdapter') as make:
            self.run_cli('framing', 'next', self.sid)
            self.run_cli('framing', 'show', self.sid)
            self.service.cancel(self.sid)
            self.run_cli('framing', 'resume', self.sid)
            self.assertFalse(load.called)
            self.assertFalse(make.called)

        self.answer_all()
        proposed = self.service.advance(
            self.sid,
            QueueAdapter(control(done=True, questions=[], question_rationale=''), frame()),
        )
        proposal_id = proposed['pending_proposal']['id']
        with patch('inquiry.config.load_openai_settings') as load, \
             patch('inquiry.openai_adapter.OpenAIAdapter') as make:
            self.run_cli('framing', 'next', self.sid)
            self.run_cli('framing', 'accept', self.sid, proposal_id)
            self.assertFalse(load.called)
            self.assertFalse(make.called)

    def test_generation_uses_resolved_model_defaults_and_prints_fixed_notice(self):
        self.prepare_answered_questions()
        adapter = QueueAdapter(control(done=True, questions=[], question_rationale=''), frame())
        settings = OpenAISettings('sk-offline', 'resolved-model')
        with patch('inquiry.config.load_openai_settings', return_value=settings) as load, \
             patch('importlib.metadata.version', return_value='2.48.0'), \
             patch('inquiry.openai_adapter.OpenAIAdapter', return_value=adapter) as make:
            result, notice = self.run_cli('framing', 'next', self.sid)
        self.assertIsNotNone(result['pending_proposal'])
        self.assertEqual(load.call_count, 2)
        self.assertEqual(load.call_args_list[0].kwargs, {'model': None})
        self.assertEqual(make.call_count, 2)
        self.assertEqual([request.model for request in adapter.calls], ['resolved-model'] * 2)
        self.assertEqual([request.max_output_tokens for request in adapter.calls], [4000, 16000])
        self.assertEqual([request.timeout for request in adapter.calls], [60.0, 60.0])
        for phrase in ('OpenAI', 'resolved-model', 'seed', 'Q&A', '4000', '16000',
                       'API', 'cost', 'second'):
            self.assertIn(phrase, notice)
        self.assertNotIn('sk-offline', notice)

    def test_explicit_limits_and_model_override_apply_to_every_generated_run(self):
        self.prepare_answered_questions()
        adapter = QueueAdapter(control(done=True, questions=[], question_rationale=''), frame())
        settings = OpenAISettings('sk-offline', 'override-model')
        with patch('inquiry.config.load_openai_settings', return_value=settings) as load, \
             patch('importlib.metadata.version', return_value='2.48.0'), \
             patch('inquiry.openai_adapter.OpenAIAdapter', return_value=adapter):
            self.run_cli('framing', 'next', self.sid, '--model', 'override-model',
                         '--max-output-tokens', '777', '--timeout', '2.5')
        self.assertEqual(load.call_args_list[0].kwargs, {'model': 'override-model'})
        self.assertTrue(all(request.max_output_tokens == 777 for request in adapter.calls))
        self.assertTrue(all(request.timeout == 2.5 for request in adapter.calls))

    def test_injected_adapter_needs_no_settings_and_defaults_to_fake_model(self):
        adapter = QueueAdapter(control())
        with patch('inquiry.config.load_openai_settings') as load, \
             patch('inquiry.openai_adapter.OpenAIAdapter') as make:
            _, notice = self.run_cli('framing', 'next', self.sid, adapter=adapter)
        self.assertFalse(load.called)
        self.assertFalse(make.called)
        self.assertEqual(adapter.calls[0].model, 'fake')
        self.assertEqual(notice, '')

    def test_invalid_limits_fail_before_provider_resolution_or_run_write(self):
        from inquiry.cli import main
        for option, value in (('--max-output-tokens', '0'), ('--max-output-tokens', '1.5'),
                              ('--timeout', '0'), ('--timeout', 'nan'), ('--timeout', 'inf')):
            with self.subTest(option=option, value=value), \
                 patch('inquiry.config.load_openai_settings') as load, \
                 patch('inquiry.openai_adapter.OpenAIAdapter') as make, \
                 contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(['--dir', self.temp.name, 'framing', 'next', self.sid, option, value])
            self.assertFalse(load.called)
            self.assertFalse(make.called)
        self.assertFalse(self.service.state().runs)

    def test_provider_failure_is_terminal_and_configuration_failure_starts_no_run(self):
        from inquiry.cli import main
        with patch('inquiry.config.load_openai_settings', side_effect=ValueError('safe config error')), \
             patch('inquiry.openai_adapter.OpenAIAdapter') as make, \
             contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(['--dir', self.temp.name, 'framing', 'next', self.sid])
        self.assertFalse(make.called)
        self.assertFalse(self.service.state().runs)

        failing = FakeAdapter([RunSignal('failed', reason='authentication-failed')])
        with patch('inquiry.config.load_openai_settings',
                   return_value=OpenAISettings('sk-offline', 'resolved-model')), \
             patch('importlib.metadata.version', return_value='2.48.0'), \
             patch('inquiry.openai_adapter.OpenAIAdapter', return_value=failing), \
             contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(['--dir', self.temp.name, 'framing', 'next', self.sid])
        run = list(self.service.state().runs.values())[-1]
        self.assertEqual((run.status, run.reason), ('failed', 'authentication-failed'))

    def test_unsupported_sdk_is_rejected_before_adapter_or_run(self):
        from inquiry.cli import main
        settings = OpenAISettings('sk-offline', 'resolved-model')
        stderr = io.StringIO()
        with patch('inquiry.config.load_openai_settings', return_value=settings), \
             patch('importlib.metadata.version', return_value='1.99.9'), \
             patch('inquiry.openai_adapter.OpenAIAdapter') as make, \
             contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
            main(['--dir', self.temp.name, 'framing', 'next', self.sid])
        self.assertFalse(make.called)
        self.assertFalse(self.service.state().runs)
        self.assertIn('requirements.txt', stderr.getvalue())

    def test_sdk_gate_rejects_prerelease_and_nonstable_suffixes(self):
        from inquiry.cli import _require_openai_sdk
        for installed in ('2.48.0rc1', '2.48.0.dev1', '2.48.0.post1', '2.48.0+local'):
            with self.subTest(installed=installed), \
                 patch('importlib.metadata.version', return_value=installed), \
                 self.assertRaisesRegex(ValueError, 'requirements.txt'):
                _require_openai_sdk()

        for installed in ('2.48.0', '2.49.1', '2.99.0'):
            with self.subTest(installed=installed), \
                 patch('importlib.metadata.version', return_value=installed):
                _require_openai_sdk()

    def test_fake_provider_factory_completes_cli_journey_and_restart(self):
        adapter = QueueAdapter(
            control(), control(done=True, questions=[], question_rationale=''), frame()
        )
        settings = OpenAISettings('sk-offline', 'journey-model')
        with patch('inquiry.config.load_openai_settings', return_value=settings), \
             patch('importlib.metadata.version', return_value='2.48.0'), \
             patch('inquiry.openai_adapter.OpenAIAdapter', return_value=adapter):
            view, _ = self.run_cli('framing', 'next', self.sid)
            for question in view['outstanding_questions']:
                view, _ = self.run_cli(
                    'framing', 'answer', self.sid, question['qid'], 'unknown'
                )
            proposed, _ = self.run_cli('framing', 'next', self.sid)
            proposal_id = proposed['pending_proposal']['id']
            accepted, _ = self.run_cli('framing', 'accept', self.sid, proposal_id)
        restarted = FramingService(self.temp.name)
        self.assertEqual(restarted.view(self.sid)['status'], 'accepted')
        self.assertEqual(set(accepted['hypothesis_ids'].values()), set(restarted.state().hypotheses))


if __name__ == '__main__':
    unittest.main()
