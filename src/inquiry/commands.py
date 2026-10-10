"""Human-issued domain commands. No model calls or automatic decisions."""
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from inquiry.domain.replay import replay
from inquiry.store.store import Store


def _next_id(prefix, objects):
    number = 1
    while f'{prefix}-{number:03d}' in objects:
        number += 1
    return f'{prefix}-{number:03d}'


def _hypothesis(identity, title, claim, parents=(), assumptions=(), falsified_if=()):
    return dict(kind='HypothesisCreated', hypothesis_id=identity, title=title, claim=claim,
                parent_ids=list(parents), assumptions=list(assumptions), falsified_if=list(falsified_if))


def _transition(state, target, action, at, reason, evidence_ids=(), reopen_if=None, synthesis_target=None):
    node = state.hypotheses.get(target)
    if node is None:
        raise ValueError('Hypothesis does not exist.')
    states = {'start': 'exploring', 'continue': 'exploring', 'reopen': 'exploring',
              'support': 'supported', 'contest': 'contested', 'suspend': 'suspended',
              'refute': 'refuted', 'close': 'human-closed', 'synthesize': 'synthesized'}
    if action not in states:
        raise ValueError('Unknown decision.')
    if action == 'start' and node.status != 'suggested':
        raise ValueError('start requires a suggested hypothesis.')
    if action == 'continue' and node.status != 'contested':
        raise ValueError('continue requires a contested hypothesis.')
    if action == 'reopen' and node.status not in ('suspended', 'refuted', 'human-closed'):
        raise ValueError('reopen requires a suspended, refuted or closed hypothesis.')
    snapshot = None
    if action in ('refute', 'close'):
        linked = sorted({link.evidence_id for link in state.evidence_links if link.hypothesis_id == target})
        snapshot = {'items': [asdict(state.evidence[key]) for key in linked],
                    'note': 'Snapshot of linked evidence.' if linked else 'No evidence linked at closure.'}
    return {'kind': 'HypothesisStateChanged', 'hypothesis_id': target, 'from': node.status,
            'to': states[action], 'trigger': action, 'actor': 'human:local', 'at': at,
            'reason': reason, 'evidence_ids': list(evidence_ids), 'evidence_snapshot': snapshot,
            'reopen_if': reopen_if, 'synthesis_target': synthesis_target}


class Commands:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def state(self):
        return replay(Store(self.root).read_all())

    def _commit(self, build, allow_new=False):
        with Store(self.root) as store:
            state = replay(store.read_all())
            if not allow_new and state.inquiry is None:
                raise ValueError('Initialize an inquiry first.')
            identity = state.inquiry_id or 'I-' + uuid4().hex
            at = datetime.now(timezone.utc).isoformat()
            changes, result = build(state, at, identity)
            event = dict(schema_version=1, event_id=uuid4().hex, seq=state.last_seq + 1,
                         inquiry_id=identity, actor='human:local', at=at,
                         type='changes-committed', changes=changes)
            store.append(event, expected_seq=state.last_seq)
            return result

    def initialize(self, seed, frame):
        """Manual bootstrap for the core; not the future Framing approval workflow."""
        def build(state, at, identity):
            if state.inquiry is not None:
                raise ValueError('Inquiry already initialized.')
            return [dict(kind='InquiryCreated', seed=seed, frame=frame)], identity
        return self._commit(build, allow_new=True)

    def add_hypothesis(self, title, claim, parents=(), assumptions=(), falsified_if=()):
        def build(state, at, identity):
            node_id = _next_id('H', state.hypotheses)
            return [_hypothesis(node_id, title, claim, parents, assumptions, falsified_if)], node_id
        return self._commit(build)

    def add_action(self, target, title):
        def build(state, at, identity):
            action_id = _next_id('A', state.actions)
            return [dict(kind='ActionCreated', action_id=action_id,
                         hypothesis_id=target, title=title)], action_id
        return self._commit(build)

    def check_action(self, action_id, done=True):
        kind = 'ActionChecked' if done else 'ActionUnchecked'
        return self._commit(lambda state, at, identity:
                            ([dict(kind=kind, action_id=action_id)], action_id))

    def add_evidence(self, target, relation, evidence_type, content, retrieved_at, uri=None):
        def build(state, at, identity):
            evidence_id = _next_id('E', state.evidence)
            return [dict(kind='EvidenceCreated', evidence_id=evidence_id, type=evidence_type,
                         content=content, uri=uri, retrieved_at=retrieved_at, actor='human:local'),
                    dict(kind='EvidenceLinked', evidence_id=evidence_id,
                         hypothesis_id=target, relation=relation)], evidence_id
        return self._commit(build)

    def link_evidence(self, evidence_id, target, relation):
        return self._commit(lambda state, at, identity: ([dict(kind='EvidenceLinked',
            evidence_id=evidence_id, hypothesis_id=target, relation=relation)], evidence_id))

    def decide(self, target, action, *, reason='', evidence_id=None, reopen_if=None):
        if action == 'synthesize':
            raise ValueError('Use synthesize with all parents.')
        if action == 'start' and not reason:
            reason = 'Human started exploration.'
        def build(state, at, identity):
            cited = [] if evidence_id is None else [evidence_id]
            change = _transition(state, target, action, at, reason, cited, reopen_if)
            return [change], target
        return self._commit(build)

    def synthesize(self, parents, title, claim, reason):
        parents = tuple(parents)
        if len(parents) < 2 or len(set(parents)) != len(parents):
            raise ValueError('Synthesis requires at least two different parents.')
        def build(state, at, identity):
            result = _next_id('SYN', state.hypotheses)
            changes = [_hypothesis(result, title, claim, parents)]
            changes.extend(_transition(state, parent, 'synthesize', at, reason,
                                       synthesis_target=result) for parent in parents)
            return changes, result
        return self._commit(build)
