"""Convert BPMN process JSON (from SOTA LLM output) to BPMN-DSL text.

Core algorithm: transforms a graph-based representation (nodes + edges)
into a tree-based DSL (nested sequences with gateway blocks).

Public API:
    dsl_text = convert(json_data)
    dsl_text = convert_file("process.json", validate=True)

The converter handles: fork/join gateway matching via BFS intersection,
nested gateways, implicit merges, cycles (via #ref), and lane membership.
"""

from __future__ import annotations

import json
import warnings
from collections import deque
from pathlib import Path

from src.data.manipulation.deterministic.graph import (
    Edge,
    Lane,
    Node,
    ProcessGraph,
    classify_gateway,
    load_llm,
)

# ── Type mapping ──────────────────────────────────────────────────────────────

# node.type → DSL task keyword
_TASK_DSL = {
    "task": "task",
    "manualTask": "manual",
    "serviceTask": "service",
    "userTask": "user",
    "scriptTask": "script",
    "sendTask": "send",
    "receiveTask": "receive",
    "businessRuleTask": "rule",
}

# node.type → (DSL position, event_kind or None)
_EVENT_DSL: dict[str, tuple[str, str | None]] = {
    "startEvent": ("start", None),
    "startMessageEvent": ("start", "message"),
    "endEvent": ("end", None),
    "endMessageEvent": ("end", "message"),
    "endErrorEvent": ("end", "error"),
    "catchMessageEvent": ("catch", "message"),
    "catchTimerEvent": ("catch", "timer"),
    "catchSignalEvent": ("catch", "signal"),
    "catchErrorEvent": ("catch", "error"),
    "catchEscalationEvent": ("catch", "escalation"),
    "throwMessageEvent": ("throw", "message"),
    "throwSignalEvent": ("throw", "signal"),
}

# node.type → DSL gateway keyword
_GATEWAY_DSL = {
    "exclusiveGateway": "xor",
    "parallelGateway": "and",
    "inclusiveGateway": "or",
}


def _is_gateway(node: Node) -> bool:
    return node.type in _GATEWAY_DSL


def _is_event(node: Node) -> bool:
    return node.type in _EVENT_DSL


def _is_task(node: Node) -> bool:
    return node.type in _TASK_DSL


# ── Emit single node ─────────────────────────────────────────────────────────


def emit_node(node: Node) -> str:
    """Convert a single Node to its DSL string representation."""
    # Events
    if node.type in _EVENT_DSL:
        position, kind = _EVENT_DSL[node.type]
        if kind is not None:
            event_name = node.name if node.name else kind
            return f'{position}:{kind}("{_esc(event_name)}")'
        return position

    # Tasks
    if node.type in _TASK_DSL:
        keyword = _TASK_DSL[node.type]
        result = f'{keyword} "{_esc(node.name)}"'
        if node.doc:
            result += f' (doc="{_esc(node.doc)}")'
        return result

    # Subprocess (treated as task if flat — full subprocess needs internal flow)
    if node.type == "subProcess":
        return f'subprocess "{_esc(node.name)}" {{ task "{_esc(node.name)}" }}'

    # Fallback
    warnings.warn(f"emit_node: unhandled type {node.type!r} for {node.id!r}")
    return f'task "{_esc(node.name)}"'


