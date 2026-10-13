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
from inquiry.features.assessment.schema import validate_axis, SOURCE_RANK
from inquiry.store.store import Store, retry_on_contention


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

    def _commit(self, build, allow_new=False):
        # Agents push concurrently into the shared graph; retry transient contention
        # so a simultaneous write from another session does not drop this one (ADR-D12).
        def operation():
            with Store(self.root) as store:
                state = replay(store.read_all())
                if not allow_new and state.inquiry is None:
                    raise ValueError('No inquiry yet — a human seeds a topic (inquiry seed <topic>), you propose a frame, the human accepts.')
                at = datetime.now(timezone.utc).isoformat()
                changes, result = build(state, at)
                store.append(dict(schema_version=1, event_id=uuid4().hex, seq=state.last_seq + 1,
                    inquiry_id=state.inquiry_id or 'I-' + uuid4().hex, actor=self.actor, at=at,
                    type='changes-committed', changes=changes), expected_seq=state.last_seq)
                return result
        return retry_on_contention(operation)

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

    def assess_axis(self, target, axis, low, high, rationale, evidence_refs=(), unverified=True):
        """Push one D3 axis estimate (A2). Always agent-estimate; per-axis ConfidenceUpdated so
        other axes are preserved. The trust hierarchy (D3) is enforced here: an agent estimate
        may not overwrite an axis already scored by a human/measured source (no downgrade)."""
        payload = dict(low=low, high=high, source='agent-estimate',
                       evidence_refs=list(evidence_refs or ()), unverified=bool(unverified),
                       rationale=rationale)
        if validate_axis(payload) is None:    # form: ranges, fields, [0,1], low<=high
            raise ValueError('Assessment axis requires scored low/high and a rationale.')
        def build(state, at):
            node = state.hypotheses.get(target)
            if node is None:
                raise ValueError('Hypothesis does not exist.')
            current = getattr(node.assessment, axis, None) if node.assessment else None
            if current is not None and SOURCE_RANK.get(current.source, 0) > 0:
                raise ValueError(f'Cannot downgrade {axis} from {current.source} with an '
                                 f'agent-estimate (D3 trust hierarchy).')
            return [dict(kind='ConfidenceUpdated', hypothesis_id=target,
                         run_id='R-' + uuid4().hex, axis=axis, score=payload)], None
        return self._commit(build)

    def contest(self, target, reason, evidence_id):
        """Mark a hypothesis contested (A2). An agent-allowed edge (exploring/supported ->
        contested, _AGENT_EDGES); terminal decisions stay human-only. Requires a challenges-
        linked evidence citation (enforced by replay)."""
        def build(state, at):
            node = state.hypotheses.get(target)
            if node is None:
                raise ValueError('Hypothesis does not exist.')
            return [dict(kind='HypothesisStateChanged', hypothesis_id=target, **{'from': node.status},
                         to='contested', trigger='contest', actor=self.actor, at=at,
                         reason=reason, evidence_ids=[evidence_id], evidence_snapshot=None,
                         reopen_if=None, synthesis_target=None)], None
        return self._commit(build)

    def report_usage(self, input_tokens, output_tokens, est_cost=None, price_ref=None):
        """Report external harness token/cost usage (A4, monitoring only — not the D6 self-run
        cap). Attributed to this agent session; monitor aggregates it from the event log."""
        usage = dict(status='known', input_tokens=int(input_tokens), output_tokens=int(output_tokens),
                     est_cost=est_cost, price_ref=price_ref)
        def build(state, at):
            return [dict(kind='AgentUsageReported', usage=usage)], None
        return self._commit(build)

    def propose_frame(self, bootstrap_id, frame):
        """A5: propose a structured frame for an already-seeded topic (pre-inquiry). The human then
        accepts to create the inquiry. The agent cannot create the inquiry (accept is human-only)."""
        if not isinstance(frame, dict):
            raise ValueError('frame must be an object.')
        def build(state, at):
            if state.inquiry is not None:
                raise ValueError('Inquiry already initialized.')
            boot = state.bootstraps.get(bootstrap_id)
            if boot is None or boot['status'] not in ('seeded', 'rejected'):
                raise ValueError('Frame proposal requires a seeded topic '
                                 '(seed one with `inquiry seed <topic>` or inquiry_propose_bootstrap).')
            return [dict(kind='BootstrapFrameProposed', bootstrap_id=bootstrap_id, frame=frame)], bootstrap_id
        return self._commit(build, allow_new=True)

    def propose_bootstrap(self, seed, frame):
        """Propose a whole bootstrap (seed topic + frame) in one step, so a human can accept it in
        the TUI without typing the topic. Reduces friction while keeping the human gate: the agent
        drafts, the human still accepts to create the inquiry (accept stays human-only)."""
        if not isinstance(frame, dict):
            raise ValueError('frame must be an object.')
        if not isinstance(seed, str) or not seed.strip():
            raise ValueError('seed topic must be a nonempty string.')
        def build(state, at):
            if state.inquiry is not None:
                raise ValueError('Inquiry already initialized.')
            bid = 'BT-' + uuid4().hex
            return [dict(kind='BootstrapSeeded', bootstrap_id=bid, seed=seed),
                    dict(kind='BootstrapFrameProposed', bootstrap_id=bid, frame=frame)], bid
        return self._commit(build, allow_new=True)
