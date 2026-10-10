import contextlib
import io
import tempfile
import unittest
from unittest.mock import patch

from inquiry.cli import main
from inquiry.commands import Commands
from inquiry.framing import FramingService
from tests.test_framing_flow import QueueAdapter
from tests.test_framing_schema import control, frame


class ChatCLITests(unittest.TestCase):
    def test_one_command_journey_and_limits(self):
        with tempfile.TemporaryDirectory() as root:
            output = io.StringIO()
            adapter = QueueAdapter(control(), control(done=True, questions=[], question_rationale=''), frame())
            with patch('builtins.input', side_effect=['seed', '1', 'a', 'b', 'c', '1', '1', '2']), \
                 contextlib.redirect_stdout(output):
                main(['--dir', root, 'chat', '--model', 'test-model',
                      '--max-output-tokens', '4000', '--timeout', '60'], adapter=adapter)
            self.assertIsNotNone(FramingService(root).state().inquiry)
            self.assertTrue(all(r.model == 'test-model' and r.max_output_tokens == 4000
                                and r.timeout == 60 for r in adapter.calls))
            self.assertIn('Accepted inquiry', output.getvalue())
            self.assertNotIn('session_id', output.getvalue())

    def test_accepted_manual_inquiry_can_exit_without_sdk(self):
        with tempfile.TemporaryDirectory() as root:
            Commands(root).initialize('manual', {'question': 'saved question'})
            with patch('builtins.input', side_effect=['2']), \
                 patch('inquiry.cli._require_openai_sdk', side_effect=AssertionError('No SDK needed')), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                main(['--dir', root, 'chat'])
            self.assertIn('saved question', output.getvalue())

    def test_chat_help_and_bad_limits(self):
        with contextlib.redirect_stdout(io.StringIO()) as output, self.assertRaises(SystemExit) as caught:
            main(['chat', '--help'])
        self.assertEqual(caught.exception.code, 0)
        self.assertIn('--timeout', output.getvalue())
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            main(['chat', '--timeout', 'nan'])
        self.assertEqual(caught.exception.code, 2)

    def test_new_generation_resolves_provider_only_after_explicit_choice(self):
        from inquiry.cli import _openai_factory
        with tempfile.TemporaryDirectory() as root:
            sid = FramingService(root).start('seed')
            with patch('builtins.input', side_effect=['2']), \
                 patch('inquiry.cli._require_openai_sdk', side_effect=AssertionError('No SDK needed')), \
                 contextlib.redirect_stdout(io.StringIO()):
                main(['--dir', root, 'chat'])
            self.assertFalse(FramingService(root).state().runs)
            self.assertEqual(FramingService(root).view(sid)['seed'], 'seed')
            self.assertTrue(callable(_openai_factory(root, None, None, 60)))
