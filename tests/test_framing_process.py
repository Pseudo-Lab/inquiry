"""Cross-process persistence check, without a provider or project data."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from inquiry.framing import FramingService
from inquiry.adapter import RunSignal
from inquiry.store import Store
from tests.fakes import FakeAdapter


class FramingProcessTests(unittest.TestCase):
    def test_provider_and_keyboard_cancellation_are_atomic(self):
        for signal in (RunSignal('cancelled', reason='provider-cancelled'), KeyboardInterrupt()):
            with self.subTest(signal=type(signal).__name__), tempfile.TemporaryDirectory() as root:
                service = FramingService(root)
                identity = service.start('cancel boundary')
                view = service.advance(identity, FakeAdapter([signal]))
                self.assertEqual(view['status'], 'cancelled')
                changes = Store(root).read_all()[-1]['changes']
                self.assertEqual([c['kind'] for c in changes], ['RunCancelled', 'FramingCancelled'])
                self.assertEqual(changes[0]['reason'], changes[1]['reason'])

    def test_exit_after_cancel_append_keeps_session_cancelled(self):
        with tempfile.TemporaryDirectory() as root:
            service = FramingService(root)
            identity = service.start('cancel boundary')
            original = Store.append
            def crash(store, event, expected_seq):
                original(store, event, expected_seq)
                if event['changes'][0]['kind'] == 'RunCancelled':
                    raise SystemExit('after durable cancellation')
            with patch.object(Store, 'append', crash), self.assertRaises(SystemExit):
                service.advance(identity, FakeAdapter([]), cancelled=lambda: True)
            fresh = FramingService(root)
            self.assertEqual(fresh.view(identity)['status'], 'cancelled')
            adapter = FakeAdapter([])
            with self.assertRaisesRegex(ValueError, 'resume'):
                fresh.advance(identity, adapter)
            self.assertFalse(adapter.calls)
            self.assertEqual(fresh.resume(identity)['status'], 'active')

    def test_separate_processes_resume_answers_preview_and_approval(self):
        first = """
import json, sys
from inquiry.framing import FramingService
from tests.test_framing_flow import QueueAdapter
from tests.test_framing_schema import control
s = FramingService(sys.argv[1])
identity = s.start('세션이 달라도 같은 실수를 줄이려면?')
view = s.advance(identity, QueueAdapter(control()))
s.answer(identity, view['questions'][0]['qid'], 'handover를 사용했다')
print(json.dumps({'session_id': identity, 'qids': [q['qid'] for q in view['questions']]}))
"""
        second = """
import json, sys
from inquiry.framing import FramingService
from tests.test_framing_flow import QueueAdapter
from tests.test_framing_schema import control, frame
s = FramingService(sys.argv[1]); identity = sys.argv[2]
view = s.resume(identity)
assert len(view['outstanding_questions']) == 2
assert view['questions'][0]['answer'] == 'handover를 사용했다'
for q in view['outstanding_questions']:
    s.answer(identity, q['qid'], '미정')
view = s.advance(identity, QueueAdapter(control(done=True, questions=[], question_rationale=''), frame()))
assert s.state().inquiry is None
print(json.dumps({'proposal_id': view['pending_proposal']['id'], 'qids': [q['qid'] for q in view['questions']]}))
"""
        third = """
import json, sys
from inquiry.framing import FramingService
from inquiry.store import Store
from tests.fakes import FakeAdapter
s = FramingService(sys.argv[1]); identity, proposal = sys.argv[2:]
adapter = FakeAdapter([])
assert s.advance(identity, adapter)['pending_proposal']['id'] == proposal
assert not adapter.calls
result = s.accept(identity, proposal)
before = Store(sys.argv[1]).path.read_bytes()
assert s.accept(identity, proposal) == result
assert Store(sys.argv[1]).path.read_bytes() == before
assert len(s.state().hypotheses) == 2
assert all(h.status == 'suggested' for h in s.state().hypotheses.values())
print(json.dumps(result))
"""
        def run(script, *args):
            result = subprocess.run([sys.executable, '-c', script, *args],
                                    cwd=Path(__file__).resolve().parents[1],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        with tempfile.TemporaryDirectory() as root:
            started = run(first, root)
            proposed = run(second, root, started['session_id'])
            self.assertEqual(proposed['qids'], started['qids'])
            approved = run(third, root, started['session_id'], proposed['proposal_id'])
            self.assertEqual(len(approved['hypothesis_ids']), 2)
