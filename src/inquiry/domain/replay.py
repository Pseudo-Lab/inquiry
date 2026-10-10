"""Deterministic, nonmutating replay of a complete event history."""
from dataclasses import asdict, replace

from inquiry.domain.events import EventValidationError, validate_event
from inquiry.domain.graph import validate_graph
from inquiry.domain.model import FramingSession, Inquiry, State, Hypothesis, Evidence, EvidenceLink, Run
from inquiry.domain.transitions import validate_transition
from inquiry.features.framing.state import KINDS as FRAMING_KINDS, apply_change as apply_framing, validate_batch as validate_framing_batch
from inquiry.features.branch.schema import parent_snapshot
from inquiry.features.branch.state import KINDS as BRANCH_KINDS, apply_change as apply_branch, validate_batch as validate_branch_batch
from inquiry.features.operation.state import KINDS as OPERATION_KINDS, apply_change as apply_operation, validate_batch as validate_operation_batch


class ReplayError(ValueError):
    def __init__(self, message, line):
        self.line = line
        super().__init__(f'Event {line}: {message}')


def _apply_run(change, event, runs, sessions, hypotheses):
    kind, identity = change['kind'], change['run_id']
    recovery = kind == 'RunFailed' and event['actor'] == 'system:recovery' and change['reason'] == 'process-interrupted'
    if event['actor'] != 'agent:runner' and not recovery:
        raise ValueError('Invalid run event producer.')
    if kind == 'RunStarted':
        if identity in runs or any(run.status == 'started' for run in runs.values()):
            raise ValueError('Duplicate run or an unfinished run needs recovery.')
        if change['session_id'] is not None and change['session_id'] not in sessions:
            raise ValueError('Run references a missing framing session.')
        if any(target not in hypotheses for target in change['target_ids']):
            raise ValueError('Run references a missing hypothesis.')
        snapshot = None
        if change['operation'] == 'hypothesis.fork':
            snapshot = parent_snapshot(hypotheses[change['target_ids'][0]])
        elif change['operation'] in ('hypothesis.deepen', 'hypothesis.challenge', 'hypothesis.synthesize'):
            snapshot = {target: parent_snapshot(hypotheses[target]) for target in sorted(change['target_ids'])}
        runs[identity] = Run(identity, change['operation'], change['model'], tuple(change['target_ids']),
                             change['session_id'], change['max_output_tokens'], change['timeout'],
                             target_snapshot=snapshot)
        return
    run = runs.get(identity)
    if run is None:
        raise ValueError('Run does not exist.')
    if kind != 'RunUsageReported' and run.status != 'started':
        raise ValueError('Run already has a terminal outcome.')
    if kind == 'RunDispatched':
        if run.dispatched:
            raise ValueError('Run was already dispatched.')
        runs[identity] = replace(run, dispatched=True)
        return
    provider = change.get('provider_request_id')
    if provider is not None and run.provider_request_id not in (None, provider):
        raise ValueError('Provider request identity mismatch.')
    if not run.dispatched and provider is not None:
        raise ValueError('Undispatched run cannot have a provider request ID.')
    updates = {'provider_request_id': provider or run.provider_request_id}
    if kind in ('RunProgress', 'RunHeartbeat', 'RunUsageReported', 'RunSucceeded') and not run.dispatched:
        raise ValueError('Provider event requires a dispatched run.')
    if 'usage' in change:
        incoming = change['usage']
        if run.usage['status'] in ('known', 'not-started') and incoming != run.usage:
            raise ValueError('Final usage cannot be changed or downgraded.')
        if incoming['status'] == 'not-started':
            if run.dispatched or provider is not None or change.get('provider_outcome') != 'not-started':
                raise ValueError('not-started usage requires cancellation before dispatch.')
        elif incoming['status'] == 'known' and not run.dispatched:
            raise ValueError('Known provider usage requires dispatch.')
        if change.get('provider_outcome') == 'not-started' and incoming['status'] != 'not-started':
            raise ValueError('Inconsistent not-started outcome.')
        updates['usage'] = incoming
    if recovery and change['provider_outcome'] != 'unknown':
        raise ValueError('Interrupted provider outcome must remain unknown.')
    if kind == 'RunProgress':
        updates['progress'] = run.progress + (change['text'],)
    elif kind == 'RunHeartbeat':
        updates['last_heartbeat_at'] = event['at']
    elif kind == 'RunSucceeded':
        updates.update(status='succeeded', provider_outcome='succeeded', proposal=change['proposal'])
    elif kind in ('RunFailed', 'RunCancelled'):
        updates.update(status='failed' if kind == 'RunFailed' else 'cancelled', reason=change['reason'],
                       provider_outcome=change['provider_outcome'])
    runs[identity] = replace(run, **updates)


