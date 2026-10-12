"""Agent-attributed ingestion into the shared inquiry graph (monitor/control-plane pivot).

External harness agents (Claude Code/Codex sessions, via the MCP server) push hypotheses
and evidence here; each commit is attributed to ``agent:<name>`` (the session identity),
reusing the same event-sourced core as the human CLI. The human still bootstraps the
inquiry and confirms terminal decisions — the D5 state machine enforces that agents may
only propose/explore, not close/refute/synthesize on their own.
"""
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from inquiry.commands import _hypothesis, _next_id
from inquiry.domain.replay import replay
from inquiry.store.store import Store


def agent_actor(name):
    """Validate a session name and return the ``agent:<name>`` actor."""
    if not isinstance(name, str) or not name.strip() or ':' in name:
        raise ValueError('Agent name must be a nonempty string without a colon.')
    return f'agent:{name.strip()}'


class IngestService:
    def __init__(self, root, agent):
        self.root = Path(root).resolve()
        self.actor = agent_actor(agent)

    def state(self):
        return replay(Store(self.root).read_all())

    def _commit(self, build):
        with Store(self.root) as store:
            state = replay(store.read_all())
            if state.inquiry is None:
                raise ValueError('Initialize an inquiry first (the human bootstraps it).')
            at = datetime.now(timezone.utc).isoformat()
            changes, result = build(state, at)
            store.append(dict(schema_version=1, event_id=uuid4().hex, seq=state.last_seq + 1,
                inquiry_id=state.inquiry_id, actor=self.actor, at=at,
                type='changes-committed', changes=changes), expected_seq=state.last_seq)
            return result

    def add_hypothesis(self, title, claim, parents=(), assumptions=(), falsified_if=()):
        """Propose a hypothesis attributed to this agent session."""
        def build(state, at):
            node_id = _next_id('H', state.hypotheses)
            return [_hypothesis(node_id, title, claim, parents, assumptions, falsified_if)], node_id
        return self._commit(build)

    def add_evidence(self, target, relation, evidence_type, content, retrieved_at, uri=None):
        """Attach external evidence the agent found (research-connector payoff) to a hypothesis."""
        def build(state, at):
            evidence_id = _next_id('E', state.evidence)
            return [dict(kind='EvidenceCreated', evidence_id=evidence_id, type=evidence_type,
                         content=content, uri=uri, retrieved_at=retrieved_at, actor=self.actor),
                    dict(kind='EvidenceLinked', evidence_id=evidence_id,
                         hypothesis_id=target, relation=relation)], evidence_id
        return self._commit(build)
