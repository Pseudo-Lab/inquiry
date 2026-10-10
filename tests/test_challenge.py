"""Focused Challenge acceptance tests using only synthetic local state."""

import tempfile
import unittest

from inquiry.adapter import RunSignal
from inquiry.commands import Commands
from inquiry.operation_schema import OPERATION_SCHEMAS, validate_operation
from inquiry.operations import OperationsService
from inquiry.store import Store
from tests.fakes import FakeAdapter
from tests.operation_fixtures import challenge_output


class ChallengeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name
        self.commands = Commands(self.root)
        self.commands.initialize('seed', {'question': 'question'})
        self.hid = self.commands.add_hypothesis('title', 'claim')
        self.service = OperationsService(self.root)

    def propose(self, output=None):
        fake = FakeAdapter([RunSignal('succeeded', proposal=output or challenge_output())])
        return self.service.propose('challenge', [self.hid], fake), fake

    def test_challenge_schema_is_strict_and_detached(self):
        source = challenge_output()
        self.assertEqual(set(OPERATION_SCHEMAS), {'deepen', 'challenge', 'synthesize'})
        result = validate_operation('challenge', source)
        self.assertEqual(result, source)
        source['objections'][0]['claim'] = 'changed'
        self.assertNotEqual(result, source)

        invalid = []
        value = challenge_output(); value['extra'] = True; invalid.append(value)
        value = challenge_output(); value['objections'] = []; invalid.append(value)
        value = challenge_output(); value['objections'] *= 4; invalid.append(value)
        value = challenge_output(); value['objections'][0]['check'] = ' '; invalid.append(value)
        value = challenge_output(); value['objections'][0]['extra'] = 'x'; invalid.append(value)
        value = challenge_output(); value['objections'].append(dict(
            value['objections'][0], claim='  ' + value['objections'][0]['claim'].upper() + '  '))
        invalid.append(value)
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                validate_operation('challenge', payload)

    def test_approval_creates_one_note_without_mutating_domain_state(self):
        before = self.service.state()
        proposal, fake = self.propose()
        self.assertEqual(fake.calls[0].operation, 'hypothesis.challenge')
        self.assertEqual(set(fake.calls[0].context),
                         {'system', 'output_schema', 'inquiry_frame', 'parents'})
        nid = self.service.accept(proposal['id'])
        after = self.service.state()

        self.assertEqual(after.hypotheses, before.hypotheses)
        self.assertEqual(after.evidence, before.evidence)
        self.assertEqual(after.evidence_links, before.evidence_links)
        self.assertEqual(nid, 'N-001')
        self.assertEqual(after.review_notes[nid]['objections'], challenge_output()['objections'])
        self.assertEqual(after.review_notes[nid]['origin'], 'model-opinion')
        self.assertEqual(after.review_notes[nid]['approved_by'], 'human:local')
        self.assertEqual(after.review_notes[nid]['run_id'], proposal['run_id'])
        self.assertEqual(self.service.notes(self.hid), [after.review_notes[nid]])

        saved = Store(self.root).path.read_bytes()
        self.assertEqual(self.service.accept(proposal['id']), nid)
        self.assertEqual(Store(self.root).path.read_bytes(), saved)

    def test_separate_generations_create_separate_notes_and_rejection_creates_none(self):
        first, _ = self.propose()
        self.assertEqual(self.service.accept(first['id']), 'N-001')
        second, _ = self.propose()
        self.assertEqual(self.service.accept(second['id']), 'N-002')
        third, _ = self.propose()
        self.service.reject(third['id'], 'not useful')
        self.assertEqual(list(self.service.state().review_notes), ['N-001', 'N-002'])

    def test_notes_remain_available_offline_after_target_closes(self):
        proposal, _ = self.propose()
        nid = self.service.accept(proposal['id'])
        self.commands.decide(self.hid, 'close', reason='done', reopen_if='new facts')
        before = Store(self.root).path.read_bytes()
        self.assertEqual(self.service.notes(self.hid), [self.service.state().review_notes[nid]])
        self.assertEqual(Store(self.root).path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
