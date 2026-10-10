"""Line-oriented UI for explicit, human-approved hypothesis operations."""

from inquiry.ui.interactive import _Exit, _run_status
from inquiry.features.operation.schema import ACTIVE_STATES
from inquiry.features.operation.service import OperationsService


def _preview_deepen(console, node, proposal):
    output = proposal['output']
    console.line(f"\nDeepen proposal / Target: {node.id} — {node.title}")
    console.line('Current assumptions:')
    for item in node.assumptions:
        console.line('  - ' + item)
    if not node.assumptions:
        console.line('  (none)')
    console.line('Current falsified if:')
    for item in node.falsified_if:
        console.line('  - ' + item)
    if not node.falsified_if:
        console.line('  (none)')
    console.line('Add assumptions:')
    for item in output['assumptions']:
        console.line('  - ' + item)
    if not output['assumptions']:
        console.line('  (none)')
    console.line('Add falsified if:')
    for item in output['falsified_if']:
        console.line('  - ' + item)
    if not output['falsified_if']:
        console.line('  (none)')
    console.line('Reason: ' + output['reason'])


def _preview_challenge(console, node, proposal):
    console.line(f"\nChallenge proposal / Target: {node.id} — {node.title}")
    for index, objection in enumerate(proposal['output']['objections'], 1):
        console.line(f"{index}. Claim: {objection['claim']}")
        console.line('   Reason: ' + objection['reason'])
        console.line('   Check: ' + objection['check'])
    console.line('Model opinion — not independent evidence.')


def _select_proposal(console, root, operation, factory, max_output_tokens, timeout):
    service = OperationsService(root)
    state = service.state()
    pending = {p['target_ids'][0]: p for p in state.operation_proposals.values()
               if p['operation'] == operation and p['status'] == 'pending'}
    targets = [node for node in state.hypotheses.values()
               if node.status in ACTIVE_STATES or node.id in pending]
    if not targets:
        console.line('보완할 수 있는 가설이 없습니다.' if operation == 'deepen'
                     else '반론을 검토할 수 있는 가설이 없습니다.')
        return None
    console.line('Target — 검토할 가설을 선택하세요.')
    labels = [f"{node.title} [{node.status}]" +
              (' / saved proposal' if node.id in pending else '') for node in targets]
    choice = console.choose(*labels, 'Back')
    if choice > len(targets):
        return None
    node = targets[choice - 1]
    if node.id in pending:
        proposal = service.view(pending[node.id]['id'])
    else:
        message = ('AI가 기존 가설에 추가할 전제와 반증 조건을 제안합니다.'
                   if operation == 'deepen' else
                   'AI가 가설에 대한 강한 반론과 확인 방법을 제안합니다.')
        console.line(message)
        if console.choose('Generate', 'Back') == 2:
            return None
        before_runs = set(service.state().runs)
        try:
            proposal = service.propose(
                operation, [node.id], adapter_factory=factory,
                max_output_tokens=max_output_tokens or 4000, timeout=timeout)
        except ValueError as error:
            console.line('Error: ' + str(error))
            for identity, run in service.state().runs.items():
                if identity not in before_runs:
                    _run_status(console, run)
            return None
        _run_status(console, service.state().runs[proposal['run_id']])
    return service, node, proposal


def _resolve_proposal(console, service, proposal, saved_message):
    if proposal['status'] != 'pending':
        console.line('이 제안은 이미 처리됐습니다.')
        return
    try:
        if proposal['stale']:
            console.line('Stale — 대상 가설이 바뀌어 승인할 수 없습니다.')
            if console.choose('Reject', 'Save & Exit') == 2:
                raise _Exit()
            service.reject(proposal['id'], console.text('거부 이유 > '))
            console.line('Rejected')
            return
        choice = console.choose('Accept', 'Reject', 'Save & Exit')
        if choice == 3:
            raise _Exit()
        if choice == 1:
            service.accept(proposal['id'])
            console.line(saved_message)
        else:
            service.reject(proposal['id'], console.text('거부 이유 > '))
            console.line('Rejected')
    except ValueError as error:
        console.line('Error: ' + str(error))


def _run_deepen(console, root, factory, max_output_tokens, timeout):
    selected = _select_proposal(console, root, 'deepen', factory, max_output_tokens, timeout)
    if selected is None:
        return
    service, node, proposal = selected
    _preview_deepen(console, node, proposal)
    _resolve_proposal(console, service, proposal, 'Deepen saved')


def _run_challenge(console, root, factory, max_output_tokens, timeout):
    selected = _select_proposal(console, root, 'challenge', factory, max_output_tokens, timeout)
    if selected is None:
        return
    service, node, proposal = selected
    _preview_challenge(console, node, proposal)
    _resolve_proposal(console, service, proposal, 'Challenge review note saved')


