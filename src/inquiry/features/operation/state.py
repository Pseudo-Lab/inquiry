"""Pure operation lifecycle validation and detached projection updates."""

from copy import deepcopy

from inquiry.features.branch.schema import parent_snapshot
from inquiry.features.operation.schema import eligible_targets, validate_operation


KINDS = frozenset({'OperationProposed', 'OperationRejected', 'OperationAccepted',
                   'HypothesisRefined', 'ReviewNoteCreated'})


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _normalized(value):
    return ' '.join(value.split()).casefold()


def _validate_additions(output, hypothesis):
    for field in ('assumptions', 'falsified_if'):
        existing = {_normalized(item) for item in getattr(hypothesis, field)}
        incoming = {_normalized(item) for item in output[field]}
        _require(not existing & incoming, f'Deepen repeats an existing {field} item.')


def validate_batch(event, proposals, notes, runs, hypotheses):
    changes = event['changes']
    for change in changes:
        if change['kind'] == 'RunStarted' and change['operation'].startswith('hypothesis.'):
            operation = change['operation'].split('.', 1)[1]
            if operation in ('deepen', 'challenge', 'synthesize'):
                _require(operation in ('deepen', 'challenge', 'synthesize'), 'Operation is not implemented yet.')
                _require(len(changes) == 1 and change['session_id'] is None,
                         'Operation run start must be stored separately without a session.')
                targets = eligible_targets(operation, hypotheses, change['target_ids'])
                _require(not any(p['operation'] == operation
                                 and tuple(p['target_ids']) == targets and p['status'] == 'pending'
                                 for p in proposals.values()), 'Resolve the pending operation proposal first.')

    successes = [c for c in changes if c['kind'] == 'RunSucceeded'
                 and c['run_id'] in runs and runs[c['run_id']].operation
                 in ('hypothesis.deepen', 'hypothesis.challenge', 'hypothesis.synthesize')]
    lifecycle = [c for c in changes if c['kind'] in KINDS]
    for success in successes:
        _require(sum(c['kind'] == 'OperationProposed' and c.get('run_id') == success['run_id']
                     for c in lifecycle) == 1, 'Operation success requires its proposal atomically.')

    for change in lifecycle:
        kind = change['kind']
        if kind in ('HypothesisRefined', 'ReviewNoteCreated'):
            _require(any(c['kind'] == 'OperationAccepted'
                         and c['proposal_id'] == change['proposal_id'] for c in lifecycle),
                     'Refinement requires its acceptance atomically.')
            continue
        if kind == 'OperationProposed':
            _require(event['actor'] == 'agent:runner', 'Invalid operation output producer.')
            _require(sorted(c['kind'] for c in changes) == ['OperationProposed', 'RunSucceeded'],
                     'Invalid operation proposal batch.')
            _require(change['proposal_id'] not in proposals, 'Duplicate operation proposal identity.')
            _require(change['operation'] in ('deepen', 'challenge', 'synthesize'), 'Operation is not implemented yet.')
            operation = change['operation']
            targets = eligible_targets(operation, hypotheses, change['target_ids'])
            run = runs.get(change['run_id'])
            _require(run is not None and run.operation == 'hypothesis.' + operation
                     and run.target_ids == targets and run.session_id is None,
                     'Operation output run mismatch.')
            matched = [c for c in successes if c['run_id'] == run.id]
            _require(len(matched) == 1, 'Operation output requires matching success.')
            snapshot = {identity: parent_snapshot(hypotheses[identity]) for identity in targets}
            _require(run.target_snapshot == change['target_snapshot'] == snapshot,
                     'Operation target snapshot changed or does not match the run start.')
            output = validate_operation(operation, change['output'])
            _require(matched[0]['proposal'] == output, 'Operation output does not match run output.')
            if operation == 'deepen':
                _validate_additions(output, hypotheses[targets[0]])
            _require(not any(p['operation'] == operation and tuple(p['target_ids']) == targets
                             and p['status'] == 'pending' for p in proposals.values()),
                     'Resolve the pending operation proposal first.')
            continue

        _require(event['actor'].startswith('human:') and bool(event['actor'][6:].strip()),
                 'Operation decision requires a human actor.')
        proposal = proposals.get(change['proposal_id'])
        _require(proposal is not None and proposal['status'] == 'pending',
                 'Operation proposal is not pending.')
        if kind == 'OperationRejected':
            _require(len(changes) == 1, 'Operation rejection must be stored separately.')
            continue
        _require(kind == 'OperationAccepted', 'Unsupported operation effect.')
        targets = eligible_targets(proposal['operation'], hypotheses, proposal['target_ids'])
        snapshot = {identity: parent_snapshot(hypotheses[identity]) for identity in targets}
        _require(snapshot == proposal['target_snapshot'], 'Operation target snapshot changed.')
        operation = proposal['operation']
        output = validate_operation(operation, proposal['output'])
        if operation == 'deepen':
            _validate_additions(output, hypotheses[targets[0]])
            expected = [change, dict(kind='HypothesisRefined', proposal_id=proposal['id'],
                hypothesis_id=targets[0], assumptions=output['assumptions'],
                falsified_if=output['falsified_if'], reason=output['reason'])]
            _require(change['result_id'] == targets[0] and changes == expected,
                     'Deepen approval must apply exactly its saved additions atomically.')
        elif operation == 'challenge':
            expected = [change, dict(kind='ReviewNoteCreated', note_id=change['result_id'],
                proposal_id=proposal['id'], hypothesis_id=targets[0],
                objections=output['objections'])]
            _require(change['result_id'] not in notes and changes == expected,
                     'Challenge approval must create exactly its saved review note atomically.')
        elif operation == 'synthesize':
            result_id = change['result_id']
            expected = [change,
                dict(kind='HypothesisCreated', hypothesis_id=result_id,
                     title=output['title'], claim=output['claim'], parent_ids=list(targets),
                     assumptions=output['assumptions'], falsified_if=output['falsified_if'])]
            expected.extend(dict(kind='HypothesisStateChanged', hypothesis_id=target,
                                 **{'from': hypotheses[target].status, 'to': 'synthesized'},
                                 trigger='synthesize', actor=event['actor'], at=event['at'],
                                 reason=output['reason'], evidence_ids=[], evidence_snapshot=None,
                                 reopen_if=None, synthesis_target=result_id) for target in targets)
            _require(result_id not in hypotheses and changes == expected,
                     'Synthesis approval must create its saved child and transition every parent atomically.')
        else:
            _require(False, 'Operation is not implemented yet.')


def apply_change(change, event, proposals, notes):
    kind = change['kind']
    if kind == 'OperationProposed':
        output = change['output']
        proposal = dict(id=change['proposal_id'], run_id=change['run_id'],
                        operation=change['operation'], target_ids=change['target_ids'],
                        target_snapshot=change['target_snapshot'], output=output,
                        status='pending', result_id=None, reason=output.get('reason'))
        proposals[proposal['id']] = deepcopy(proposal)
    elif kind == 'OperationRejected':
        proposals[change['proposal_id']] = deepcopy(dict(
            proposals[change['proposal_id']], status='rejected', reason=change['reason']))
    elif kind == 'OperationAccepted':
        proposals[change['proposal_id']] = deepcopy(dict(
            proposals[change['proposal_id']], status='accepted', result_id=change['result_id']))
    elif kind == 'ReviewNoteCreated':
        proposal = proposals[change['proposal_id']]
        notes[change['note_id']] = deepcopy(dict(
            id=change['note_id'], hypothesis_id=change['hypothesis_id'],
            proposal_id=change['proposal_id'], run_id=proposal['run_id'],
            objections=change['objections'], origin='model-opinion',
            approved_by=event['actor'], approved_at=event['at']))
