import copy
import json
import tempfile
import unittest

from inquiry.adapter import RunRequest, RunSignal, unknown_usage
from inquiry.branch_schema import BRANCH_SCHEMA, parent_context, parent_snapshot, validate_branch
from inquiry.model import Hypothesis
from inquiry.replay import ReplayError, replay
from inquiry.runs import Runner
from inquiry.store import Store
from tests.fakes import FakeAdapter
from tests.test_events import event


def payload():
    return {'candidates': [dict(candidate_id='C' + str(n), title='title ' + str(n),
                                claim='claim ' + str(n), difference='different cause')
                           for n in range(1, 4)]}


def created(identity='H0', **updates):
    return dict(kind='HypothesisCreated', hypothesis_id=identity, title='parent',
                claim='original claim', parent_ids=[], assumptions=[], falsified_if=[], **updates)


class BranchSchemaTests(unittest.TestCase):
    def test_schema_and_detached_valid_output(self):
        source = payload()
        validated = validate_branch(source)
        source['candidates'][0]['claim'] = 'mutated'
        self.assertEqual(validated, payload())
        self.assertFalse(BRANCH_SCHEMA['additionalProperties'])

    def test_rejects_counts_fields_blank_duplicates_and_non_json(self):
        bad = [None, [], {'candidates': []}, {'candidates': payload()['candidates'][:1]},
               {'candidates': payload()['candidates'] * 2}, dict(payload(), extra=True)]
        for key in ('candidate_id', 'title', 'claim', 'difference'):
            value = payload()
            value['candidates'][0][key] = '  '
            bad.append(value)
        for key in ('candidate_id', 'title', 'claim'):
            value = payload()
            value['candidates'][1][key] = value['candidates'][0][key]
            if key != 'candidate_id':
                value['candidates'][1][key] = '  ' + value['candidates'][1][key].upper() + '  '
            bad.append(value)
        for value in (float('nan'), object(), '\ud800'):
            invalid = payload()
            invalid['candidates'][0]['claim'] = value
            bad.append(invalid)
        extra = payload()
        extra['candidates'][0]['state'] = 'supported'
        bad.append(extra)
        missing = payload()
        del missing['candidates'][0]['difference']
        bad.append(missing)
        for invalid in bad:
            with self.subTest(invalid=repr(invalid)), self.assertRaises(ValueError):
                validate_branch(invalid)

    def test_full_snapshot_and_minimum_context_are_detached_json(self):
        node = Hypothesis('H0', 'parent', 'original claim', (), history=({'reason': 'private'},))
        snapshot = parent_snapshot(node)
        self.assertEqual(json.loads(json.dumps(snapshot)), snapshot)
        context = parent_context(snapshot)
        self.assertEqual(set(context), {'id', 'title', 'claim', 'parent_ids', 'status', 'assumptions', 'falsified_if'})
        context['assumptions'].append('changed')
        snapshot['history'][0]['reason'] = 'changed'
        self.assertEqual(node.history[0]['reason'], 'private')
        self.assertEqual(snapshot['assumptions'], [])


