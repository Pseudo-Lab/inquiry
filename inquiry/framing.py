"""Durable human-approved framing; provider execution stays behind Runner."""
from dataclasses import asdict
from datetime import datetime, timezone
import math
from pathlib import Path
from uuid import uuid4

from .adapter import RunRequest
from .commands import _hypothesis, _next_id
from .framing_schema import CONTROL_SCHEMA, FRAME_SCHEMA, validate_questions, validate_frame
from .framing_prompts import FACILITATOR_SYSTEM, FRAMER_SYSTEM
from .replay import replay
from .runs import Runner
from .store import Store


def _session(state, identity):
    session = state.framing_sessions.get(identity)
    if session is None:
        raise ValueError('Framing session does not exist.')
    return session


def _qa(session):
    return [dict(qid=q['qid'], question=q['text'], answer=q['answer'])
            for q in session.questions if q['answer'] is not None]


class FramingService:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def state(self):
        return replay(Store(self.root).read_all())

    def _commit(self, build, actor='human:local'):
        with Store(self.root) as store:
            state = replay(store.read_all())
            changes, result = build(state)
            if changes:
                event = dict(schema_version=1, event_id=uuid4().hex,
                             seq=state.last_seq + 1, inquiry_id=state.inquiry_id or 'I-' + uuid4().hex,
                             actor=actor, at=datetime.now(timezone.utc).isoformat(),
                             type='changes-committed', changes=changes)
                store.append(event, expected_seq=state.last_seq)
            return result

    def start(self, seed):
        identity = 'F-' + uuid4().hex
        def build(state):
            if state.inquiry is not None:
                raise ValueError('Inquiry already initialized.')
            return [dict(kind='FramingStarted', session_id=identity, seed=seed)], identity
        return self._commit(build)

    def view(self, session_id):
        session = _session(self.state(), session_id)
        result = asdict(session)
        result['outstanding_questions'] = [q for q in result['questions'] if q['answer'] is None]
        result['pending_proposal'] = next((p for p in result['proposals'].values()
                                           if p['status'] == 'pending'), None)
        return result

    def answer(self, session_id, qid, text):
        def build(state):
            session = _session(state, session_id)
            if session.status != 'active':
                raise ValueError('Answer requires an active session.')
            question = next((q for q in session.questions if q['qid'] == qid), None)
            if question is None:
                raise ValueError('Question does not exist.')
            if question['answer'] is not None:
                if question['answer'] == text:
                    return [], None
                raise ValueError('Question already has a different saved answer.')
            return [dict(kind='AnswerRecorded', session_id=session_id, qid=qid, answer=text)], None
        self._commit(build)
        return self.view(session_id)

    def cancel(self, session_id, reason='user-cancelled'):
        self._change(session_id, 'FramingCancelled', reason=reason)
        return self.view(session_id)

    def _change(self, session_id, kind, *, actor='human:local', **fields):
        def build(state):
            _session(state, session_id)
            return [dict(kind=kind, session_id=session_id, **fields)], None
        self._commit(build, actor)

    def resume(self, session_id):
        _session(self.state(), session_id)
        Runner(self.root).recover()
        def build(state):
            session = _session(state, session_id)
            if session.status != 'cancelled':
                return [], None
            return [dict(kind='FramingResumed', session_id=session_id, reason='user-resumed')], None
        self._commit(build)
        return self.view(session_id)

    def reject(self, session_id, proposal_id, reason):
        self._change(session_id, 'FrameRejected', proposal_id=proposal_id, reason=reason)
        return self.view(session_id)

    def accept(self, session_id, proposal_id):
        def build(state):
            session = _session(state, session_id)
            proposal = session.proposals.get(proposal_id)
            if proposal is None:
                raise ValueError('Proposal does not exist.')
            if session.status == 'accepted' and session.accepted_proposal_id == proposal_id:
                return [], dict(inquiry_id=state.inquiry_id, hypothesis_ids=dict(proposal['hypothesis_ids']))
            if session.status != 'active' or proposal['status'] != 'pending':
                raise ValueError('Acceptance requires an active session and pending proposal.')
            mapping, used = {}, dict(state.hypotheses)
            changes = []
            for candidate in proposal['frame']['hypotheses']:
                identity = _next_id('H', used)
                used[identity] = True
                mapping[candidate['candidate_id']] = identity
                changes.append(_hypothesis(identity, candidate['title'], candidate['claim']))
            result = dict(inquiry_id=state.inquiry_id, hypothesis_ids=mapping)
            return [dict(kind='FrameAccepted', session_id=session_id, proposal_id=proposal_id, **result),
                    dict(kind='InquiryCreated', seed=session.seed, frame=proposal['frame']), *changes], result
        return self._commit(build)

    def advance(self, session_id, adapter=None, *, model='fake', regenerate=False, cancelled=None,
                adapter_factory=None, max_output_tokens=None, timeout=30.0):
        if adapter is not None and adapter_factory is not None:
            raise ValueError('Provide either adapter or adapter_factory, not both.')
        if (max_output_tokens is not None and
                (type(max_output_tokens) is not int or max_output_tokens <= 0)):
            raise ValueError('expected positive integer max_output_tokens')
        if (isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or
                not math.isfinite(timeout) or timeout <= 0):
            raise ValueError('expected positive finite timeout')
        state = self.state()
        session = _session(state, session_id)
        if session.status == 'accepted':
            return self.view(session_id)
        if state.inquiry is not None:
            raise ValueError('Inquiry already initialized from another session.')
        if session.status != 'active':
            raise ValueError('Cancelled framing requires explicit resume.')
        if any(q['answer'] is None for q in session.questions):
            return self.view(session_id)
        if any(p['status'] == 'pending' for p in session.proposals.values()):
            return self.view(session_id)
        rejected = bool(session.proposals)
        if rejected and not regenerate:
            raise ValueError('Rejected proposal requires explicit regeneration.')
        if regenerate and not rejected:
            raise ValueError('Regeneration requires a rejected proposal.')
        qa = _qa(session)
        done = (len(qa) == 5 or rejected or
                (session.control is not None and session.control['done'] and
                 tuple(q['qid'] for q in qa) == session.control_answered_qids))
        operation = 'framing.propose' if done else 'framing.control'
        if adapter_factory is not None:
            binding = adapter_factory()
            if not isinstance(binding, tuple) or len(binding) != 2:
                raise ValueError('Adapter factory must return (adapter, model).')
            adapter, model = binding
        if adapter is None:
            raise ValueError('No framing adapter configured.')
        snapshot = asdict(session)
        context = dict(system=FRAMER_SYSTEM if done else FACILITATOR_SYSTEM,
                       output_schema=FRAME_SCHEMA if done else CONTROL_SCHEMA,
                       seed=session.seed, qa=qa)
        if done:
            feedback = [dict(frame=p['frame'], reason=p.get('reason'))
                        for p in session.proposals.values() if p['status'] == 'rejected']
            if feedback:
                context['rejected'] = feedback
        request = RunRequest(inquiry_id=state.inquiry_id, run_id='R-' + uuid4().hex,
                             operation=operation, model=model, session_id=session_id,
                             max_output_tokens=max_output_tokens or (16000 if done else 4000),
                             timeout=timeout, context=context)
        def preflight(current):
            if current.inquiry is not None:
                raise ValueError('Inquiry already initialized from another session.')
            if asdict(_session(current, session_id)) != snapshot:
                raise ValueError('Framing changed; reload the saved session.')
        def success(current, actual_request, output):
            preflight(current)
            if done:
                validated = validate_frame(output)
                return [dict(kind='FrameProposed', session_id=session_id,
                             proposal_id='P-' + uuid4().hex, run_id=actual_request.run_id,
                             frame=validated, qa=qa)]
            validated = validate_questions(output, len(session.questions))
            previous = {' '.join(q['text'].split()).casefold() for q in session.questions}
            if any(' '.join(text.split()).casefold() in previous for text in validated['questions']):
                raise ValueError('Question duplicates an earlier question.')
            changes = [dict(kind='FramingControlRecorded', session_id=session_id,
                            run_id=actual_request.run_id, control=validated,
                            answered_qids=[q['qid'] for q in qa])]
            if not validated['done']:
                changes.append(dict(kind='QuestionsIssued', session_id=session_id,
                                    run_id=actual_request.run_id, batch_id='B-' + uuid4().hex,
                                    questions=[dict(qid='Q-' + uuid4().hex, text=text)
                                               for text in validated['questions']]))
            return changes
        def cancellation(current, actual_request, reason):
            preflight(current)
            return [dict(kind='FramingCancelled', session_id=session_id, reason=reason)]
        run = Runner(self.root).execute(request, adapter, cancelled=cancelled,
                                        preflight=preflight, success_changes=success,
                                        cancellation_changes=cancellation)
        if run.status == 'cancelled':
            return self.view(session_id)
        if run.status != 'succeeded':
            raise ValueError(f'Framing run {run.id} failed: {run.reason}. Inspect saved state before retrying.')
        if not done and run.proposal['done']:
            if adapter_factory is not None:
                return self.advance(session_id, model=model, cancelled=cancelled,
                                    adapter_factory=adapter_factory,
                                    max_output_tokens=max_output_tokens, timeout=timeout)
            return self.advance(session_id, adapter, model=model, cancelled=cancelled,
                                max_output_tokens=max_output_tokens, timeout=timeout)
        return self.view(session_id)
