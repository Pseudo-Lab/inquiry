"""Offline durable framing acceptance and restart flows."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from inquiry.adapter import RunSignal
from tests.fakes import FakeAdapter
from tests.test_framing_schema import control, frame


class QueueAdapter:
    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = []

    def run(self, request):
        self.calls.append(request)
        yield from FakeAdapter([RunSignal('succeeded', proposal=self.outputs.pop(0))]).run(request)


class FramingFlowTests(unittest.TestCase):
    def setUp(self):
        from inquiry.framing import FramingService
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = FramingService(self.temp.name)
        self.sid = self.service.start('A saved seed')

    def answer_all(self):
        for question in self.service.view(self.sid)['outstanding_questions']:
            self.service.answer(self.sid, question['qid'], '아직 미정')

    def proposal(self, value=None):
        adapter = QueueAdapter(control(), control(done=True, questions=[], question_rationale=''), value or frame())
        self.service.advance(self.sid, adapter)
        self.answer_all()
        result = self.service.advance(self.sid, adapter)
        return result['pending_proposal'], adapter

    def test_restart_and_accept_are_durable_and_idempotent(self):
        from inquiry.framing import FramingService
        proposal, adapter = self.proposal()
        service = FramingService(self.temp.name)
        self.assertIsNone(service.state().inquiry)
        self.assertEqual(service.advance(self.sid, adapter)['pending_proposal'], proposal)
        self.assertEqual(len(adapter.calls), 3)
        accepted = service.accept(self.sid, proposal['id'])
        seq = service.state().last_seq
        self.assertEqual(service.accept(self.sid, proposal['id']), accepted)
        self.assertEqual(service.state().last_seq, seq)
        self.assertEqual(len(service.state().hypotheses), 2)
        self.assertTrue(all(h.status == 'suggested' for h in service.state().hypotheses.values()))
        self.assertEqual(adapter.calls[-1].context['qa'], proposal['qa'])

    def test_questions_answers_and_five_question_cap(self):
        adapter = QueueAdapter(control(), control(questions=['시간?', '비용?']), frame())
        self.service.advance(self.sid, adapter)
        self.service.advance(self.sid, adapter)
        self.assertEqual(len(adapter.calls), 1)
        qid = self.service.view(self.sid)['outstanding_questions'][0]['qid']
        self.service.answer(self.sid, qid, 'same')
        seq = self.service.state().last_seq
        self.service.answer(self.sid, qid, 'same')
        self.assertEqual(self.service.state().last_seq, seq)
        with self.assertRaises(ValueError):
            self.service.answer(self.sid, qid, 'different')
        self.answer_all()
        self.service.advance(self.sid, adapter)
        self.answer_all()
        self.service.advance(self.sid, adapter)
        self.assertEqual([r.operation for r in adapter.calls], ['framing.control', 'framing.control', 'framing.propose'])
        self.assertEqual(len(self.service.view(self.sid)['questions']), 5)

    def test_regeneration_forwards_rejected_frame_and_reason(self):
        proposal, _ = self.proposal()
        self.service.reject(self.sid, proposal['id'], '4번은 없애고싶어')
        adapter = QueueAdapter(frame())
        self.service.advance(self.sid, adapter, regenerate=True)
        forwarded = adapter.calls[-1].context.get('rejected')
        self.assertEqual(len(forwarded), 1)
        self.assertEqual(forwarded[0]['reason'], '4번은 없애고싶어')
        self.assertEqual(forwarded[0]['frame'], proposal['frame'])

    def test_reject_requires_explicit_regeneration_and_cancel_resume(self):
        proposal, adapter = self.proposal()
        self.service.reject(self.sid, proposal['id'], 'try again')
        with self.assertRaises(ValueError):
            self.service.advance(self.sid, adapter)
        self.service.cancel(self.sid)
        with self.assertRaises(ValueError):
            self.service.advance(self.sid, adapter, regenerate=True)
        self.assertIsNone(self.service.state().inquiry)
        self.service.resume(self.sid)
        regenerated = self.service.advance(self.sid, QueueAdapter(frame()), regenerate=True)['pending_proposal']
        self.assertNotEqual(regenerated['id'], proposal['id'])
        self.assertEqual(regenerated['qa'], proposal['qa'])
        with self.assertRaises(ValueError):
            self.service.accept(self.sid, proposal['id'])

    def test_invalid_frame_records_failure_without_graph(self):
        adapter = QueueAdapter(control(), control(done=True, questions=[], question_rationale=''), {'bad': 'frame'})
        self.service.advance(self.sid, adapter)
        self.answer_all()
        with self.assertRaisesRegex(ValueError, 'run'):
            self.service.advance(self.sid, adapter)
        self.assertEqual(list(self.service.state().runs.values())[-1].reason, 'invalid-proposal')
        self.assertIsNone(self.service.state().inquiry)

    def test_saved_done_control_survives_crash_before_frame(self):
        adapter = QueueAdapter(control(), control(done=True, questions=[], question_rationale=''))
        self.service.advance(self.sid, adapter)
        self.answer_all()
        from inquiry.runs import Runner
        execute = Runner.execute
        def crash(runner, request, *args, **kwargs):
            if request.operation == 'framing.propose':
                raise SystemExit('crash')
            return execute(runner, request, *args, **kwargs)
        with patch.object(Runner, 'execute', crash), self.assertRaises(SystemExit):
            self.service.advance(self.sid, adapter)
        adapter = QueueAdapter(frame())
        self.service.advance(self.sid, adapter)
        self.assertEqual([r.operation for r in adapter.calls], ['framing.propose'])

    def test_runtime_cancel_preserves_draft(self):
        adapter = FakeAdapter([])
        result = self.service.advance(self.sid, adapter, cancelled=lambda: True)
        self.assertEqual(result['status'], 'cancelled')
        self.assertEqual(adapter.calls, [])
        self.service.resume(self.sid)
        self.assertEqual(self.service.view(self.sid)['status'], 'active')

    def test_saved_output_and_acceptance_survive_display_crashes(self):
        adapter = QueueAdapter(control(), control(done=True, questions=[], question_rationale=''), frame())
        self.service.advance(self.sid, adapter)
        self.answer_all()
        with patch.object(self.service, 'view', side_effect=SystemExit('display')), self.assertRaises(SystemExit):
            self.service.advance(self.sid, adapter)
        proposal = self.service.view(self.sid)['pending_proposal']
        self.assertIsNotNone(proposal)
        empty = QueueAdapter()
        self.assertEqual(self.service.advance(self.sid, empty)['pending_proposal'], proposal)
        commit = self.service._commit
        def lose_return(*args, **kwargs):
            commit(*args, **kwargs)
            raise SystemExit('output lost')
        with patch.object(self.service, '_commit', lose_return), self.assertRaises(SystemExit):
            self.service.accept(self.sid, proposal['id'])
        seq = self.service.state().last_seq
        accepted = self.service.accept(self.sid, proposal['id'])
        self.assertEqual(self.service.state().last_seq, seq)
        self.assertEqual(set(accepted['hypothesis_ids'].values()), set(self.service.state().hypotheses))

    def test_another_accepted_session_prevents_dispatch(self):
        other = self.service.start('Another seed')
        proposal, _ = self.proposal()
        self.service.accept(self.sid, proposal['id'])
        adapter = QueueAdapter(control())
        with self.assertRaises(ValueError):
            self.service.advance(other, adapter)
        self.assertEqual(adapter.calls, [])

    def test_duplicate_question_is_saved_as_failed_run(self):
        adapter = QueueAdapter(control(), control(questions=['  목적?  ']))
        self.service.advance(self.sid, adapter)
        self.answer_all()
        with self.assertRaises(ValueError):
            self.service.advance(self.sid, adapter)
        self.assertEqual(len(self.service.view(self.sid)['questions']), 3)
        self.assertEqual(list(self.service.state().runs.values())[-1].reason, 'invalid-proposal')

    def test_five_handcrafted_fixtures(self):
        fixtures = json.loads((Path(__file__).parent / 'fixtures/framing.json').read_text())
        from inquiry.framing import FramingService
        for fixture in fixtures:
            with self.subTest(sample=fixture['sample']), tempfile.TemporaryDirectory() as root:
                self.service = FramingService(root)
                self.sid = self.service.start(fixture['seed'])
                proposal, _ = self.proposal(fixture['frame'])
                self.service.accept(self.sid, proposal['id'])
                self.assertEqual(self.service.state().inquiry.frame, fixture['frame'])

    def test_cli_injected_adapter_and_saved_question_need_no_configuration(self):
        from inquiry.cli import main
        with contextlib.redirect_stdout(io.StringIO()):
            main(['--dir', self.temp.name, 'framing', 'next', self.sid], adapter=QueueAdapter(control()))
        with contextlib.redirect_stdout(io.StringIO()):
            main(['--dir', self.temp.name, 'framing', 'next', self.sid])

    def test_cli_unconfigured_error_occurs_only_when_generation_is_needed(self):
        from inquiry.cli import main
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(['--dir', self.temp.name, 'framing', 'next', self.service.start('fresh')])