def _apply_domain(change, event, hypotheses, evidence, links, created, merges):
    kind = change['kind']
    if kind == 'HypothesisCreated':
        identity = change['hypothesis_id']
        if identity in hypotheses:
            raise ValueError('Hypothesis already exists.')
        parents = tuple(change['parent_ids'])
        graph = {key: node.parent_ids for key, node in hypotheses.items()}
        graph[identity] = parents
        validate_graph(graph)
        if any(hypotheses[p].status in ('refuted', 'suspended', 'human-closed', 'synthesized') for p in parents):
            raise ValueError('Reactivate inactive parents before branching.')
        hypotheses[identity] = Hypothesis(identity, change['title'], change['claim'], parents,
            assumptions=tuple(change['assumptions']), falsified_if=tuple(change['falsified_if']))
        created.add(identity)
    elif kind == 'EvidenceCreated':
        identity = change['evidence_id']
        if identity in evidence or change['actor'] != event['actor']:
            raise ValueError('Duplicate evidence or mismatched collector.')
        evidence[identity] = Evidence(identity, change['type'], change['content'], change['uri'],
                                      change['retrieved_at'], change['actor'])
    elif kind == 'EvidenceLinked':
        if change['evidence_id'] not in evidence or change['hypothesis_id'] not in hypotheses:
            raise ValueError('Evidence link references missing objects.')
        if any(link.evidence_id == change['evidence_id'] and link.hypothesis_id == change['hypothesis_id'] for link in links):
            raise ValueError('Evidence is already linked to this hypothesis.')
        links.append(EvidenceLink(change['evidence_id'], change['hypothesis_id'], change['relation']))
    elif kind == 'HypothesisStateChanged':
        node = hypotheses.get(change['hypothesis_id'])
        if node is None or node.status != change['from']:
            raise ValueError('Missing hypothesis or stale state.')
        if change['actor'] != event['actor'] or change['at'] != event['at']:
            raise ValueError('Transition actor/time must match its event.')
        target = change['to']
        trigger = {'supported': 'support', 'contested': 'contest', 'suspended': 'suspend',
                   'refuted': 'refute', 'human-closed': 'close', 'synthesized': 'synthesize'}.get(target)
        if target == 'exploring':
            trigger = 'start' if node.status == 'suggested' else 'continue' if node.status == 'contested' else 'reopen'
        if change['trigger'] != trigger:
            raise ValueError('Transition trigger does not match states.')
        validate_transition(node.status, target, change['actor'], reason=change['reason'],
            evidence_snapshot=change['evidence_snapshot'], reopen_if=change['reopen_if'],
            synthesis_target=change['synthesis_target'])
        cited = change['evidence_ids']
        if any(identity not in evidence for identity in cited):
            raise ValueError('Missing cited evidence.')
        if target in ('supported', 'contested', 'refuted'):
            relation = 'supports' if target == 'supported' else 'challenges'
            linked = {link.evidence_id for link in links if link.hypothesis_id == node.id and link.relation == relation}
            if not cited or not set(cited) <= linked:
                raise ValueError('Decision requires evidence linked with the matching relation.')
        if trigger == 'reopen' and not cited:
            raise ValueError('Reopen requires evidence for the changed condition.')
        if target in ('refuted', 'human-closed'):
            linked = sorted({link.evidence_id for link in links if link.hypothesis_id == node.id})
            expected = [asdict(evidence[identity]) for identity in linked]
            if change['evidence_snapshot']['items'] != expected:
                raise ValueError('Closure snapshot must preserve all currently linked evidence.')
        elif change['evidence_snapshot'] is not None or change['reopen_if'] is not None:
            raise ValueError('Closure metadata belongs only to refuted/closed transitions.')
        if target == 'synthesized':
            merged = hypotheses.get(change['synthesis_target'])
            if merged is None or merged.id not in created or len(merged.parent_ids) < 2 or node.id not in merged.parent_ids:
                raise ValueError('Synthesis must reference a new multi-parent hypothesis in the same batch.')
            merges.setdefault(merged.id, set()).add(node.id)
        elif change['synthesis_target'] is not None:
            raise ValueError('Unexpected synthesis target.')
        hypotheses[node.id] = replace(node, status=target, reason=change['reason'],
            evidence_snapshot=change['evidence_snapshot'] if target in ('refuted', 'human-closed') else node.evidence_snapshot,
            reopen_if=change['reopen_if'] if target in ('refuted', 'human-closed') else node.reopen_if,
            synthesis_target=change['synthesis_target'] or node.synthesis_target,
            history=node.history + (change,))


