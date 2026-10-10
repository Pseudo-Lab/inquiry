"""Human-approved hypothesis operations using the durable Runner boundary."""

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from inquiry.llm.adapter import RunRequest, _number, _string
from inquiry.features.branch.schema import parent_snapshot
from inquiry.commands import _hypothesis, _next_id, _transition
from inquiry.features.operation.prompts import OPERATION_PROMPTS
from inquiry.features.operation.schema import OPERATION_SCHEMAS, eligible_targets, validate_operation
from inquiry.domain.replay import replay
from inquiry.llm.runs import Runner
from inquiry.store.store import Store


class OperationsService:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def state(self):
        return replay(Store(self.root).read_all())

    @staticmethod
    def _view(state, proposal_id):
        proposal = state.operation_proposals.get(proposal_id)
        if proposal is None:
            raise ValueError('Operation proposal does not exist.')
        result = deepcopy(proposal)
        try:
            targets = eligible_targets(proposal['operation'], state.hypotheses, proposal['target_ids'])
            current = {identity: parent_snapshot(state.hypotheses[identity]) for identity in targets}
            stale = current != proposal['target_snapshot']
        except ValueError:
            stale = True
        result['stale'] = proposal['status'] == 'pending' and stale
        return result

    def view(self, proposal_id):
        return self._view(self.state(), proposal_id)

    def list_proposals(self, operation=None):
        if operation is not None and operation not in OPERATION_SCHEMAS:
            raise ValueError('Unsupported operation.')
        state = self.state()
        return [self._view(state, proposal['id']) for proposal in state.operation_proposals.values()
                if operation is None or proposal['operation'] == operation]

    def notes(self, hypothesis_id):
        state = self.state()
        if hypothesis_id not in state.hypotheses:
            raise ValueError('Hypothesis does not exist.')
        return [deepcopy(note) for note in state.review_notes.values()
                if note['hypothesis_id'] == hypothesis_id]

    def _commit(self, build):
        with Store(self.root) as store:
            state = replay(store.read_all())
            if state.inquiry is None:
                raise ValueError('Inquiry does not exist.')
            at = datetime.now(timezone.utc).isoformat()
            changes, result = build(state, at)
            if changes:
                store.append(dict(schema_version=1, event_id=uuid4().hex, seq=state.last_seq + 1,
                    inquiry_id=state.inquiry_id, actor='human:local', at=at,
                    type='changes-committed', changes=changes), expected_seq=state.last_seq)
            return result

    def propose(self, operation, target_ids, adapter=None, *, adapter_factory=None, model='fake',
                max_output_tokens=4000, timeout=60.0, cancelled=None):
        if operation not in OPERATION_SCHEMAS:
            raise ValueError('Unsupported operation.')
        if adapter is not None and adapter_factory is not None:
            raise ValueError('Provide either adapter or adapter_factory, not both.')
        if not isinstance(target_ids, (list, tuple)):
            raise ValueError('Targets must be a list or tuple.')
        for identity in target_ids:
            _string(identity)
        targets = tuple(sorted(target_ids))
        if len(set(targets)) != len(targets):
            raise ValueError('Targets must be unique.')
        if type(max_output_tokens) is not int or max_output_tokens <= 0:
            raise ValueError('Expected positive integer max_output_tokens.')
        if not _number(timeout) or timeout <= 0:
            raise ValueError('Expected positive finite timeout.')
        state = self.state()
        for proposal in state.operation_proposals.values():
            if proposal['operation'] == operation and tuple(proposal['target_ids']) == targets \
                    and proposal['status'] == 'pending':
                return self._view(state, proposal['id'])
        if state.inquiry is None:
            raise ValueError('Accept a framing proposal or initialize an inquiry first.')
        targets = eligible_targets(operation, state.hypotheses, targets)
        if any(run.status == 'started' for run in state.runs.values()):
            raise ValueError('Unfinished runs require explicit recovery.')
        snapshot = {identity: parent_snapshot(state.hypotheses[identity]) for identity in targets}
        if adapter_factory is not None:
            binding = adapter_factory()
            if not isinstance(binding, tuple) or len(binding) != 2:
                raise ValueError('Adapter factory must return (adapter, model).')
            adapter, model = binding
        if adapter is None:
            raise ValueError('No operation adapter configured.')
        request = RunRequest(inquiry_id=state.inquiry_id, run_id='R-' + uuid4().hex,
            operation='hypothesis.' + operation, model=model, target_ids=targets,
            max_output_tokens=max_output_tokens, timeout=timeout,
            context=dict(system=OPERATION_PROMPTS[operation], output_schema=OPERATION_SCHEMAS[operation],
                         inquiry_frame=deepcopy(state.inquiry.frame),
                         parents=[deepcopy(snapshot[identity]) for identity in targets]))

        def preflight(current):
            current_targets = eligible_targets(operation, current.hypotheses, targets)
            current_snapshot = {identity: parent_snapshot(current.hypotheses[identity])
                                for identity in current_targets}
            if current.inquiry_id != state.inquiry_id or current_snapshot != snapshot:
                raise ValueError('Operation target changed; reload its saved state.')
            if any(p['operation'] == operation and tuple(p['target_ids']) == targets
                   and p['status'] == 'pending' for p in current.operation_proposals.values()):
                raise ValueError('Resolve the saved pending proposal first.')

        proposal_id = 'OP-' + uuid4().hex
        def success(current, actual_request, output):
            preflight(current)
            validated = validate_operation(operation, output)
            if operation == 'deepen':
                node = current.hypotheses[targets[0]]
                for field in ('assumptions', 'falsified_if'):
                    existing = {' '.join(item.split()).casefold() for item in getattr(node, field)}
                    incoming = {' '.join(item.split()).casefold() for item in validated[field]}
                    if existing & incoming:
                        raise ValueError('Deepen repeats an existing item.')
            return [dict(kind='OperationProposed', proposal_id=proposal_id,
                         run_id=actual_request.run_id, operation=operation,
                         target_ids=list(targets), target_snapshot=snapshot, output=validated)]

        run = Runner(self.root).execute(request, adapter, cancelled=cancelled,
                                        preflight=preflight, success_changes=success)
        if run.status != 'succeeded':
            raise ValueError(f'Operation run {run.id} {run.status}: {run.reason}. '
                             'Inspect saved state before another explicit generation.')
        return self.view(proposal_id)

    def accept(self, proposal_id):
        def build(state, at):
            proposal = self._view(state, proposal_id)
            if proposal['status'] == 'accepted':
                return [], proposal['result_id']
            if proposal['status'] != 'pending':
                raise ValueError('Only pending proposals may be accepted.')
            if proposal['stale']:
                raise ValueError('Operation target changed; reject this stale proposal and generate again.')
            output = proposal['output']
            target = proposal['target_ids'][0]
            if proposal['operation'] == 'deepen':
                return [dict(kind='OperationAccepted', proposal_id=proposal_id, result_id=target),
                        dict(kind='HypothesisRefined', proposal_id=proposal_id, hypothesis_id=target,
                             assumptions=output['assumptions'], falsified_if=output['falsified_if'],
                             reason=output['reason'])], target
            if proposal['operation'] == 'challenge':
                note_id = _next_id('N', state.review_notes)
                return [dict(kind='OperationAccepted', proposal_id=proposal_id, result_id=note_id),
                        dict(kind='ReviewNoteCreated', note_id=note_id,
                             proposal_id=proposal_id, hypothesis_id=target,
                             objections=output['objections'])], note_id
            if proposal['operation'] == 'synthesize':
                result_id = _next_id('SYN', state.hypotheses)
                targets = tuple(proposal['target_ids'])
                changes = [dict(kind='OperationAccepted', proposal_id=proposal_id, result_id=result_id),
                           _hypothesis(result_id, output['title'], output['claim'], targets,
                                       output['assumptions'], output['falsified_if'])]
                changes.extend(_transition(state, target, 'synthesize', at, output['reason'],
                                           synthesis_target=result_id) for target in targets)
                return changes, result_id
            raise ValueError('Operation is not implemented yet.')
        return self._commit(build)

    def reject(self, proposal_id, reason):
        _string(reason)
        def build(state, at):
            proposal = self._view(state, proposal_id)
            if proposal['status'] != 'pending':
                raise ValueError('Only pending proposals may be rejected.')
            return [dict(kind='OperationRejected', proposal_id=proposal_id, reason=reason)], None
        self._commit(build)
        return self.view(proposal_id)
