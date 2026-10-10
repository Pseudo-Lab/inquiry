"""Human conversation flow backed by the real store and fake model outputs."""
import tempfile
import unittest
from unittest.mock import patch

from inquiry.framing import FramingService
from inquiry.store import Store, StoreError
from tests.fakes import FakeAdapter
from tests.test_framing_flow import QueueAdapter
from tests.test_framing_schema import control, frame


class InteractiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = FramingService(self.temp.name)
        self.output = []
        self.prompts = []

    def converse(self, inputs, adapter=None, factory=None):
        from inquiry.interactive import run_conversation
        values = iter(inputs)
        def read(prompt):
            self.prompts.append(prompt)
            try:
                value = next(values)
            except StopIteration:
                raise EOFError from None
            if isinstance(value, BaseException):
                raise value
            return value
        def forbidden():
            self.fail('Saved state must not construct a provider')
        return run_conversation(self.temp.name, read=read, write=self.output.append,
                                adapter_factory=factory or ((lambda: (adapter, 'fake')) if adapter else forbidden))

    def pending(self):
        sid = self.service.start('saved seed')
        adapter = QueueAdapter(control(), control(done=True, questions=[], question_rationale=''), frame())
        self.service.advance(sid, adapter)
        for q in self.service.view(sid)['outstanding_questions']:
            self.service.answer(sid, q['qid'], 'saved answer')
        self.service.advance(sid, adapter)
        return sid

    def test_full_conversation_accepts_without_copying_ids(self):
        adapter = QueueAdapter(control(), control(done=True, questions=[], question_rationale=''), frame())
        self.converse(['seed', '1', 'one', 'two', 'three', '1', '1'], adapter)
        state = self.service.state()
        self.assertIsNotNone(state.inquiry)
        self.assertEqual(len(state.hypotheses), 2)
        self.assertTrue(all(h.status == 'suggested' for h in state.hypotheses.values()))
        self.assertEqual(len(adapter.calls), 3)
        self.assertIn('Git-log', '\n'.join(self.output))
        self.assertNotIn('session_id', '\n'.join(self.output))

    def test_unanswered_resume_does_not_ask_saved_answer_or_call_model(self):
        sid = self.service.start('seed')
        self.service.advance(sid, QueueAdapter(control()))
        first = self.service.view(sid)['questions'][0]
        self.service.answer(sid, first['qid'], 'already saved')
        self.converse(['second answer', '/exit'])
        questions = self.service.view(sid)['questions']
        self.assertEqual([q['answer'] for q in questions], ['already saved', 'second answer', None])
        self.assertNotIn(first['text'], '\n'.join(self.output))

    def test_pending_save_exit_and_accept_are_offline_then_summary_is_readonly(self):
        self.pending()
        before = Store(self.temp.name).path.read_bytes()
        self.converse(['3'])
        self.assertEqual(Store(self.temp.name).path.read_bytes(), before)
        self.converse(['1'])
        accepted = Store(self.temp.name).path.read_bytes()
        self.converse([])
        self.assertEqual(Store(self.temp.name).path.read_bytes(), accepted)
        self.assertEqual(len(self.service.state().hypotheses), 2)

    def test_rejection_requires_separate_regenerate_choice(self):
        sid = self.pending()
        self.converse(['2', 'different angle', '2'])
        old = list(self.service.view(sid)['proposals'].values())[0]
        self.assertEqual(old['status'], 'rejected')
        self.assertIsNone(self.service.state().inquiry)
        adapter = QueueAdapter(frame())
        self.converse(['1', '1'], adapter)
        self.assertEqual(len(adapter.calls), 1)
        self.assertIsNotNone(self.service.state().inquiry)

    def test_blank_input_and_invalid_menu_do_not_create_extra_questions(self):
        adapter = QueueAdapter(control())
        self.converse([' ', 'seed', 'wrong', '1', '', 'answer', KeyboardInterrupt()], adapter)
        session = next(iter(self.service.state().framing_sessions.values()))
        self.assertEqual(len(session.questions), 3)
        self.assertEqual(session.questions[0]['answer'], 'answer')
        self.assertEqual(len(adapter.calls), 1)

    def test_multiple_drafts_are_selected_by_number(self):
        first = self.service.start('first')
        second = self.service.start('second')
        self.service.advance(second, QueueAdapter(control()))
        self.converse(['2', 'answer', '/exit'])
        self.assertFalse(self.service.view(first)['questions'])
        self.assertEqual(self.service.view(second)['questions'][0]['answer'], 'answer')

    def test_cancelled_or_interrupted_runs_require_explicit_resume(self):
        sid = self.service.start('seed')
        with self.assertRaises(SystemExit):
            self.service.advance(sid, FakeAdapter([SystemExit()]))
        before = Store(self.temp.name).path.read_bytes()
        self.converse(['2'])
        self.assertEqual(Store(self.temp.name).path.read_bytes(), before)
        self.converse(['1', '2'])
        run = next(iter(self.service.state().runs.values()))
        self.assertEqual(run.reason, 'process-interrupted')
        self.assertIn('failed / process-interrupted', '\n'.join(self.output))
        self.assertIn('Provider outcome: unknown', '\n'.join(self.output))
        self.assertIn('Usage: unknown', '\n'.join(self.output))
        self.service.cancel(sid)
        self.converse(['1', '2'])
        self.assertEqual(self.service.view(sid)['status'], 'active')

    def test_provider_error_never_retries_without_choice(self):
        adapter = FakeAdapter([RuntimeError('private upstream error')])
        self.converse(['seed', '1', '2'], adapter)
        self.assertEqual(len(adapter.calls), 1)
        self.assertNotIn('private upstream error', '\n'.join(self.output))
        self.assertIsNone(self.service.state().inquiry)

    def test_store_failure_propagates_without_success_or_retry(self):
        self.pending()
        original = Store.append
        def fail(store, event, expected_seq):
            if event['changes'][0]['kind'] == 'FrameAccepted':
                raise StoreError('uncertain write')
            return original(store, event, expected_seq)
        with patch.object(Store, 'append', fail), self.assertRaises(StoreError):
            self.converse(['1'])
        self.assertIsNone(self.service.state().inquiry)
        self.assertNotIn('Accepted', '\n'.join(self.output))

    def test_terminal_control_codes_are_escaped_only_for_display(self):
        sid = self.service.start('seed\x1b[2J')
        self.converse(['2'])
        self.assertNotIn('\x1b', '\n'.join(self.output))
        self.assertEqual(self.service.view(sid)['seed'], 'seed\x1b[2J')

    def test_eof_before_seed_creates_no_draft(self):
        self.converse([])
        self.assertFalse(self.service.state().framing_sessions)
