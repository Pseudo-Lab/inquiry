"""Branch lifecycle batch validation and detached projection updates."""
from copy import deepcopy

from .branch_schema import BRANCH_PARENT_STATES, parent_snapshot, validate_branch


KINDS = frozenset({'BranchProposed', 'BranchRejected', 'BranchAccepted'})


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _parent(hypotheses, identity):
    parent = hypotheses.get(identity)
    _require(parent is not None and parent.status in BRANCH_PARENT_STATES,
             'Branch requires an existing active parent.')
    return parent


def _no_pending(proposals, parent_id):
    _require(not any(p['parent_id'] == parent_id and p['status'] == 'pending'
                     for p in proposals.values()), 'Resolve the pending branch proposal first.')


def validate_batch(event, proposals, runs, hypotheses):
    changes = event['changes']
    for change in changes:
        if change['kind'] == 'RunStarted' and change['operation'] == 'hypothesis.fork':
            _require(len(changes) == 1, 'Branch run start must be stored separately.')
            _require(len(change['target_ids']) == 1 and change['session_id'] is None,
                     'Branch run requires exactly one parent and no framing session.')
            parent_id = change['target_ids'][0]
            _parent(hypotheses, parent_id)
            _no_pending(proposals, parent_id)
    successes = [c for c in changes if c['kind'] == 'RunSucceeded'
                 and c['run_id'] in runs and runs[c['run_id']].operation == 'hypothesis.fork']
    lifecycle = [c for c in changes if c['kind'] in KINDS]
    for success in successes:
        _require(sum(c['kind'] == 'BranchProposed' and c.get('run_id') == success['run_id']
                     for c in lifecycle) == 1, 'Branch success requires its proposal atomically.')
    for change in lifecycle:
        kind = change['kind']
        if kind == 'BranchProposed':
            _require(event['actor'] == 'agent:runner', 'Invalid branch output producer.')
            _require(sorted(c['kind'] for c in changes) == ['BranchProposed', 'RunSucceeded'],
                     'Invalid branch proposal batch.')
            _require(change['proposal_id'] not in proposals, 'Duplicate branch proposal identity.')
            run = runs.get(change['run_id'])
            _require(run is not None and run.operation == 'hypothesis.fork'
                     and run.target_ids == (change['parent_id'],) and run.session_id is None,
                     'Branch output run mismatch.')
            matched = [c for c in successes if c['run_id'] == run.id]
            _require(len(matched) == 1, 'Branch output requires matching success.')
            parent = _parent(hypotheses, change['parent_id'])
            _no_pending(proposals, parent.id)
            _require(run.target_snapshot == change['parent_snapshot'] == parent_snapshot(parent),
                     'Branch parent snapshot changed or does not match the run start.')
            output = validate_branch({'candidates': change['candidates']})
            _require(matched[0]['proposal'] == output, 'Branch candidates do not match run output.')
            normalized = ' '.join(parent.claim.split()).casefold()
            _require(all(' '.join(c['claim'].split()).casefold() != normalized for c in output['candidates']),
                     'Branch candidate repeats the parent claim.')
        else:
            _require(event['actor'].startswith('human:') and bool(event['actor'][6:].strip()),
                     'Branch decision requires a human actor.')
            proposal = proposals.get(change['proposal_id'])
            _require(proposal is not None and proposal['status'] == 'pending', 'Branch proposal is not pending.')
            if kind == 'BranchRejected':
                _require(len(changes) == 1, 'Branch rejection must be stored separately.')
                continue
            parent = _parent(hypotheses, proposal['parent_id'])
            _require(parent_snapshot(parent) == proposal['parent_snapshot'], 'Branch parent snapshot changed.')
            selected = change['selected_ids']
            candidates = proposal['candidates']
            _require(1 <= len(selected) <= 4 and len(set(selected)) == len(selected)
                     and set(selected) <= {c['candidate_id'] for c in candidates}, 'Invalid branch selection.')
            mapping = change['hypothesis_ids']
            _require(set(mapping) == set(selected), 'Branch candidate mapping mismatch.')
            _require(len(set(mapping.values())) == len(mapping) and not set(mapping.values()) & set(hypotheses),
                     'Branch hypothesis identities must be fresh and unique.')
            expected = [change] + [
                dict(kind='HypothesisCreated', hypothesis_id=mapping[c['candidate_id']],
                     title=c['title'], claim=c['claim'], parent_ids=[parent.id], assumptions=[], falsified_if=[])
                for c in candidates if c['candidate_id'] in mapping]
            _require(changes == expected, 'Approval must create exactly its selected candidates atomically.')


def apply_change(change, proposals):
    identity = change['proposal_id']
    kind = change['kind']
    if kind == 'BranchProposed':
        proposal = dict(id=identity, run_id=change['run_id'], parent_id=change['parent_id'],
                        parent_snapshot=change['parent_snapshot'], candidates=change['candidates'],
                        status='pending', selected_ids=[], hypothesis_ids={}, reason=None)
    elif kind == 'BranchRejected':
        proposal = dict(proposals[identity], status='rejected', reason=change['reason'])
    else:
        proposal = dict(proposals[identity], status='accepted', selected_ids=change['selected_ids'],
                        hypothesis_ids=change['hypothesis_ids'])
    proposals[identity] = deepcopy(proposal)
