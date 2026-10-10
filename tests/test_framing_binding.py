"""Lazy provider binding and explicit limits, with no installed SDK required."""
import tempfile
import unittest

from inquiry.framing import FramingService
from tests.test_framing_flow import QueueAdapter
from tests.test_framing_schema import control, frame


class FramingBindingTests(unittest.TestCase):
    def test_binding_is_lazy_and_recursive_limits_and_model_are_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            service = FramingService(root)
            identity = service.start('binding')
            adapter = QueueAdapter(control(), control(done=True, questions=[], question_rationale=''), frame())
            calls = []
            def factory():
                calls.append(True)
                return adapter, 'bound-model'
            def forbidden():
                self.fail('Saved state must not resolve credentials or SDK')
            view = service.advance(identity, adapter_factory=factory, max_output_tokens=512, timeout=2.0)
            self.assertEqual(len(calls), 1)
            self.assertEqual(service.advance(identity, adapter_factory=forbidden), view)
            for question in view['outstanding_questions']:
                service.answer(identity, question['qid'], '미정')
            proposed = service.advance(identity, adapter_factory=factory, max_output_tokens=512, timeout=2.0)
            self.assertEqual(len(calls), 3)
            self.assertEqual(len(adapter.calls), 3)
            self.assertTrue(all(r.model == 'bound-model' for r in adapter.calls))
            self.assertTrue(all(r.max_output_tokens == 512 and r.timeout == 2.0 for r in adapter.calls))
            self.assertEqual(service.advance(identity, adapter_factory=forbidden), proposed)
            service.accept(identity, proposed['pending_proposal']['id'])
            self.assertEqual(service.advance(identity, adapter_factory=forbidden)['status'], 'accepted')

    def test_invalid_limits_do_not_resolve_credentials_or_write_runs(self):
        with tempfile.TemporaryDirectory() as root:
            service = FramingService(root)
            identity = service.start('limits')
            calls = []
            def factory():
                calls.append(True)
                return QueueAdapter(control()), 'bound-model'
            for limits in (dict(max_output_tokens=0), dict(max_output_tokens=True),
                           dict(timeout=float('nan')), dict(timeout=True), dict(timeout=0)):
                with self.subTest(limits=limits), self.assertRaises(ValueError):
                    service.advance(identity, adapter_factory=factory, **limits)
            self.assertFalse(calls)
            self.assertFalse(service.state().runs)
