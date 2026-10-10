"""Framing lifecycle validation and detached projection updates."""
from dataclasses import replace

from .framing_schema import validate_frame, validate_questions


KINDS = frozenset({'FramingControlRecorded', 'QuestionsIssued', 'AnswerRecorded',
                   'FrameProposed', 'FramingCancelled', 'FramingResumed',
                   'FrameRejected', 'FrameAccepted'})


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_batch(event, sessions, runs, inquiry, hypotheses, batches):
    changes = event['changes']
    if any(c['kind'] == 'FramingStarted' for c in changes):
        _require(len(changes) == 1, 'Framing start must be a separate draft event.')
    for change in changes:
        if change['kind'] == 'RunStarted' and change['operation'] in ('framing.control', 'framing.propose'):
            _require(len(changes) == 1, 'Framing run start must be stored separately.')
            session = sessions.get(change['session_id'])
            _require(inquiry is None and session is not None and session.status == 'active',
                     'Framing run requires an active draft without an inquiry.')
    lifecycle = [c for c in changes if c['kind'] in KINDS]
    successes = [c for c in changes if c['kind'] == 'RunSucceeded'
                 and c['run_id'] in runs and runs[c['run_id']].operation in ('framing.control', 'framing.propose')]
    for success in successes:
        operation = runs[success['run_id']].operation
        kind = 'FramingControlRecorded' if operation == 'framing.control' else 'FrameProposed'
        _require(sum(c['kind'] == kind and c.get('run_id') == success['run_id'] for c in lifecycle) == 1,
                 'Framing success requires its lifecycle record atomically.')
    accepts = [c for c in lifecycle if c['kind'] == 'FrameAccepted']
    if sessions and inquiry is None and any(c['kind'] in ('InquiryCreated', 'HypothesisCreated') for c in changes):
        _require(len(accepts) == 1, 'Draft graph creation requires approval.')
    for change in lifecycle:
        kind = change['kind']
        session = sessions.get(change['session_id'])
        _require(session is not None, 'Framing session does not exist.')
        expected_status = 'cancelled' if kind == 'FramingResumed' else 'active'
        _require(session.status == expected_status, 'Invalid framing session state.')
        if kind in ('FramingControlRecorded', 'QuestionsIssued', 'FrameProposed'):
            _require(inquiry is None, 'Framing output cannot follow inquiry creation.')
            _require(event['actor'] == 'agent:runner', 'Invalid framing output producer.')
            _require(not any(p['status'] == 'pending' for p in session.proposals.values()),
                     'Resolve pending proposal before new output.')
            _require(all(q['answer'] is not None for q in session.questions), 'Answer pending questions first.')
            run = runs.get(change['run_id'])
            operation = 'framing.propose' if kind == 'FrameProposed' else 'framing.control'
            _require(run is not None and run.operation == operation and run.session_id == session.id,
                     'Framing output run mismatch.')
            matched = [c for c in successes if c['run_id'] == run.id]
            _require(len(matched) == 1, 'Framing output requires matching success.')
            if kind == 'QuestionsIssued':
                controls = [c for c in lifecycle if c['kind'] == 'FramingControlRecorded'
                            and c['session_id'] == session.id and c['run_id'] == run.id]
                _require(len(controls) == 1, 'Questions require matching control.')
                control = validate_questions(controls[0]['control'], len(session.questions))
                _require(not control['done'], 'Completed control cannot issue questions.')
                _require(change['batch_id'] not in batches, 'Duplicate question batch.')
                qids = [q['qid'] for q in change['questions']]
                _require(len(set(qids)) == len(qids) and not set(qids) & {q['qid'] for q in session.questions},
                         'Duplicate question identity.')
                _require([q['text'] for q in change['questions']] == controls[0]['control']['questions'],
                         'Question texts must match control.')
            elif kind == 'FramingControlRecorded':
                control = validate_questions(change['control'], len(session.questions))
                _require(matched[0]['proposal'] == control, 'Control does not match run output.')
                _require(change['answered_qids'] == [q['qid'] for q in session.questions if q['answer'] is not None],
                         'Control QA binding mismatch.')
                expected = ['RunSucceeded', 'FramingControlRecorded'] + ([] if control['done'] else ['QuestionsIssued'])
                _require(sorted(c['kind'] for c in changes) == sorted(expected), 'Invalid control batch.')
                previous = {' '.join(q['text'].split()).casefold() for q in session.questions}
                normalized = {' '.join(q.split()).casefold() for q in control['questions']}
                _require(len(normalized) == len(control['questions']) and not previous & normalized,
                         'Repeated question text.')
            else:
                frame = validate_frame(change['frame'])
                _require(sorted(c['kind'] for c in changes) == ['FrameProposed', 'RunSucceeded'], 'Invalid proposal batch.')
                _require(matched[0]['proposal'] == frame, 'Frame does not match run output.')
                _require(3 <= len(session.questions) <= 5, 'Frame requires three to five answers.')
                qa = [dict(qid=q['qid'], question=q['text'], answer=q['answer']) for q in session.questions]
                _require(change['qa'] == qa, 'Proposal must preserve exact persisted QA.')
                ready = session.control is not None and session.control['done'] and session.control_answered_qids == tuple(q['qid'] for q in session.questions)
                _require(len(session.questions) == 5 or ready, 'Frame requires current done control.')
                _require(change['proposal_id'] not in session.proposals, 'Duplicate proposal identity.')
        else:
            human = event['actor'].startswith('human:') and bool(event['actor'][6:].strip())
            _require(human or (kind == 'FramingCancelled' and event['actor'] == 'agent:runner'),
                     'Framing decision requires a human actor.')
            if kind != 'FrameAccepted':
                allowed = len(changes) == 1
                if kind == 'FramingCancelled' and event['actor'] == 'agent:runner':
                    cancellations = [c for c in changes if c['kind'] == 'RunCancelled']
                    allowed = (len(changes) == 2 and len(cancellations) == 1
                        and cancellations[0]['run_id'] in runs
                        and runs[cancellations[0]['run_id']].session_id == session.id
                        and cancellations[0]['reason'] == change['reason'])
                _require(allowed, 'Invalid framing decision batch.')
            if kind == 'AnswerRecorded':
                question = next((q for q in session.questions if q['qid'] == change['qid']), None)
                _require(question is not None and question['answer'] is None, 'Question missing or already answered.')
            elif kind in ('FrameRejected', 'FrameAccepted'):
                proposal = session.proposals.get(change['proposal_id'])
                _require(proposal is not None and proposal['status'] == 'pending', 'Proposal is not pending.')
                if kind == 'FrameAccepted':
                    _require(inquiry is None and change['inquiry_id'] == event['inquiry_id'], 'Invalid inquiry approval identity.')
                    mapping = change['hypothesis_ids']
                    candidates = proposal['frame']['hypotheses']
                    _require(set(mapping) == {c['candidate_id'] for c in candidates}, 'Candidate mapping mismatch.')
                    _require(len(set(mapping.values())) == len(mapping) and not set(mapping.values()) & set(hypotheses),
                             'Hypothesis identities must be fresh and unique.')
                    expected = [change, dict(kind='InquiryCreated', seed=session.seed, frame=proposal['frame'])]
                    expected += [dict(kind='HypothesisCreated', hypothesis_id=mapping[c['candidate_id']],
                                      title=c['title'], claim=c['claim'], parent_ids=[], assumptions=[], falsified_if=[])
                                 for c in candidates]
                    _require(changes == expected, 'Approval must create exactly its inquiry and candidates atomically.')


