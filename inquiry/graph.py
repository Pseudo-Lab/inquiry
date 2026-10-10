"""Pure validation of the DAG-only hypothesis graph (ADR-D2)."""
from collections import deque
from collections.abc import Mapping, Sequence


class GraphError(ValueError):
    """The hypothesis graph violates a DAG invariant."""


def validate_graph(parents: Mapping[str, Sequence[str]]) -> None:
    """Validate node identifiers, parent edges, and acyclicity without mutation."""
    if not isinstance(parents, Mapping):
        raise GraphError('Graph must be a mapping of node IDs to parent sequences.')
    for node in parents:
        if not isinstance(node, str) or not node.strip():
            raise GraphError('Node IDs must be nonempty strings.')

    children = {node: [] for node in parents}
    remaining = {}
    for node, ancestors in parents.items():
        if not isinstance(ancestors, Sequence) or isinstance(ancestors, (str, bytes)):
            raise GraphError('Parents must be a sequence of node IDs.')
        seen = set()
        for parent in ancestors:
            if not isinstance(parent, str) or not parent.strip():
                raise GraphError('Parent IDs must be nonempty strings.')
            if parent == node:
                raise GraphError(f'Node {node!r} cannot parent itself.')
            if parent in seen:
                raise GraphError(f'Node {node!r} has duplicate parent {parent!r}.')
            if parent not in parents:
                raise GraphError(f'Node {node!r} has missing parent {parent!r}.')
            seen.add(parent)
            children[parent].append(node)
        remaining[node] = len(seen)

    ready = deque(node for node, count in remaining.items() if count == 0)
    visited = 0
    while ready:
        node = ready.popleft()
        visited += 1
        for child in children[node]:
            remaining[child] -= 1
            if remaining[child] == 0:
                ready.append(child)
    if visited != len(parents):
        raise GraphError('Hypothesis graph contains a cycle.')
