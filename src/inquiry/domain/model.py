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
