"""MCP server exposing inquiry ingestion + monitor as tools for harness agents.

Pivot (ADR-D12): harness agents (Claude Code/Codex sessions) call these tools to push
hypotheses/evidence into the shared graph and read status, instead of inquiry calling an
LLM itself. Each session passes its agent name; writes are attributed to ``agent:<name>``.

The `mcp` package is an optional/lazy dependency (like the OpenAI SDK): the handler
functions below are plain, testable Python; only ``serve()`` needs `mcp` installed.
"""
from typing import Optional

from inquiry.features.ingest.service import IngestService
from inquiry.domain.replay import replay
from inquiry.store.store import Store
from inquiry import monitor


_MISSING_MCP = "The MCP server requires the 'mcp' package. Install it with: pip install mcp"


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
    eid = IngestService(root, agent).add_evidence(
        target, relation, evidence_type, content, retrieved_at, uri)
    return {"evidence_id": eid}


def status(root, window=3, threshold=0.5):
    events = Store(root).read_all()
    return monitor.summary(events, replay(events), window=window, threshold=threshold)


def build_server(root, agent):
    """Build the MCP server with inquiry tools registered. Requires the optional `mcp` package.

    Separated from serve() so the tool wiring is testable without blocking on the transport.
    """
    IngestService(root, agent)  # validate the agent name eagerly (fail fast, clear message)
    server = _load_server_class()("inquiry")

    @server.tool()
    def inquiry_add_hypothesis(title: str, claim: str, parents: Optional[list] = None,
                              assumptions: Optional[list] = None,
                              falsified_if: Optional[list] = None) -> dict:
        """Propose a hypothesis in the shared inquiry graph (attributed to this agent)."""
        return add_hypothesis(root, agent, title, claim, parents, assumptions, falsified_if)

    @server.tool()
    def inquiry_add_evidence(target: str, relation: str, evidence_type: str, content: str,
                            retrieved_at: str, uri: Optional[str] = None) -> dict:
        """Attach external evidence you found to a hypothesis. relation: supports|challenges."""
        return add_evidence(root, agent, target, relation, evidence_type, content, retrieved_at, uri)

    @server.tool()
    def inquiry_status(window: int = 3, threshold: float = 0.5) -> dict:
        """Read the monitor summary: hypotheses by state, agents, saturation, near-duplicates."""
        return status(root, window, threshold)

    return server


def serve(root, agent):
    """Launch the MCP server over stdio. Requires the optional `mcp` package."""
    build_server(root, agent).run()