def replay(events):
    inquiry_id = None
    inquiry = None
    sessions = {}
    batches = set()
    hypotheses, evidence, links, runs = {}, {}, [], {}
    branch_proposals = {}
    operation_proposals, review_notes = {}, {}
    seen = set()
    ids = []
    for line, source in enumerate(events, 1):
        try:
            event = validate_event(source)
        except EventValidationError as error:
            raise ReplayError(str(error), line) from error
        if event['seq'] != line:
            raise ReplayError('Nonconsecutive sequence.', line)
        if event['event_id'] in seen:
            raise ReplayError('Duplicate event_id.', line)
        if inquiry_id is not None and event['inquiry_id'] != inquiry_id:
            raise ReplayError('Multiple inquiry IDs in one log.', line)
        inquiry_id = event['inquiry_id']
        seen.add(event['event_id'])
        ids.append(event['event_id'])
        created, merges = set(), {}
        try:
            validate_framing_batch(event, sessions, runs, inquiry, hypotheses, batches)
            validate_branch_batch(event, branch_proposals, runs, hypotheses)
            validate_operation_batch(event, operation_proposals, review_notes, runs, hypotheses)
        except ValueError as error:
            raise ReplayError(str(error), line) from error
        for change in event['changes']:
            if change['kind'].startswith('Run'):
                try:
                    _apply_run(change, event, runs, sessions, hypotheses)
                except ValueError as error:
                    raise ReplayError(str(error), line) from error
            elif change['kind'] == 'FramingStarted':
                identity = change['session_id']
                if identity in sessions or inquiry is not None:
                    raise ReplayError('Duplicate framing session or inquiry already created.', line)
                sessions[identity] = FramingSession(identity, change['seed'])
            elif change['kind'] in FRAMING_KINDS:
                apply_framing(change, sessions, batches)
            elif change['kind'] in BRANCH_KINDS:
                apply_branch(change, branch_proposals)
            elif change['kind'] == 'HypothesisRefined':
                node = hypotheses[change['hypothesis_id']]
                hypotheses[node.id] = replace(node,
                    assumptions=node.assumptions + tuple(change['assumptions']),
                    falsified_if=node.falsified_if + tuple(change['falsified_if']))
            elif change['kind'] in OPERATION_KINDS:
                apply_operation(change, event, operation_proposals, review_notes)
            elif change['kind'] == 'InquiryCreated':
                if inquiry is not None:
                    raise ReplayError('Inquiry already created.', line)
                inquiry = Inquiry(inquiry_id, change['seed'], change['frame'])
            else:
                if inquiry is None:
                    raise ReplayError('Create an inquiry before domain objects.', line)
                try:
                    _apply_domain(change, event, hypotheses, evidence, links, created, merges)
                except ValueError as error:
                    raise ReplayError(str(error), line) from error
                if change['kind'] == 'HypothesisCreated':
                    inquiry = replace(inquiry, hypothesis_ids=inquiry.hypothesis_ids + (change['hypothesis_id'],))
        for target, parents in merges.items():
            if parents != set(hypotheses[target].parent_ids):
                raise ReplayError('All synthesis parents must change together.', line)
    return State(inquiry_id, len(ids), tuple(ids), inquiry, sessions,
                 hypotheses, evidence, tuple(links), runs, branch_proposals,
                 operation_proposals, review_notes)
