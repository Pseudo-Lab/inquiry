import copy
import unittest

from inquiry.adapter import unknown_usage
from inquiry.branch_schema import parent_snapshot
from inquiry.replay import ReplayError, replay
from inquiry.store import Store
from tests.operation_fixtures import challenge_output, deepen_output
from tests.test_events import event


def created(identity='H-001', assumptions=None):
    return dict(kind='HypothesisCreated', hypothesis_id=identity, title='title', claim='claim',
                parent_ids=[], assumptions=list(assumptions or []), falsified_if=[])


class OperationReplayTests(unittest.TestCase):
    def setUp(self):
        self.records = [event(changes=[dict(kind='InquiryCreated', seed='seed', frame={}), created()])]

    def append(self, changes, actor='human:local'):
        self.records.append(event(seq=len(self.records) + 1, changes=changes, actor=actor))

    def start(self, operation='hypothesis.deepen', targets=None):
        self.append([dict(kind='RunStarted', run_id='R-1', operation=operation, model='fake',
                          target_ids=list(targets or ['H-001']), session_id=None,
                          max_output_tokens=4000, timeout=60.0)], 'agent:runner')

    def propose(self):
        self.start()
        self.append([dict(kind='RunDispatched', run_id='R-1')], 'agent:runner')
        snapshot = {'H-001': parent_snapshot(replay(self.records).hypotheses['H-001'])}
        output = deepen_output()
        self.append([
            dict(kind='RunSucceeded', run_id='R-1', proposal=output,
                 usage=unknown_usage(), provider_request_id=None),
            dict(kind='OperationProposed', proposal_id='OP-1', run_id='R-1', operation='deepen',
                 target_ids=['H-001'], target_snapshot=snapshot, output=output),
        ], 'agent:runner')

    def approval(self):
        output = deepen_output()
        return [dict(kind='OperationAccepted', proposal_id='OP-1', result_id='H-001'),
                dict(kind='HypothesisRefined', proposal_id='OP-1', hypothesis_id='H-001',
                     assumptions=output['assumptions'], falsified_if=output['falsified_if'],
                     reason=output['reason'])]

    def challenge_propose(self):
        self.start('hypothesis.challenge')
        self.append([dict(kind='RunDispatched', run_id='R-1')], 'agent:runner')
        snapshot = {'H-001': parent_snapshot(replay(self.records).hypotheses['H-001'])}
        output = challenge_output()
        self.append([
            dict(kind='RunSucceeded', run_id='R-1', proposal=output,
                 usage=unknown_usage(), provider_request_id=None),
            dict(kind='OperationProposed', proposal_id='OP-1', run_id='R-1', operation='challenge',
                 target_ids=['H-001'], target_snapshot=snapshot, output=output),
        ], 'agent:runner')

    def challenge_approval(self, note_id='N-001'):
        return [dict(kind='OperationAccepted', proposal_id='OP-1', result_id=note_id),
                dict(kind='ReviewNoteCreated', note_id=note_id, proposal_id='OP-1',
                     hypothesis_id='H-001', objections=challenge_output()['objections'])]

    def test_deepen_projection_snapshot_and_atomic_approval(self):
        before = replay(self.records).hypotheses['H-001']
        self.propose()
        pending = replay(self.records)
        self.assertEqual(pending.hypotheses['H-001'], before)
        self.assertEqual(pending.runs['R-1'].target_snapshot,
                         {'H-001': parent_snapshot(before)})
        self.assertEqual(pending.operation_proposals['OP-1']['status'], 'pending')
        self.append(self.approval())
        state = replay(self.records)
        node = state.hypotheses['H-001']
        self.assertEqual((node.id, node.title, node.claim, node.parent_ids, node.status, node.history),
                         (before.id, before.title, before.claim, before.parent_ids, before.status, before.history))
        self.assertEqual(node.assumptions, tuple(deepen_output()['assumptions']))
        self.assertEqual(state.operation_proposals['OP-1']['result_id'], 'H-001')
        self.assertEqual(state.operation_proposals['OP-1']['reason'], deepen_output()['reason'])
        self.assertEqual(state.review_notes, {})

    def test_challenge_projection_and_derived_provenance(self):
        before = replay(self.records)
        self.challenge_propose()
        self.append(self.challenge_approval())
        state = replay(self.records)
        self.assertEqual(state.hypotheses, before.hypotheses)
        self.assertEqual(state.evidence, before.evidence)
        self.assertEqual(state.evidence_links, before.evidence_links)
        note = state.review_notes['N-001']
        self.assertEqual(set(note), {'id', 'hypothesis_id', 'proposal_id', 'run_id',
                                    'objections', 'origin', 'approved_by', 'approved_at'})
        self.assertEqual((note['run_id'], note['origin'], note['approved_by'], note['approved_at']),
                         ('R-1', 'model-opinion', 'human:local', self.records[-1]['at']))

    def test_hostile_challenge_notes_are_rejected(self):
        self.challenge_propose()
        pending = copy.deepcopy(self.records)
        variants = []
        for changes, actor in [
            (self.challenge_approval(), 'agent:runner'),
            (self.challenge_approval()[1:], 'human:local'),
            (self.challenge_approval()[:1], 'human:local'),
        ]:
            rows = copy.deepcopy(pending)
            rows.append(event(seq=len(rows) + 1, changes=changes, actor=actor))
            variants.append(rows)
        for mutate in (
            lambda c: c[0].update(result_id='N-other'),
            lambda c: c[1].update(note_id='N-other'),
            lambda c: c[1].update(proposal_id='OP-other'),
            lambda c: c[1].update(hypothesis_id='H-other'),
            lambda c: c[1].update(objections=[dict(challenge_output()['objections'][0], claim='forged')]),
        ):
            changes = self.challenge_approval(); mutate(changes)
            rows = copy.deepcopy(pending)
            rows.append(event(seq=len(rows) + 1, changes=changes))
            variants.append(rows)
        accepted = copy.deepcopy(pending)
        accepted.append(event(seq=len(accepted) + 1, changes=self.challenge_approval()))
        accepted.append(event(seq=len(accepted) + 1, changes=[
            dict(kind='OperationAccepted', proposal_id='OP-1', result_id='N-001'),
            dict(kind='ReviewNoteCreated', note_id='N-001', proposal_id='OP-1',
                 hypothesis_id='H-001', objections=challenge_output()['objections'])]))
        variants.append(accepted)
        for rows in variants:
            with self.subTest(rows=rows[-1]), self.assertRaises(ReplayError):
                replay(rows)

    def test_forged_proposal_batches_and_future_operations_are_rejected(self):
        self.propose()
        good = copy.deepcopy(self.records)
        mutations = [
            lambda rows: rows[-1]['changes'].pop(),
            lambda rows: rows[-1]['changes'][1].update(run_id='missing'),
            lambda rows: rows[-1]['changes'][1].update(operation='challenge'),
            lambda rows: rows[-1]['changes'][1]['target_snapshot']['H-001'].update(claim='forged'),
            lambda rows: rows[-1]['changes'][1].update(
                output=dict(rows[-1]['changes'][1]['output'], reason='forged')),
            lambda rows: rows[-1].update(actor='human:local'),
        ]
        for mutate in mutations:
            rows = copy.deepcopy(good); mutate(rows)
            with self.subTest(mutate=mutate), self.assertRaises(ReplayError):
                replay(rows)
        for operation in ('hypothesis.synthesize',):
            rows = copy.deepcopy(self.records[:1])
            rows.append(event(seq=2, actor='agent:runner', changes=[dict(
                kind='RunStarted', run_id='R-X', operation=operation, model='fake',
                target_ids=['H-001'], session_id=None, max_output_tokens=4, timeout=1)]))
            with self.assertRaises(ReplayError):
                replay(rows)

    def test_hostile_approval_rejects_nonhuman_stale_partial_extra_and_duplicates(self):
        self.propose()
        pending = copy.deepcopy(self.records)
        variants = []
        for changes, actor in [
            (self.approval(), 'agent:runner'),
            (self.approval()[:1], 'human:local'),
            (self.approval() + [created('H-extra')], 'human:local'),
        ]:
            rows = copy.deepcopy(pending)
            rows.append(event(seq=len(rows) + 1, changes=changes, actor=actor))
            variants.append(rows)
        for mutate in (
            lambda c: c[0].update(result_id='H-other'),
            lambda c: c[1].update(hypothesis_id='H-other'),
            lambda c: c[1].update(reason='forged'),
            lambda c: c[1].update(assumptions=[]),
            lambda c: c[1].update(assumptions=['forged']),
        ):
            changes = self.approval(); mutate(changes)
            rows = copy.deepcopy(pending)
            rows.append(event(seq=len(rows) + 1, changes=changes))
            variants.append(rows)
        stale = copy.deepcopy(pending)
        stale.append(event(seq=len(stale) + 1, changes=[dict(
            kind='HypothesisStateChanged', hypothesis_id='H-001', **{'from': 'suggested', 'to': 'exploring'},
            trigger='start', actor='human:local', at='2026-09-17T00:00:00Z', reason='start',
            evidence_ids=[], evidence_snapshot=None, reopen_if=None, synthesis_target=None)]))
        stale.append(event(seq=len(stale) + 1, changes=self.approval()))
        variants.append(stale)
        accepted = copy.deepcopy(pending)
        accepted.append(event(seq=len(accepted) + 1, changes=self.approval()))
        accepted.append(event(seq=len(accepted) + 1, changes=self.approval()))
        variants.append(accepted)
        for rows in variants:
            with self.subTest(rows=rows[-1]), self.assertRaises(ReplayError):
                replay(rows)

    def test_existing_item_duplicate_and_noop_output_are_rejected(self):
        self.records[0]['changes'][1]['assumptions'] = ['Existing Item']
        self.start(); self.append([dict(kind='RunDispatched', run_id='R-1')], 'agent:runner')
        snapshot = {'H-001': parent_snapshot(replay(self.records).hypotheses['H-001'])}
        for output in (
            {'assumptions': [' existing   item '], 'falsified_if': [], 'reason': 'duplicate'},
            {'assumptions': [], 'falsified_if': [], 'reason': 'noop'},
        ):
            rows = copy.deepcopy(self.records)
            rows.append(event(seq=len(rows) + 1, actor='agent:runner', changes=[
                dict(kind='RunSucceeded', run_id='R-1', proposal=output,
                     usage=unknown_usage(), provider_request_id=None),
                dict(kind='OperationProposed', proposal_id='OP-X', run_id='R-1', operation='deepen',
                     target_ids=['H-001'], target_snapshot=snapshot, output=output)]))
            with self.subTest(output=output), self.assertRaises(ReplayError):
                replay(rows)

    def test_invalid_approval_batches_preserve_store_bytes(self):
        import tempfile
        self.propose()
        with tempfile.TemporaryDirectory() as root, Store(root) as store:
            for record in self.records:
                store.append(record, expected_seq=record['seq'] - 1)
            before = store.path.read_bytes()
            variants = [self.approval()[:1], self.approval() + [created('H-extra')]]
            forged = self.approval(); forged[1]['reason'] = 'forged'; variants.append(forged)
            for changes in variants:
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    store.append(event(seq=5, changes=changes), expected_seq=4)
                self.assertEqual(store.path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