def apply_change(change, sessions, batches):
    session = sessions[change['session_id']]
    kind = change['kind']
    updates = {}
    if kind == 'FramingControlRecorded':
        updates = dict(control=change['control'], control_answered_qids=tuple(change['answered_qids']))
    elif kind == 'QuestionsIssued':
        batches.add(change['batch_id'])
        updates['questions'] = session.questions + tuple(dict(q, answer=None) for q in change['questions'])
    elif kind == 'AnswerRecorded':
        updates['questions'] = tuple(dict(q, answer=change['answer']) if q['qid'] == change['qid'] else q for q in session.questions)
    elif kind in ('FramingCancelled', 'FramingResumed'):
        updates['status'] = 'cancelled' if kind == 'FramingCancelled' else 'active'
    elif kind == 'FrameProposed':
        proposal = dict(id=change['proposal_id'], run_id=change['run_id'], frame=change['frame'],
                        qa=change['qa'], status='pending', hypothesis_ids={}, reason=None)
        updates['proposals'] = dict(session.proposals, **{proposal['id']: proposal})
    elif kind in ('FrameRejected', 'FrameAccepted'):
        identity = change['proposal_id']
        proposal = dict(session.proposals[identity], status='rejected' if kind == 'FrameRejected' else 'accepted')
        if kind == 'FrameRejected':
            proposal['reason'] = change.get('reason')
        if kind == 'FrameAccepted':
            proposal['hypothesis_ids'] = change['hypothesis_ids']
            updates.update(status='accepted', accepted_proposal_id=identity)
        updates['proposals'] = dict(session.proposals, **{identity: proposal})
    sessions[session.id] = replace(session, **updates)