def _esc(s: str) -> str:
    """Escape double quotes and backslashes for ESCAPED_STRING."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


# ── Gateway matching: find_join ───────────────────────────────────────────────


def find_join(graph: ProcessGraph, fork_id: str) -> str | None:
    """Find the join/merge point for a fork gateway using BFS intersection.

    For each outgoing branch, BFS forward collecting reachable nodes.
    The join is the closest node reachable by ALL branches (minimum of
    max-branch-distances, ensuring all branches converge there).

    Returns None if branches never converge (each ends independently).
    """
    branch_starts = graph.succs.get(fork_id, [])
    if len(branch_starts) < 2:
        return None

    reachable: list[dict[str, int]] = []  # [{node_id: distance}, ...]

    for branch_start in branch_starts:
        distances: dict[str, int] = {}
        queue: deque[tuple[str, int]] = deque([(branch_start, 0)])
        while queue:
            nid, dist = queue.popleft()
            if nid in distances:
                continue
            distances[nid] = dist
            for succ in graph.succs.get(nid, []):
                if succ != fork_id:  # don't loop back to fork
                    queue.append((succ, dist + 1))
        reachable.append(distances)

    # Intersection: nodes reachable by ALL branches
    common = set(reachable[0].keys())
    for r in reachable[1:]:
        common &= set(r.keys())

    if not common:
        return None

    # Pick closest by minimum of max-branch-distances
    best: str | None = None
    best_cost = float("inf")
    for nid in common:
        cost = max(r[nid] for r in reachable)
        if cost < best_cost:
            best_cost = cost
            best = nid

    return best


# ── Linearize: graph → DSL token list ─────────────────────────────────────────


def linearize(
    graph: ProcessGraph,
    start_id: str,
    end_boundary: str | None = None,
    visited: set[str] | None = None,
) -> list[str]:
    """Recursively linearize a graph segment into DSL parts joined by ' -> '.

    Walks from start_id, emitting nodes and gateway blocks, until hitting
    end_boundary (exclusive) or a terminal node.
    """
    if visited is None:
        visited = set()

    parts: list[str] = []
    current = start_id

    while current is not None and current != end_boundary:
        node = graph.nodes.get(current)
        if node is None:
            break

        # Cycle detection → emit ref
        if current in visited:
            parts.append(f'#"{_esc(node.name)}"')
            break
        visited.add(current)

        succs = graph.succs.get(current, [])

        # Gateway with multiple outgoing = fork
        if _is_gateway(node) and len(succs) > 1:
            gw_block = _emit_gateway_block(graph, current, visited)
            parts.append(gw_block)

            # Advance past join
            join_id = find_join(graph, current)
            if join_id is not None:
                # Mark join as visited
                visited.add(join_id)
                join_succs = graph.succs.get(join_id, [])
                if len(join_succs) == 1:
                    current = join_succs[0]
                elif len(join_succs) > 1:
                    # Combined join-fork: the join is also a fork — process it
                    current = join_id
                    visited.discard(join_id)  # let it be processed as fork
                else:
                    current = None  # join is terminal
            else:
                current = None  # no convergence, branches end independently
            continue

        # Pure merge gateway (in-degree > 1, out-degree <= 1): skip in output
        if _is_gateway(node) and classify_gateway(current, graph.succs, graph.preds) in (
            "join",
            "both",
        ):
            if len(succs) == 1:
                current = succs[0]
            else:
                current = None
            continue

        # Regular node: emit
        parts.append(emit_node(node))

        if len(succs) == 1:
            current = succs[0]
        else:
            current = None  # terminal

    return parts


def _emit_gateway_block(graph: ProcessGraph, fork_id: str, visited: set[str]) -> str:
    """Emit a gateway block (xor/and/or) with its branches."""
    node = graph.nodes[fork_id]
    gw_keyword = _GATEWAY_DSL.get(node.type, "xor")
    gw_name = f' "{_esc(node.name)}"' if node.name else ""

    join_id = find_join(graph, fork_id)
    branch_starts = graph.succs.get(fork_id, [])
    is_parallel = gw_keyword == "and"

    branch_strs: list[str] = []
    branch_visited_sets: list[set[str]] = []

    for branch_start in branch_starts:
        branch_visited = visited.copy()
        branch_parts = linearize(graph, branch_start, end_boundary=join_id, visited=branch_visited)
        branch_visited_sets.append(branch_visited)
        branch_body = " ->\n    ".join(branch_parts) if branch_parts else 'task "empty"'

        if is_parallel:
            branch_strs.append(f"    {branch_body}")
        else:
            # Get condition from edge
            edge = graph.edge_map.get((fork_id, branch_start))
            cond = _extract_condition(edge)
            branch_strs.append(f"    [{cond}] ->\n      {branch_body}")

    # Merge all branch visited sets back into parent
    for bv in branch_visited_sets:
        visited.update(bv)

    if is_parallel:
        inner = ",\n".join(branch_strs)
    else:
        inner = "\n".join(branch_strs)

    return f"{gw_keyword}{gw_name} {{\n{inner}\n  }}"


def _extract_condition(edge: Edge | None) -> str:
    """Extract condition text for a branch edge."""
    if edge is None:
        return "default"
    # Prefer explicit condition text, fall back to label
    cond = edge.condition or edge.label
    if not cond:
        return "default"
    # Sanitize: CONDITION_TEXT can't contain [ or ]
    return cond.replace("[", "(").replace("]", ")")


# ── Lane emission ─────────────────────────────────────────────────────────────


def emit_lanes(lanes: list[Lane], nodes: dict[str, Node]) -> list[str]:
    """Emit lane membership declaration lines."""
    lines = []
    for lane in lanes:
        if not lane.node_ids:
            lines.append(f'  lane "{_esc(lane.name)}" {{}}')
            continue
        members = []
        for nid in lane.node_ids:
            node = nodes.get(nid)
            if node is None:
                continue
            members.append(emit_node(node))
        if members:
            member_str = ",\n    ".join(members)
            lines.append(f'  lane "{_esc(lane.name)}" {{\n    {member_str}\n  }}')
        else:
            lines.append(f'  lane "{_esc(lane.name)}" {{}}')
    return lines


# ── Full process emission ─────────────────────────────────────────────────────


def emit_process(graph: ProcessGraph, wrapper: str = "process") -> str:
    """Emit a complete process/pool block from a ProcessGraph."""
    name = graph.name or "Unnamed Process"
    parts: list[str] = []

    # Lane declarations
    if graph.lanes:
        lane_lines = emit_lanes(graph.lanes, graph.nodes)
        parts.extend(lane_lines)
        parts.append("")  # blank line between lanes and seq

    # Sequence flow
    if graph.start_id:
        seq_parts = linearize(graph, graph.start_id)
        if seq_parts:
            seq_str = " ->\n  ".join(seq_parts)
            parts.append(f"  {seq_str}")

    body = "\n".join(parts)
    return f'{wrapper} "{_esc(name)}" {{\n{body}\n}}'


# ── Public API ────────────────────────────────────────────────────────────────


def convert(data: dict) -> str:
    """Convert a BPMN JSON dict to DSL string.

    Accepts the SOTA LLM JSON format:
      {"pool": "Name", "lanes": [...], "nodes": [...], "flows": [...]}
    """
    graph = load_llm(data)
    return emit_process(graph)


def convert_file(json_path: str | Path, validate: bool = True) -> str:
    """Load JSON file, convert to DSL, optionally validate with parser."""
    path = Path(json_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    dsl_text = convert(data)

    if validate:
        from src.dsl.parser import parse

        parse(dsl_text)  # raises UnexpectedInput on bad DSL

    return dsl_text
