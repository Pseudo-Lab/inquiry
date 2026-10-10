"""Offline human approval journeys using real persistence."""
import tempfile
import unittest

from inquiry.commands import Commands
from inquiry.interactive import run_conversation
from inquiry.store import Store
from tests.fakes import FakeAdapter
from inquiry.adapter import RunSignal
from tests.operation_fixtures import challenge_output, supported_pair, synthesis_output


def output():
    return dict(assumptions=['추가 전제'], falsified_if=['추가 반증 조건'], reason='검토 범위를 구체화')


class OperationChatTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name
        self.commands = Commands(self.root)
        self.commands.initialize('seed', {'central_question': 'question'})
        self.hid = self.commands.add_hypothesis('가설', '주장', assumptions=['기존 전제'])
        self.lines = []

    def converse(self, values, adapter=None, challenge_adapter=None, synthesis_adapter=None):
        inputs = iter(values)
        def read(_):
            try:
                return next(inputs)
            except StopIteration:
                raise EOFError from None
        def forbidden():
            self.fail('No provider call expected')
        run_conversation(self.root, adapter_factory=forbidden, read=read, write=self.lines.append,
                         operation_factories={
                             'deepen': (lambda: (adapter, 'fake')) if adapter else forbidden,
                             'challenge': ((lambda: (challenge_adapter, 'fake'))
                                           if challenge_adapter else forbidden),
                             'synthesize': ((lambda: (synthesis_adapter, 'fake'))
                                            if synthesis_adapter else forbidden),
                         })

    def propose(self):
        from inquiry.operations import OperationsService
        return OperationsService(self.root).propose('deepen', [self.hid],
            FakeAdapter([RunSignal('succeeded', proposal=output())]))

    def test_deepen_preview_and_approval_preserve_claim_and_show_additions(self):
        adapter = FakeAdapter([RunSignal('succeeded', proposal=output())])
        self.converse(['3', '1', '1', '1', '1', '2'], adapter)
        node = self.commands.state().hypotheses[self.hid]
        self.assertEqual(node.assumptions, ('기존 전제', '추가 전제'))
        self.assertEqual((node.claim, node.status), ('주장', 'suggested'))
        self.assertEqual(len(adapter.calls), 1)
        self.assertEqual(adapter.calls[0].operation, 'hypothesis.deepen')
        text = '\n'.join(self.lines)
        for expected in ('Current assumptions', 'Add assumptions', 'Add falsified if', 'Deepen saved'):
            self.assertIn(expected, text)

    def test_pending_exit_and_restart_approval_are_offline(self):
        proposal = self.propose()
        before = Store(self.root).path.read_bytes()
        self.converse(['3', '1', '1', '3'])
        self.assertEqual(Store(self.root).path.read_bytes(), before)
        self.converse(['3', '1', '1', '1', '2'])
        self.assertEqual(self.commands.state().operation_proposals[proposal['id']]['status'], 'accepted')

    def test_challenge_chat_approval_and_saved_resume(self):
        adapter = FakeAdapter([RunSignal('succeeded', proposal=challenge_output())])
        self.converse(['3', '2', '1', '1', '3'], challenge_adapter=adapter)
        state = self.commands.state()
        proposal = next(p for p in state.operation_proposals.values()
                        if p['operation'] == 'challenge')
        self.assertEqual(proposal['status'], 'pending')
        self.converse(['3', '2', '1', '1', '2'])
        state = self.commands.state()
        self.assertEqual(state.operation_proposals[proposal['id']]['status'], 'accepted')
        self.assertEqual(len(state.review_notes), 1)
        self.assertEqual(len(adapter.calls), 1)
        self.assertIn('Challenge review note saved', '\n'.join(self.lines))

    def test_stale_inactive_target_can_be_seen_and_rejected_offline(self):
        proposal = self.propose()
        self.commands.decide(self.hid, 'start')
        self.commands.decide(self.hid, 'suspend', reason='pause')
        self.converse(['3', '1', '1', '1', 'old proposal', '2'])
        self.assertIn('Stale', '\n'.join(self.lines))
        self.assertNotIn('1. Accept', '\n'.join(self.lines))
        self.assertEqual(self.commands.state().operation_proposals[proposal['id']]['status'], 'rejected')

    def test_failure_discloses_run_and_never_retries(self):
        adapter = FakeAdapter([RuntimeError('private-error-marker')])
        self.converse(['3', '1', '1', '1', '2'], adapter)
        text = '\n'.join(self.lines)
        self.assertEqual(len(adapter.calls), 1)
        self.assertIn('Usage: unknown', text)
        self.assertNotIn('private-error-marker', text)
        self.assertEqual(self.commands.state().hypotheses[self.hid].assumptions, ('기존 전제',))

    def test_back_paths_and_save_exit_do_not_write(self):
        before = Store(self.root).path.read_bytes()
        self.converse(['3', '4', '3', '1', '2', '3', '1', '1', '2', '2'])
        self.assertEqual(Store(self.root).path.read_bytes(), before)

    def test_preview_escapes_terminal_controls(self):
        payload = output()
        payload['reason'] = '\x1b[2Jmalicious'
        adapter = FakeAdapter([RunSignal('succeeded', proposal=payload)])
        self.converse(['3', '1', '1', '1', '3'], adapter)
        self.assertNotIn('\x1b', '\n'.join(self.lines))
        self.assertIn('\\x1b[2J', '\n'.join(self.lines))

    def test_no_eligible_targets_returns_without_call_or_write(self):
        self.commands.decide(self.hid, 'close', reason='not selected', reopen_if='new information')
        before = Store(self.root).path.read_bytes()
        self.converse(['3', '1', '2'])
        self.assertIn('보완할 수 있는 가설이 없습니다', '\n'.join(self.lines))
        self.assertEqual(Store(self.root).path.read_bytes(), before)

    def test_interrupted_deepen_requires_explicit_recovery_before_check(self):
        from inquiry.operations import OperationsService
        with self.assertRaises(SystemExit):
            OperationsService(self.root).propose('deepen', [self.hid], FakeAdapter([SystemExit()]))
        before = Store(self.root).path.read_bytes()
        self.converse(['2'])
        self.assertEqual(Store(self.root).path.read_bytes(), before)
        self.converse(['1', '2'])
        text = '\n'.join(self.lines)
        self.assertIn('process-interrupted', text)
        self.assertIn('Provider outcome: unknown', text)
        self.assertEqual(self.commands.state().hypotheses[self.hid].assumptions, ('기존 전제',))

    def test_synthesis_chat_generates_then_atomically_saves_all_parent_changes(self):
        self.temp.cleanup()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name
        first, second = supported_pair(self.root)
        self.commands = Commands(self.root)
        adapter = FakeAdapter([RunSignal('succeeded', proposal=synthesis_output())])

        self.converse(['3', '4', '1', '1,2', '1', '1', '2'], synthesis_adapter=adapter)

        state = self.commands.state()
        merged = state.hypotheses['SYN-001']
        self.assertEqual(merged.parent_ids, (first, second))
        self.assertEqual([state.hypotheses[item].status for item in (first, second)],
                         ['synthesized', 'synthesized'])
        self.assertEqual(len(adapter.calls), 1)
        self.assertIn('Synthesis saved', '\n'.join(self.lines))
