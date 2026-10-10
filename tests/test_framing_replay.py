import copy
import json
from pathlib import Path
import tempfile
import unittest

from inquiry.adapter import unknown_usage
from inquiry.replay import ReplayError, replay
from inquiry.store import Store, StoreError
from tests.test_events import event


class FramingReplayTests(unittest.TestCase):
    def setUp(self):
        self.records = [self.start()]
        self.frame = json.loads((Path(__file__).parent / 'fixtures/framing.json').read_text())[0]['frame']

    def start(self):
        return event(changes=[dict(kind='FramingStarted', session_id='S', seed='seed')])

    def append(self, changes, actor='human:local'):
        self.records.append(event(seq=len(self.records) + 1, changes=changes, actor=actor))

    def output(self, payload, operation, lifecycle):
        identity = 'R' + str(len(self.records))
        self.append([dict(kind='RunStarted', run_id=identity, operation=operation, model='fake',
                          target_ids=[], session_id='S', max_output_tokens=100, timeout=10)], 'agent:runner')
        self.append([dict(kind='RunDispatched', run_id=identity)], 'agent:runner')
        changes = [dict(kind='RunSucceeded', run_id=identity, proposal=payload,
                        usage=unknown_usage(), provider_request_id=None)]
        changes.extend(dict(c, run_id=identity) for c in lifecycle)
        self.append(changes, 'agent:runner')

    def questions(self, texts=None):
        texts = texts or ['one?', 'two?', 'three?']
        session = replay(self.records).framing_sessions['S']
        control = dict(mode='explore', mode_rationale='reason', done=False,
                       question_rationale='reason', questions=texts)
        self.output(control, 'framing.control', [
            dict(kind='FramingControlRecorded', session_id='S', control=control,
                 answered_qids=[q['qid'] for q in session.questions]),
            dict(kind='QuestionsIssued', session_id='S', batch_id='B' + str(len(self.records)),
                 questions=[dict(qid='Q' + str(len(session.questions) + n), text=t) for n, t in enumerate(texts)])])

    def answers(self):
        for question in replay(self.records).framing_sessions['S'].questions:
            if question['answer'] is None:
                self.append([dict(kind='AnswerRecorded', session_id='S', qid=question['qid'], answer='unknown')])

    def done(self):
        session = replay(self.records).framing_sessions['S']
        control = dict(mode='explore', mode_rationale='reason', done=True, question_rationale='', questions=[])
        self.output(control, 'framing.control', [dict(kind='FramingControlRecorded', session_id='S',
            control=control, answered_qids=[q['qid'] for q in session.questions])])

    def propose(self, identity='P'):
        session = replay(self.records).framing_sessions['S']
        self.output(self.frame, 'framing.propose', [dict(kind='FrameProposed', session_id='S', proposal_id=identity,
            frame=self.frame, qa=[dict(qid=q['qid'], question=q['text'], answer=q['answer']) for q in session.questions])])

    def ready(self):
        self.questions()
        self.answers()
        self.done()
        self.propose()

    def acceptance(self):
        mapping = {c['candidate_id']: 'H' + str(n) for n, c in enumerate(self.frame['hypotheses'])}
        return [dict(kind='FrameAccepted', session_id='S', proposal_id='P', inquiry_id='I-001', hypothesis_ids=mapping),
                dict(kind='InquiryCreated', seed='seed', frame=self.frame)] + [
            dict(kind='HypothesisCreated', hypothesis_id=mapping[c['candidate_id']], title=c['title'], claim=c['claim'],
                 parent_ids=[], assumptions=[], falsified_if=[]) for c in self.frame['hypotheses']]

    def test_approval_replay_and_detachment(self):
        self.ready()
        self.assertIsNone(replay(self.records).inquiry)
        self.append(self.acceptance())
        state = replay(self.records)
        self.assertEqual(state.framing_sessions['S'].status, 'accepted')
        self.assertTrue(all(h.status == 'suggested' for h in state.hypotheses.values()))
        self.frame['central_question'] = 'mutated'
        self.assertNotEqual(state.inquiry.frame['central_question'], 'mutated')
        self.assertEqual(state.framing_sessions['S'].accepted_proposal_id, 'P')

    def test_hostile_approval_is_atomic_and_preserves_store_bytes(self):
        self.ready()
        valid = self.acceptance()
        variants = [valid[:-1], valid[1:], valid + [valid[-1]], copy.deepcopy(valid), copy.deepcopy(valid)]
        variants[-2][1]['seed'] = 'wrong'
        variants[-1][-1]['claim'] = 'wrong'
        with tempfile.TemporaryDirectory() as root, Store(root) as store:
            for record in self.records:
                store.append(record, expected_seq=record['seq'] - 1)
            before = store.path.read_bytes()
            for changes in variants:
                with self.subTest(changes=changes), self.assertRaises((StoreError, ReplayError, ValueError)):
                    store.append(event(seq=len(self.records) + 1, changes=changes), expected_seq=len(self.records))
                self.assertEqual(store.path.read_bytes(), before)

    def test_output_pairing_and_qa_binding(self):
        self.ready()
        good = copy.deepcopy(self.records)
        mutations = [lambda c: c.pop(), lambda c: c.pop(0),
                     lambda c: c[-1]['qa'][0].update(answer='forged'),
                     lambda c: c[-1].update(frame=dict(c[-1]['frame'], purpose='different'))]
        for mutate in mutations:
            records = copy.deepcopy(good)
            mutate(records[-1]['changes'])
            with self.subTest(mutate=mutate), self.assertRaises(ReplayError):
                replay(records)

    def test_reject_then_regenerate_retains_history(self):
        self.ready()
        self.append([dict(kind='FrameRejected', session_id='S', proposal_id='P', reason='retry')])
        self.propose('P2')
        session = replay(self.records).framing_sessions['S']
        self.assertEqual(session.proposals['P']['status'], 'rejected')
        self.assertEqual(session.proposals['P2']['status'], 'pending')

    def test_pending_proposal_blocks_new_output(self):
        self.ready()
        self.propose('P2')
        with self.assertRaises(ReplayError):
            replay(self.records)

    def test_answers_require_human_existing_unanswered_question(self):
        self.questions()
        valid = copy.deepcopy(self.records)
        for actor, qid in [('agent:runner', 'Q0'), ('human:local', 'missing')]:
            self.records = copy.deepcopy(valid)
            self.append([dict(kind='AnswerRecorded', session_id='S', qid=qid, answer='answer')], actor)
            with self.assertRaises(ReplayError):
                replay(self.records)
        self.records = valid
        self.answers()
        self.append([dict(kind='AnswerRecorded', session_id='S', qid='Q0', answer='overwrite')])
        with self.assertRaises(ReplayError):
            replay(self.records)

    def test_five_answers_allow_frame_without_done_control(self):
        self.questions()
        self.answers()
        self.questions(['four?', 'five?'])
        self.answers()
        self.propose()
        self.assertEqual(len(replay(self.records).framing_sessions['S'].questions), 5)

    def test_three_answers_require_done_control(self):
        self.questions()
        self.answers()
        self.propose()
        with self.assertRaises(ReplayError):
            replay(self.records)

    def test_question_duplicates_and_pending_answers_block_new_batch(self):
        self.questions()
        original = copy.deepcopy(self.records)
        self.questions(['four?'])
        with self.assertRaises(ReplayError):
            replay(self.records)
        self.records = original
        self.answers()
        self.questions([' ONE? '])
        with self.assertRaises(ReplayError):
            replay(self.records)

    def test_cancel_resume_preserves_draft(self):
        records = [self.start(), event(seq=2, changes=[dict(kind='FramingCancelled', session_id='S', reason='pause')])]
        self.assertEqual(replay(records).framing_sessions['S'].status, 'cancelled')
        records.append(event(seq=3, changes=[dict(kind='FramingResumed', session_id='S', reason='continue')]))
        self.assertEqual(replay(records).framing_sessions['S'].status, 'active')

    def test_draft_blocks_direct_graph_creation(self):
        with self.assertRaises(ReplayError):
            replay([self.start(), event(seq=2)])

    def test_start_after_graph_rejected(self):
        with self.assertRaises(ReplayError):
            replay([event(), event(seq=2, changes=self.start()['changes'])])

    def test_invalid_cancel_actors_and_transitions(self):
        for actor in ('agent:model', 'user'):
            with self.subTest(actor=actor), self.assertRaises(ReplayError):
                replay([self.start(), event(seq=2, actor=actor, changes=[dict(kind='FramingCancelled', session_id='S', reason='pause')])])
        with self.assertRaises(ReplayError):
            replay([self.start(), event(seq=2, changes=[dict(kind='FramingResumed', session_id='S', reason='resume')])])
