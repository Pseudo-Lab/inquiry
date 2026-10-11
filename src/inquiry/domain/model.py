"""Minimal projections needed to verify durable storage and replay."""
from dataclasses import dataclass, field
from typing import Optional
from inquiry.llm.adapter import unknown_usage


@dataclass(frozen=True)
class FramingSession:
    id: str
    seed: str
    status: str = 'active'
    questions: tuple = ()
    control: Optional[dict] = None
    control_answered_qids: tuple = ()
    proposals: dict = field(default_factory=dict)
    accepted_proposal_id: Optional[str] = None


@dataclass(frozen=True)
class Inquiry:
    id: str
    seed: str
    frame: dict
    hypothesis_ids: tuple = ()
    action_ids: tuple = ()


@dataclass(frozen=True)
class AxisScore:
    """One ADR-D3 axis: a range (not a point) with its provenance.

    `low`/`high` carry inter-rung uncertainty; `source` follows the trust
    hierarchy agent-estimate < human-judgment < measured-result. `unverified`
    flags an upward move lacking fresh external evidence (principle 4, advisory).
    """
    low: float
    high: float
    source: str
    evidence_refs: tuple = ()
    unverified: bool = False
    rationale: str = ''
    updated_at: str = ''


@dataclass(frozen=True)
class Assessment:
    """The five non-additive D3 axes. Unscored axes stay None (explicit null)."""
    plausibility: Optional[AxisScore] = None
    evidence_strength: Optional[AxisScore] = None
    novelty: Optional[AxisScore] = None
    impact: Optional[AxisScore] = None
    testability: Optional[AxisScore] = None


@dataclass(frozen=True)
class Hypothesis:
    id: str
    title: str
    claim: str
    parent_ids: tuple
    status: str = 'suggested'
    assumptions: tuple = ()
    falsified_if: tuple = ()
    reason: str = ''
    evidence_snapshot: Optional[dict] = None
    reopen_if: Optional[str] = None
    synthesis_target: Optional[str] = None
    history: tuple = ()
    assessment: Optional[Assessment] = None


@dataclass(frozen=True)
class Action:
    id: str
    hypothesis_id: str
    title: str
    done: bool = False
    created_at: str = ''
    done_at: Optional[str] = None


@dataclass(frozen=True)
class Evidence:
    id: str
    type: str
    content: str
    uri: Optional[str]
    retrieved_at: str
    actor: str


@dataclass(frozen=True)
class EvidenceLink:
    evidence_id: str
    hypothesis_id: str
    relation: str


@dataclass(frozen=True)
class Run:
    id: str
    operation: str
    model: str
    target_ids: tuple
    session_id: Optional[str]
    max_output_tokens: int
    timeout: float
    status: str = 'started'
    dispatched: bool = False
    provider_request_id: Optional[str] = None
    provider_outcome: str = 'unknown'
    proposal: Optional[dict] = None
    reason: Optional[str] = None
    usage: dict = field(default_factory=unknown_usage)
    progress: tuple = ()
    last_heartbeat_at: Optional[str] = None
    target_snapshot: Optional[dict] = None


@dataclass(frozen=True)
class State:
    inquiry_id: Optional[str] = None
    last_seq: int = 0
    event_ids: tuple = ()
    inquiry: Optional[Inquiry] = None
    framing_sessions: dict = field(default_factory=dict)
    hypotheses: dict = field(default_factory=dict)
    actions: dict = field(default_factory=dict)
    evidence: dict = field(default_factory=dict)
    evidence_links: tuple = ()
    runs: dict = field(default_factory=dict)
    branch_proposals: dict = field(default_factory=dict)
    operation_proposals: dict = field(default_factory=dict)
    review_notes: dict = field(default_factory=dict)
    spend_cap: Optional[int] = None
