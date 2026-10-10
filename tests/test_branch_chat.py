import contextlib
import io
import tempfile
import unittest
from unittest.mock import patch

from inquiry.branch import BranchService
from inquiry.commands import Commands
from inquiry.framing import FramingService
from inquiry.interactive import run_conversation
from inquiry.store import Store
from tests.branch_fixtures import branch_output
from tests.fakes import FakeAdapter
from tests.test_framing_flow import QueueAdapter
from tests.test_framing_schema import control, frame


class BranchChatTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.commands = Commands(self.temp.name)
        self.commands.initialize('seed', {'central_question': 'question'})
        self.parent = self.commands.add_hypothesis('parent', 'parent claim')
        self.service = BranchService(self.temp.name)
        self.output = []

    def converse(self, values, adapter=None):
        inputs = iter(values)
        def read(prompt):
            try:
                return next(inputs)
            except StopIteration:
                raise EOFError from None
        def forbidden():
            self.fail('No provider call expected')
        return run_conversation(self.temp.name, adapter_factory=forbidden,
                                branch_factory=(lambda: (adapter, 'fake')) if adapter else forbidden,
                                read=read, write=self.output.append)

    def test_accepted_inquiry_branches_by_numbers_and_subset(self):
        adapter = QueueAdapter(branch_output())
        self.converse(['1', '1', '1', '1', '1,3', '2'], adapter)
        state = self.service.state()
        self.assertEqual(len(adapter.calls), 1)
        self.assertEqual(len(state.hypotheses), 3)
        children = [h for h in state.hypotheses.values() if h.parent_ids]
        self.assertTrue(all(h.parent_ids == (self.parent,) and h.status == 'suggested' for h in children))
        self.assertIn('Parents: ' + self.parent, '\n'.join(self.output))
        before = Store(self.temp.name).path.read_bytes()
        self.converse(['2'])
        self.assertEqual(Store(self.temp.name).path.read_bytes(), before)

    def test_pending_preview_exit_and_reject_never_call_model(self):
        proposal = self.service.propose(self.parent, QueueAdapter(branch_output()))
        before = Store(self.temp.name).path.read_bytes()
        self.converse(['1', '1', '3'])
        self.assertEqual(Store(self.temp.name).path.read_bytes(), before)
        self.converse(['1', '1', '2', 'another direction', '2'])
        self.assertEqual(self.service.view(proposal['id'])['status'], 'rejected')
        self.assertEqual(len(self.service.state().hypotheses), 1)

    def test_stale_pending_of_inactive_parent_remains_inspectable(self):
        proposal = self.service.propose(self.parent, QueueAdapter(branch_output()))
        self.commands.decide(self.parent, 'start')
        self.commands.decide(self.parent, 'suspend', reason='pause')
        self.converse(['1', '1', '2'])
        self.assertIn('Stale', '\n'.join(self.output))
        self.assertNotIn('Accept Selected', '\n'.join(self.output))
        self.assertEqual(self.service.view(proposal['id'])['status'], 'pending')

    def test_bad_selection_reprompts_without_extra_generation(self):
        adapter = QueueAdapter(branch_output())
        self.converse(['1', '1', '1', '1', '9', '1,1', 'C-1', '1 3', '2'], adapter)
        self.assertEqual(len(adapter.calls), 1)
        self.assertEqual(len(self.service.state().hypotheses), 3)

    def test_interrupted_branch_recovery_is_explicit_and_discloses_unknown(self):
        with self.assertRaises(SystemExit):
            self.service.propose(self.parent, FakeAdapter([SystemExit()]))
        before = Store(self.temp.name).path.read_bytes()
        self.converse(['2'])
        self.assertEqual(Store(self.temp.name).path.read_bytes(), before)
        self.converse(['1', '2'])
        self.assertIn('Provider outcome: unknown', '\n'.join(self.output))
        self.assertIn('Usage: unknown', '\n'.join(self.output))
        self.assertEqual(len(self.service.state().hypotheses), 1)

    def test_failed_generation_requires_new_choice_and_never_changes_graph(self):
        adapter = FakeAdapter([RuntimeError('private-provider-detail')])
        self.converse(['1', '1', '1', '2'], adapter)
        self.assertEqual(len(adapter.calls), 1)
        self.assertEqual(len(self.service.state().hypotheses), 1)
        self.assertNotIn('private-provider-detail', '\n'.join(self.output))
        self.assertIn('Unknown runs: 1', '\n'.join(self.output))

    def test_same_chat_continues_from_framing_approval_into_branch(self):
        from inquiry.cli import main
        with tempfile.TemporaryDirectory() as root:
            adapter = QueueAdapter(control(), control(done=True, questions=[], question_rationale=''),
                                   frame(), branch_output())
            inputs = ['seed', '1', 'a', 'b', 'c', '1', '1', '1', '1', '1', '1', '2', '2']
            with patch('builtins.input', side_effect=inputs), contextlib.redirect_stdout(io.StringIO()):
                main(['--dir', root, 'chat'], adapter=adapter)
            state = FramingService(root).state()
            self.assertEqual(len(state.hypotheses), 3)
            self.assertEqual(len(adapter.calls), 4)
            self.assertEqual(adapter.calls[-1].operation, 'hypothesis.fork')