def _synthesis_selection(console, candidates):
    choices = {str(index): node.id for index, node in enumerate(candidates, 1)}
    while True:
        text = console.text('통합할 부모 번호 (예: 1,2) > ').strip()
        numbers = text.replace(',', ' ').split()
        if len(numbers) >= 2 and len(set(numbers)) == len(numbers) and all(number in choices for number in numbers):
            return [choices[number] for number in numbers]
        console.line('표시된 서로 다른 부모 번호를 두 개 이상 입력해 주세요.')


def _preview_synthesis(console, state, proposal):
    output = proposal['output']
    console.line('\nSynthesis proposal / Parents: ' + ', '.join(proposal['target_ids']))
    for parent_id in proposal['target_ids']:
        node = state.hypotheses[parent_id]
        console.line(f'  - {node.title} [{node.status}]')
    console.line('Title: ' + output['title'])
    console.line('Claim: ' + output['claim'])
    console.line('Reason: ' + output['reason'])
    console.line('Unresolved:')
    for item in output['unresolved']:
        console.line('  - ' + item)
    if not output['unresolved']:
        console.line('  (none)')


def _run_synthesis(console, root, factory, max_output_tokens, timeout):
    service = OperationsService(root)
    state = service.state()
    pending = [service.view(proposal['id']) for proposal in state.operation_proposals.values()
               if proposal['operation'] == 'synthesize' and proposal['status'] == 'pending']
    eligible = [node for node in state.hypotheses.values()
                if node.status in ('supported', 'contested')]
    labels = [f"Saved synthesis: {', '.join(proposal['target_ids'])}" for proposal in pending]
    if len(eligible) >= 2:
        labels.append('New synthesis')
    labels.append('Back')
    choice = console.choose(*labels)
    if choice == len(labels):
        return
    if choice <= len(pending):
        proposal = pending[choice - 1]
    else:
        console.line('Parents — supported 또는 contested 가설을 두 개 이상 선택하세요.')
        for index, node in enumerate(eligible, 1):
            console.line(f'{index}. {node.title} [{node.status}]')
        targets = _synthesis_selection(console, eligible)
        console.line('AI가 새 통합 가설과 아직 해결되지 않은 차이를 제안합니다.')
        if console.choose('Generate', 'Back') == 2:
            return
        before_runs = set(service.state().runs)
        try:
            proposal = service.propose('synthesize', targets, adapter_factory=factory,
                                       max_output_tokens=max_output_tokens or 4000, timeout=timeout)
        except ValueError as error:
            console.line('Error: ' + str(error))
            for identity, run in service.state().runs.items():
                if identity not in before_runs:
                    _run_status(console, run)
            return
        _run_status(console, service.state().runs[proposal['run_id']])
    _preview_synthesis(console, service.state(), proposal)
    _resolve_proposal(console, service, proposal, 'Synthesis saved')


def _run_review_notes(console, root):
    service = OperationsService(root)
    state = service.state()
    targets = list(state.hypotheses.values())
    if not targets:
        console.line('가설이 없습니다.')
        return
    choice = console.choose(*[f'{node.title} [{node.status}]' for node in targets], 'Back')
    if choice > len(targets):
        return
    notes = service.notes(targets[choice - 1].id)
    console.line('Review Notes — model opinions, not independent evidence.')
    if not notes:
        console.line('(none)')
        return
    row = 1
    for note in notes:
        for objection in note['objections']:
            console.line(f"{row}. {note['id']} | Claim: {objection['claim']} | Reason: {objection['reason']} | Check: {objection['check']}")
            row += 1


def run_check(console, root, factories, max_output_tokens, timeout):
    """Run one Check action and return to the caller's root menu."""
    state = OperationsService(root).state()
    has_synthesis = (sum(node.status in ('supported', 'contested') for node in state.hypotheses.values()) >= 2
                     or any(proposal['operation'] == 'synthesize' and proposal['status'] == 'pending'
                            for proposal in state.operation_proposals.values()))
    labels = ['Deepen', 'Challenge', 'Review Notes']
    if has_synthesis:
        labels.append('Synthesize')
    labels.append('Back')
    choice = console.choose(*labels)
    if choice == len(labels):
        return
    if choice == 3:
        _run_review_notes(console, root)
        return
    if has_synthesis and choice == 4:
        factory = factories.get('synthesize')
        if factory is None:
            raise ValueError('No Synthesize adapter configured.')
        _run_synthesis(console, root, factory, max_output_tokens, timeout)
        return
    operation = 'deepen' if choice == 1 else 'challenge'
    factory = factories.get(operation)
    if factory is None:
        raise ValueError(f'No {operation.capitalize()} adapter configured.')
    if operation == 'deepen':
        _run_deepen(console, root, factory, max_output_tokens, timeout)
    else:
        _run_challenge(console, root, factory, max_output_tokens, timeout)
