"""MCP server exposing inquiry ingestion + monitor as tools for harness agents.

Pivot (ADR-D12): harness agents (Claude Code/Codex sessions) call these tools to push
hypotheses/evidence into the shared graph and read status, instead of inquiry calling an
LLM itself. Each session passes its agent name; writes are attributed to ``agent:<name>``.

The `mcp` package is an optional/lazy dependency (like the OpenAI SDK): the handler
functions below are plain, testable Python; only ``serve()`` needs `mcp` installed.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from inquiry.features.ingest.service import IngestService
from inquiry.domain.events import EVIDENCE_TYPES
from inquiry.features.assessment.schema import AXES
from inquiry.domain.replay import replay
from inquiry.store.store import Store
from inquiry import monitor


_MISSING_MCP = "The MCP server requires the 'mcp' package. Install it with: pip install mcp"
_ACTIVITY_LOG = 'mcp-activity.jsonl'   # <root>/mcp-activity.jsonl — human-tailable, replay ignores it


def _summarize_args(args):
    """Shorten arg values so the log stays small and append stays ~atomic (not full content)."""
    out = {}
    for key, value in (args or {}).items():
        if isinstance(value, str) and len(value) > 120:
            out[key] = value[:117] + '…'
        else:
            out[key] = value
    return out


def append_activity(root, agent, tool, args, result):
    """Best-effort: append one JSON line recording an MCP tool call to <root>/mcp-activity.jsonl,
    then return `result` unchanged. A logging failure must never break the tool call. Note: tools
    that raise instead of returning a dict (inquiry_add_hypothesis on error) are not logged."""
    ok = not (isinstance(result, dict) and 'error' in result)
    entry = {'at': datetime.now(timezone.utc).isoformat(), 'agent': agent, 'tool': tool,
             'ok': ok, 'args': _summarize_args(args)}
    if not ok:
        entry['error'] = result.get('error')
    try:
        path = Path(root)
        path.mkdir(parents=True, exist_ok=True)
        with open(path / _ACTIVITY_LOG, 'a', encoding='utf-8') as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except OSError:
        pass   # best-effort — never fail a tool call on logging
    return result


def _load_server_class():
    """Return the MCP server class, supporting mcp >= 2 (MCPServer) and 1.x (FastMCP)."""
    try:
        from mcp.server.mcpserver import MCPServer
        return MCPServer
    except ImportError:
        pass
    try:
        from mcp.server.fastmcp import FastMCP
        return FastMCP
    except ImportError as error:
        raise ValueError(_MISSING_MCP) from error


def add_hypothesis(root, agent, title, claim, parents=None, assumptions=None, falsified_if=None):
    hid = IngestService(root, agent).add_hypothesis(
        title, claim, tuple(parents or ()), tuple(assumptions or ()), tuple(falsified_if or ()))
    return {"hypothesis_id": hid}


def add_evidence(root, agent, target, relation, evidence_type, content, retrieved_at, uri=None):
    try:
        eid = IngestService(root, agent).add_evidence(
            target, relation, evidence_type, content, retrieved_at, uri)
    except ValueError as error:
        # The MCP framework collapses a raised exception to an opaque "Error executing tool
        # inquiry_add_evidence" string (the message is dropped), so a calling agent can't see
        # *why* it failed and flails. Return the reason as structured output instead — this
        # path is always surfaced to the caller, so the agent can self-correct.
        return {
            "error": str(error),
            "allowed_evidence_types": sorted(EVIDENCE_TYPES),
            "allowed_relations": ["supports", "challenges"],
            "hint": ("evidence_type must be one of allowed_evidence_types (model opinions are "
                     "not evidence); 'external-article' and 'dataset' also require a source `uri`; "
                     "`target` must be an existing hypothesis id."),
        }
    return {"evidence_id": eid}


def assess(root, agent, target, axis, low, high, rationale, evidence_refs=None, unverified=True):
    """A2: push one D3 axis estimate (agent-estimate). Structured error on invalid input so the
    agent can self-correct (the MCP framework drops raised-exception messages)."""
    try:
        IngestService(root, agent).assess_axis(
            target, axis, low, high, rationale, tuple(evidence_refs or ()), unverified)
    except ValueError as error:
        return {
            "error": str(error),
            "allowed_axes": sorted(AXES),
            "hint": ("axis must be one of allowed_axes; low<=high in [0,1]; rationale required; "
                     "evidence_refs must already be linked to the hypothesis. Agent pushes are "
                     "always 'agent-estimate' and cannot downgrade a human/measured axis."),
        }
    return {"ok": True, "target": target, "axis": axis}


def contest(root, agent, target, reason, evidence_id):
    """A2: mark a hypothesis contested (agent-allowed edge). Structured error on invalid input."""
    try:
        IngestService(root, agent).contest(target, reason, evidence_id)
    except ValueError as error:
        return {
            "error": str(error),
            "hint": ("contest is only allowed from exploring/supported (agents cannot refute/close/"
                     "synthesize — those stay human-only), requires a nonempty reason and an "
                     "evidence_id already linked to the hypothesis with the 'challenges' relation."),
        }
    return {"ok": True, "target": target, "status": "contested"}


def report_usage(root, agent, input_tokens, output_tokens, est_cost=None, price_ref=None):
    """A4: report external harness token/cost usage (monitoring only). Structured error on invalid
    input (negative tokens, or est_cost without a price_ref)."""
    try:
        IngestService(root, agent).report_usage(input_tokens, output_tokens, est_cost, price_ref)
    except (ValueError, TypeError) as error:
        return {
            "error": str(error),
            "hint": ("input_tokens/output_tokens must be nonnegative integers; est_cost (if given) "
                     "must be a nonnegative number AND requires a price_ref label. This is "
                     "monitoring only — it does not cap or block generation."),
        }
    return {"ok": True, "input_tokens": int(input_tokens), "output_tokens": int(output_tokens)}


def _assemble_frame(central_question, purpose, criteria, scope_include, scope_exclude):
    return {
        'central_question': central_question,
        'purpose': purpose,
        'criteria': list(criteria or ()),
        'scope': {'include': list(scope_include or ()), 'exclude': list(scope_exclude or ())},
    }


def propose_bootstrap(root, agent, seed, central_question, purpose='', criteria=None,
                      scope_include=None, scope_exclude=None):
    """Draft a whole bootstrap (topic + frame) in one step for a human to accept in the TUI.
    Structured error on invalid input (e.g. an inquiry already exists, or empty seed/question)."""
    frame = _assemble_frame(central_question, purpose, criteria, scope_include, scope_exclude)
    try:
        bid = IngestService(root, agent).propose_bootstrap(seed, frame)
    except ValueError as error:
        return {
            "error": str(error),
            "hint": ("seed (the human-facing topic) and central_question are required. This drafts "
                     "a proposal; a human accepts it in the TUI (`accept <BT-id>`) to create the "
                     "inquiry. You cannot create the inquiry yourself."),
        }
    return {"ok": True, "bootstrap_id": bid, "status": "proposed"}


def propose_frame(root, agent, bootstrap_id, central_question, purpose='', criteria=None,
                  scope_include=None, scope_exclude=None):
    """A5: propose a structured frame for a human-seeded topic. Structured error on invalid input
    (e.g. no such seeded topic — a human must `inquiry seed <topic>` first)."""
    frame = {
        'central_question': central_question,
        'purpose': purpose,
        'criteria': list(criteria or ()),
        'scope': {'include': list(scope_include or ()), 'exclude': list(scope_exclude or ())},
    }
    try:
        IngestService(root, agent).propose_frame(bootstrap_id, frame)
    except ValueError as error:
        return {
            "error": str(error),
            "hint": ("central_question is required. A human throws the topic first "
                     "(`inquiry seed <topic>`), then you propose a frame for that bootstrap_id; "
                     "the human accepts it to create the inquiry. You cannot create the inquiry."),
        }
    return {"ok": True, "bootstrap_id": bootstrap_id, "status": "proposed"}


def status(root, window=3, threshold=0.5):
    events = Store(root).read_all()
    state = replay(events)
    if state.inquiry is None:
        # A5 guidance: no inquiry yet — show seeded topics awaiting a frame so the agent knows
        # what to propose for (and that a human must seed first). Not the full monitor summary.
        return {
            "initialized": False,
            "bootstraps": [dict(id=b['id'], seed=b['seed'], status=b['status'],
                                has_frame=b['frame'] is not None, proposed_by=b['proposed_by'])
                           for b in state.bootstraps.values()],
            "hint": ("No inquiry yet. Draft a whole bootstrap (topic + frame) from the discussion "
                     "with inquiry_propose_bootstrap; a human then accepts it in the TUI to create "
                     "the inquiry. (Or a human seeds first with `inquiry seed <topic>` and you add "
                     "a frame via inquiry_propose_frame.) You cannot create the inquiry yourself."),
        }
    return monitor.summary(events, state, window=window, threshold=threshold)


def build_server(root, agent):
    """Build the MCP server with inquiry tools registered. Requires the optional `mcp` package.

    Separated from serve() so the tool wiring is testable without blocking on the transport.
    """
    IngestService(root, agent)  # validate the agent name eagerly (fail fast, clear message)
    server = _load_server_class()("inquiry")

    @server.tool(structured_output=True)
    def inquiry_add_hypothesis(title: str, claim: str, parents: Optional[list] = None,
                              assumptions: Optional[list] = None,
                              falsified_if: Optional[list] = None) -> dict[str, Any]:
        """Propose a hypothesis in the shared inquiry graph (attributed to this agent)."""
        return append_activity(root, agent, 'inquiry_add_hypothesis', {'title': title},
            add_hypothesis(root, agent, title, claim, parents, assumptions, falsified_if))

    # These Literals mirror EVIDENCE_TYPES / the relation whitelist so the allowed values show
    # up in the tool's input schema (agents pick from them instead of guessing "web"/"url").
    # test_mcp_and_status guards that the evidence-type Literal stays in sync with EVIDENCE_TYPES.
    @server.tool(structured_output=True)
    def inquiry_add_evidence(
            target: str,
            relation: Literal["supports", "challenges"],
            evidence_type: Literal["external-article", "measured-result",
                                   "human-interview", "human-judgment", "dataset"],
            content: str, retrieved_at: str, uri: Optional[str] = None) -> dict[str, Any]:
        """Attach external evidence you found to a hypothesis (model opinions are not evidence).

        relation: supports|challenges. 'external-article' and 'dataset' require a source `uri`.
        On a validation failure the tool returns an ``{"error", "hint", ...}`` dict (not a raise).
        """
        return append_activity(root, agent, 'inquiry_add_evidence',
            {'target': target, 'relation': relation, 'evidence_type': evidence_type},
            add_evidence(root, agent, target, relation, evidence_type, content, retrieved_at, uri))

    @server.tool(structured_output=True)
    def inquiry_assess(
            target: str,
            axis: Literal["plausibility", "evidence_strength", "novelty", "impact", "testability"],
            low: float, high: float, rationale: str,
            evidence_refs: Optional[list] = None, unverified: bool = True) -> dict[str, Any]:
        """Push your D3 estimate for ONE axis of a hypothesis (as agent-estimate).

        low/high are a [0,1] range (not a point); rationale is required. evidence_refs cite
        evidence already linked to the hypothesis. Other axes are preserved. You cannot
        downgrade an axis a human/measurement already scored. Returns {"error","hint"} on failure.
        """
        return append_activity(root, agent, 'inquiry_assess',
            {'target': target, 'axis': axis, 'low': low, 'high': high},
            assess(root, agent, target, axis, low, high, rationale, evidence_refs, unverified))

    @server.tool(structured_output=True)
    def inquiry_contest(target: str, reason: str, evidence_id: str) -> dict[str, Any]:
        """Mark a hypothesis contested (exploring/supported -> contested) with challenging evidence.

        Agents may contest but not refute/close/synthesize (those stay human-only). Requires a
        nonempty reason and an evidence_id already linked with the 'challenges' relation.
        Returns {"error","hint"} on failure.
        """
        return append_activity(root, agent, 'inquiry_contest',
            {'target': target, 'evidence_id': evidence_id},
            contest(root, agent, target, reason, evidence_id))

    @server.tool(structured_output=True)
    def inquiry_report_usage(input_tokens: int, output_tokens: int,
                             est_cost: Optional[float] = None,
                             price_ref: Optional[str] = None) -> dict[str, Any]:
        """Report your token/cost usage so the human monitor can see spend for this session.

        Monitoring only — inquiry does NOT cap or block your generation (that is the operator's
        job). est_cost is optional; if given, pass a price_ref label (e.g. the model/price id).
        Returns {"error","hint"} on invalid input.
        """
        return append_activity(root, agent, 'inquiry_report_usage',
            {'input_tokens': input_tokens, 'output_tokens': output_tokens},
            report_usage(root, agent, input_tokens, output_tokens, est_cost, price_ref))

    @server.tool(structured_output=True)
    def inquiry_propose_bootstrap(
            seed: str, central_question: str, purpose: str = "",
            criteria: Optional[list] = None,
            scope_include: Optional[list] = None, scope_exclude: Optional[list] = None) -> dict[str, Any]:
        """Draft a WHOLE bootstrap (topic + frame) from the discussion so a human can accept it in
        the TUI without typing the topic. Use this to start a brand-new inquiry: `seed` is the
        human-facing topic, `central_question` the framed question. A human accepts it (`accept
        <BT-id>`) to create the inquiry — you cannot create it yourself. Returns {"error","hint"}.
        """
        return append_activity(root, agent, 'inquiry_propose_bootstrap',
            {'seed': seed, 'central_question': central_question},
            propose_bootstrap(root, agent, seed, central_question, purpose,
                              criteria, scope_include, scope_exclude))

    @server.tool(structured_output=True)
    def inquiry_propose_frame(
            bootstrap_id: str, central_question: str, purpose: str = "",
            criteria: Optional[list] = None,
            scope_include: Optional[list] = None, scope_exclude: Optional[list] = None) -> dict[str, Any]:
        """Propose a frame for a human-seeded topic (A5 bootstrap), so a human can accept it to
        create the inquiry. The topic is always human-thrown: call inquiry_status first to find a
        seeded bootstrap_id (initialized:false → bootstraps). You cannot create the inquiry yourself.
        Returns {"error","hint"} on failure.
        """
        return append_activity(root, agent, 'inquiry_propose_frame',
            {'bootstrap_id': bootstrap_id, 'central_question': central_question},
            propose_frame(root, agent, bootstrap_id, central_question, purpose,
                          criteria, scope_include, scope_exclude))

    @server.tool(structured_output=True)
    def inquiry_status(window: int = 3, threshold: float = 0.5) -> dict[str, Any]:
        """Read the monitor summary: hypotheses by state, agents, saturation, near-duplicates.

        Before any inquiry exists this returns {"initialized": false, "bootstraps": [...]} so you
        can see human-seeded topics awaiting a frame proposal.
        """
        return append_activity(root, agent, 'inquiry_status',
            {'window': window, 'threshold': threshold}, status(root, window, threshold))

    return server


def serve(root, agent):
    """Launch the MCP server over stdio. Requires the optional `mcp` package."""
    build_server(root, agent).run()