class BranchReplayTests(unittest.TestCase):
    def setUp(self):
        self.records = [event(changes=[dict(kind='InquiryCreated', seed='seed', frame={}), created()])]

    def append(self, changes, actor='human:local'):
        self.records.append(event(seq=len(self.records) + 1, changes=changes, actor=actor))

    def start(self, **updates):
        change = dict(kind='RunStarted', run_id='R', operation='hypothesis.fork', model='fake',
                      target_ids=['H0'], session_id=None, max_output_tokens=100, timeout=10)
        change.update(updates)
        self.append([change], 'agent:runner')

    def propose(self):
        self.start()
        self.append([dict(kind='RunDispatched', run_id='R')], 'agent:runner')
        self.append([
            dict(kind='RunSucceeded', run_id='R', proposal=payload(), usage=unknown_usage(), provider_request_id=None),
            dict(kind='BranchProposed', proposal_id='P', run_id='R', parent_id='H0',
                 parent_snapshot=parent_snapshot(replay(self.records).hypotheses['H0']), candidates=payload()['candidates'])
        ], 'agent:runner')

    def approval(self, selected=('C3', 'C1')):
        mapping = {identity: 'H-' + identity for identity in selected}
        return [dict(kind='BranchAccepted', proposal_id='P', selected_ids=list(selected), hypothesis_ids=mapping)] + [
            dict(kind='HypothesisCreated', hypothesis_id=mapping[c['candidate_id']], title=c['title'], claim=c['claim'],
                 parent_ids=['H0'], assumptions=[], falsified_if=[])
            for c in payload()['candidates'] if c['candidate_id'] in mapping]

    def transition(self):
        return dict(kind='HypothesisStateChanged', hypothesis_id='H0', **{'from': 'suggested', 'to': 'exploring'},
                    trigger='start', actor='human:local', at='2026-01-01T00:00:00Z', reason='investigate',
                    evidence_ids=[], evidence_snapshot=None, reopen_if=None, synthesis_target=None)

    def assert_rejected(self, records):
        with self.assertRaises(ReplayError):
            replay(records)

    def test_success_projection_snapshot_and_approval(self):
        self.propose()
        state = replay(self.records)
        self.assertEqual(state.runs['R'].target_snapshot, parent_snapshot(state.hypotheses['H0']))
        proposal = state.branch_proposals['P']
        self.assertEqual(proposal['status'], 'pending')
        self.assertEqual(proposal['selected_ids'], [])
        self.assertIsNone(proposal['reason'])
        self.append(self.approval())
        state = replay(self.records)
        self.assertEqual(list(state.hypotheses), ['H0', 'H-C1', 'H-C3'])
        self.assertEqual(state.branch_proposals['P']['status'], 'accepted')
        self.assertEqual(state.branch_proposals['P']['selected_ids'], ['C3', 'C1'])
        self.assertEqual(state.hypotheses['H0'].status, 'suggested')
        self.assertTrue(all(node.status == 'suggested' for node in state.hypotheses.values()))
        self.records[3]['changes'][1]['candidates'][0]['claim'] = 'mutated'
        self.assertEqual(state.branch_proposals['P']['candidates'], payload()['candidates'])

    def test_old_non_fork_run_defaults_to_no_snapshot(self):
        self.start(operation='test')
        state = replay(self.records)
        self.assertIsNone(state.runs['R'].target_snapshot)
        self.assertEqual(state.branch_proposals, {})

    def test_fork_start_requires_one_parent_no_session_and_allowed_status(self):
        original = copy.deepcopy(self.records)
        for updates in ({'target_ids': []}, {'target_ids': ['H0', 'missing']}, {'session_id': 'S'}, {'target_ids': ['missing']}):
            self.records = copy.deepcopy(original)
            self.start(**updates)
            self.assert_rejected(self.records)
        self.records = original
        close = self.transition()
        close.update(to='suspended', trigger='suspend')
        self.append([close])
        self.start()
        self.assert_rejected(self.records)

    def test_fork_start_cannot_mix_parent_mutation_or_another_change(self):
        self.start()
        self.records[-1]['changes'].insert(0, created('H-other'))
        self.assert_rejected(self.records)

    def test_proposal_pairing_and_bindings_reject_forgery(self):
        self.propose()
        good = copy.deepcopy(self.records)
        mutations = [lambda c: c.pop(), lambda c: c.pop(0),
                     lambda c: c[-1].update(run_id='missing'), lambda c: c[-1].update(parent_id='missing'),
                     lambda c: c[-1]['parent_snapshot'].update(reason='forged'),
                     lambda c: c[-1]['candidates'][0].update(claim='different'),
                     lambda c: c.append(created('H-extra'))]
        for mutate in mutations:
            records = copy.deepcopy(good)
            mutate(records[-1]['changes'])
            self.assert_rejected(records)
        for operation in ('test', 'framing.propose'):
            records = copy.deepcopy(good)
            records[1]['changes'][0]['operation'] = operation
            self.assert_rejected(records)
        records = copy.deepcopy(good)
        records[-1]['actor'] = 'human:local'
        self.assert_rejected(records)

    def test_parent_equivalent_claim_rejected_even_when_run_output_matches(self):
        self.propose()
        for change in self.records[-1]['changes']:
            candidates = change['proposal']['candidates'] if change['kind'] == 'RunSucceeded' else change['candidates']
            candidates[0]['claim'] = '  ORIGINAL  claim  '
        self.assert_rejected(self.records)

    def test_changed_parent_cannot_forge_fresh_proposal_snapshot(self):
        self.start()
        self.append([self.transition()])
        self.records[-1]['at'] = '2026-01-01T00:00:00Z'
        self.append([dict(kind='RunDispatched', run_id='R')], 'agent:runner')
        snapshot = parent_snapshot(replay(self.records).hypotheses['H0'])
        self.append([dict(kind='RunSucceeded', run_id='R', proposal=payload(), usage=unknown_usage(), provider_request_id=None),
                     dict(kind='BranchProposed', proposal_id='P', run_id='R', parent_id='H0',
                          parent_snapshot=snapshot, candidates=payload()['candidates'])], 'agent:runner')
        self.assert_rejected(self.records)

    def test_pending_blocks_new_run_for_same_parent(self):
        self.propose()
        self.start(run_id='R2')
        self.assert_rejected(self.records)

    def test_hostile_approval_batches_preserve_store_bytes(self):
        self.propose()
        valid = self.approval()
        variants = [valid[:-1], valid + [created('H-extra')]]
        for mutate in (lambda c: c[-1].update(claim='forged'), lambda c: c[-1].update(parent_ids=[]),
                       lambda c: c[-1].update(assumptions=['forged']),
                       lambda c: c[0].update(selected_ids=[]), lambda c: c[0].update(selected_ids=['C1', 'C1']),
                       lambda c: c[0].update(selected_ids=['unknown']),
                       lambda c: c[0]['hypothesis_ids'].update(C2='H-extra'),
                       lambda c: c[0]['hypothesis_ids'].update(C1='H0'),
                       lambda c: c[0]['hypothesis_ids'].update(C1='H-C3')):
            changes = copy.deepcopy(valid)
            mutate(changes)
            variants.append(changes)
        with tempfile.TemporaryDirectory() as root, Store(root) as store:
            for record in self.records:
                store.append(record, expected_seq=record['seq'] - 1)
            before = store.path.read_bytes()
            for changes in variants:
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    store.append(event(seq=5, changes=changes), expected_seq=4)
                self.assertEqual(store.path.read_bytes(), before)

    def test_agent_stale_and_duplicate_approval_rejected(self):
        self.propose()
        pending = copy.deepcopy(self.records)
        self.append(self.approval(), 'agent:runner')
        self.assert_rejected(self.records)
        self.records = copy.deepcopy(pending)
        self.append([self.transition()])
        self.records[-1]['at'] = '2026-01-01T00:00:00Z'
        self.append(self.approval())
        self.assert_rejected(self.records)
        self.records = pending
        self.append(self.approval())
        self.append(self.approval())
        self.assert_rejected(self.records)

    def test_rejection_retains_reason_and_candidates_and_allows_new_run(self):
        self.propose()
        self.append([dict(kind='BranchRejected', proposal_id='P', reason='too broad')])
        self.start(run_id='R2')
        proposal = replay(self.records).branch_proposals['P']
        self.assertEqual((proposal['status'], proposal['reason']), ('rejected', 'too broad'))
        self.assertEqual(proposal['candidates'], payload()['candidates'])

    def test_rejection_requires_human_pending_and_separate_batch(self):
        self.propose()
        pending = copy.deepcopy(self.records)
        change = dict(kind='BranchRejected', proposal_id='P', reason='retry')
        for actor, changes in [('agent:runner', [change]), ('human:local', [change, created('H1')])]:
            self.records = copy.deepcopy(pending)
            self.append(changes, actor)
            self.assert_rejected(self.records)
        self.records = pending
        self.append([change])
        self.append([change])
        self.assert_rejected(self.records)

    def test_runner_allows_proposal_hook_but_never_graph_creation(self):
        with tempfile.TemporaryDirectory() as root:
            with Store(root) as store:
                store.append(self.records[0], expected_seq=0)
            runner = Runner(root)
            request = RunRequest('I-001', 'R', 'hypothesis.fork', 'fake', {}, target_ids=('H0',))
            adapter = FakeAdapter([RunSignal('succeeded', proposal=payload())])
            def extras(state, request, output):
                return [dict(kind='BranchProposed', proposal_id='P', run_id=request.run_id, parent_id='H0',
                             parent_snapshot=state.runs[request.run_id].target_snapshot, candidates=output['candidates'])]
            self.assertEqual(runner.execute(request, adapter, success_changes=extras).status, 'succeeded')
            self.assertEqual(list(runner.state().hypotheses), ['H0'])

