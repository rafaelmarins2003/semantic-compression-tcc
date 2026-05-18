"""Convert BPMN process JSON (SOTA LLM output) to BPMN-DSL v2.

v2 design — see src/dsl/dsl_documentation.txt
Key differences from v1:
  - named events emitted as `start "Name"`, `end "Name"` (was: name lost)
  - empty XOR/OR branches emit `()` (was: bogus `task "empty"` placeholder)
  - refs use stable CNAME IDs `#order_id` (was: fragile `#"Node Name"`)
  - lanes are emitted as `@lane "X" { flow }` scopes when feasible (was:
    declaration block + duplicated flow); intra-branch lane overrides use
    `(lane="Y")` prop
  - join tasks are emitted exactly once in the natural flow position
  - wrapped multi-process inputs emit one top-level `process` per component

Public API (unchanged):
    dsl_text = convert(json_data)
    dsl_text = convert_file("process.json", validate=True)
"""

from __future__ import annotations

import json
import re
import warnings
from collections import deque
from pathlib import Path

from src.data.manipulation.deterministic.graph import (
    Edge,
    Lane,
    Node,
    ProcessGraph,
    build_adjacency,
    classify_gateway,
    load_llm,
)

# ── Type → DSL keyword maps ──────────────────────────────────────────────────

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

_EVENT_DSL: dict[str, tuple[str, str | None]] = {
    "startEvent": ("start", None),
    "startMessageEvent": ("start", "message"),
    "endEvent": ("end", None),
    "endMessageEvent": ("end", "message"),
    "endErrorEvent": ("end", "error"),
    "catchEvent": ("catch", "none"),
    "catchMessageEvent": ("catch", "message"),
    "catchTimerEvent": ("catch", "timer"),
    "catchSignalEvent": ("catch", "signal"),
    "catchErrorEvent": ("catch", "error"),
    "catchEscalationEvent": ("catch", "escalation"),
    "throwEvent": ("throw", "none"),
    "throwMessageEvent": ("throw", "message"),
    "throwSignalEvent": ("throw", "signal"),
}

_GATEWAY_DSL = {
    "exclusiveGateway": "xor",
    "parallelGateway": "and",
    "inclusiveGateway": "or",
    "eventBasedGateway": "event",
}


def _is_gateway(node: Node) -> bool:
    return node.type in _GATEWAY_DSL


def _is_event(node: Node) -> bool:
    return node.type in _EVENT_DSL


def _is_task(node: Node) -> bool:
    return node.type in _TASK_DSL


# ── String escaping ──────────────────────────────────────────────────────────


def _esc(s: str) -> str:
    """Escape double quotes and backslashes for ESCAPED_STRING."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


_CNAME_RE = re.compile(r"[^a-z0-9_]")


def _slugify(s: str) -> str:
    """Coerce arbitrary string into a CNAME-compatible id (snake_case ASCII)."""
    s = (s or "").lower().strip()
    s = _CNAME_RE.sub("_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if s and s[0].isdigit():
        s = "n_" + s
    return s


# ── ID assignment ────────────────────────────────────────────────────────────


def _find_back_edge_targets(graph: ProcessGraph) -> set[str]:
    """Return node ids that are the target of at least one back-edge.

    Back-edge = DFS edge (u, v) where v is currently on the recursion stack.
    Iterative implementation to avoid Python recursion limits on big graphs.
    """
    targets: set[str] = set()
    if graph.start_id is None:
        return targets

    color: dict[str, int] = {}  # 0=white, 1=gray (on stack), 2=black
    # Stack entries: (node_id, iterator over its successors)
    stack: list[tuple[str, list[str]]] = []

    def push(nid: str) -> None:
        color[nid] = 1
        stack.append((nid, list(graph.succs.get(nid, []))))

    push(graph.start_id)
    while stack:
        nid, succs = stack[-1]
        if not succs:
            color[nid] = 2
            stack.pop()
            continue
        nxt = succs.pop()
        col = color.get(nxt, 0)
        if col == 1:
            targets.add(nxt)
        elif col == 0:
            push(nxt)
        # col == 2: already finished, skip
    return targets


def _assign_ids(graph: ProcessGraph) -> dict[str, str]:
    """Decide which nodes get a DSL id and pick collision-free CNAMEs.

    A node needs an id when it is referenced from somewhere other than its
    natural position in the flow:
      - in-degree >= 2 (convergence point), OR
      - target of a back-edge (loop), OR
      - target of an explicit ref (currently same as above two)
    Gateways also receive ids when needed. Some LLM graphs loop back to a
    decision gateway; filtering those ids would emit refs with no declaration.
    """
    needs_id: set[str] = set()
    for nid, node in graph.nodes.items():
        if len(graph.preds.get(nid, [])) >= 2:
            needs_id.add(_ref_target(graph, nid))
    needs_id |= {_ref_target(graph, nid) for nid in _find_back_edge_targets(graph)}
    id_map: dict[str, str] = {}
    used: set[str] = set()
    for nid in sorted(needs_id):  # deterministic
        candidate = _slugify(nid) or "n"
        unique = candidate
        i = 2
        while unique in used:
            unique = f"{candidate}_{i}"
            i += 1
        id_map[nid] = unique
        used.add(unique)
    return id_map


# ── Lane lookup ──────────────────────────────────────────────────────────────


def _build_node_lane(graph: ProcessGraph) -> dict[str, str]:
    """Map each node id to its lane name (or omit if no lane)."""
    out: dict[str, str] = {}
    for lane in graph.lanes:
        for nid in lane.node_ids:
            if nid in graph.nodes and nid not in out:
                out[nid] = lane.name
    for nid, node in graph.nodes.items():
        if node.lane and nid not in out:
            out[nid] = node.lane
    return out


# ── Single-element emission ──────────────────────────────────────────────────


def _emit_event(node: Node, id_map: dict[str, str], lane_override: str | None) -> str:
    position, kind = _EVENT_DSL[node.type]
    parts = [position]
    if kind:
        parts.append(f":{kind}")
    if node.name:
        parts.append(f' "{_esc(node.name)}"')
    if node.id in id_map:
        parts.append(f" #{id_map[node.id]}")
    extras = _build_props(node, lane_override)
    if extras:
        parts.append(f" ({extras})")
    return "".join(parts)


def _emit_task(node: Node, id_map: dict[str, str], lane_override: str | None) -> str:
    keyword = _TASK_DSL[node.type]
    name = node.name or node.id
    parts = [f'{keyword} "{_esc(name)}"']
    if node.id in id_map:
        parts.append(f" #{id_map[node.id]}")
    extras = _build_props(node, lane_override)
    if extras:
        parts.append(f" ({extras})")
    return "".join(parts)


def _emit_subprocess(node: Node, id_map: dict[str, str], lane_override: str | None) -> str:
    # Flat subprocess: treat its name as the only inner element.
    # Full nested subprocess flow expansion is out of scope here.
    name = node.name or node.id
    inner = f'task "{_esc(name)}"'
    id_part = f" #{id_map[node.id]}" if node.id in id_map else ""
    return f'subprocess "{_esc(name)}"{id_part} {{ {inner} }}'


def _emit_element(node: Node, id_map: dict[str, str], lane_override: str | None) -> str:
    """Emit a single non-gateway element."""
    if _is_event(node):
        return _emit_event(node, id_map, lane_override)
    if _is_task(node):
        return _emit_task(node, id_map, lane_override)
    if node.type == "subProcess":
        return _emit_subprocess(node, id_map, lane_override)
    warnings.warn(f"_emit_element: unhandled type {node.type!r} for {node.id!r}")
    return f'task "{_esc(node.name or node.id)}"'


def _build_props(node: Node, lane_override: str | None) -> str:
    """Build the `(key="value", ...)` props clause for an element."""
    props: list[str] = []
    if node.doc:
        props.append(f'doc="{_esc(node.doc)}"')
    if lane_override:
        props.append(f'lane="{_esc(lane_override)}"')
    return ", ".join(props)


# ── Gateway join detection ───────────────────────────────────────────────────


def find_join(graph: ProcessGraph, fork_id: str) -> str | None:
    """Find the convergence node for a fork via BFS intersection of branches."""
    branch_starts = graph.succs.get(fork_id, [])
    if len(branch_starts) < 2:
        return None

    reachable: list[dict[str, int]] = []
    for branch_start in branch_starts:
        distances: dict[str, int] = {}
        queue: deque[tuple[str, int]] = deque([(branch_start, 0)])
        while queue:
            nid, dist = queue.popleft()
            if nid in distances:
                continue
            distances[nid] = dist
            for succ in graph.succs.get(nid, []):
                if succ != fork_id:
                    queue.append((succ, dist + 1))
        reachable.append(distances)

    common = set(reachable[0].keys())
    for r in reachable[1:]:
        common &= set(r.keys())
    if not common:
        return None

    best: str | None = None
    best_cost = float("inf")
    for nid in common:
        cost = max(r[nid] for r in reachable)
        if cost < best_cost:
            best_cost = cost
            best = nid
    return best


def _extract_condition(edge: Edge | None) -> str:
    """Extract a sanitised condition string for a branch edge."""
    if edge is None:
        return "default"
    cond = (edge.condition or edge.label or "").strip()
    if not cond:
        return "default"
    return cond.replace("[", "(").replace("]", ")")


def _ref_for(
    nid: str,
    graph: ProcessGraph,
    id_map: dict[str, str],
) -> str:
    """Emit a ref string for a node. Prefers stable CNAME id; falls back to slug of name.

    If neither is usable, returns a comment-style placeholder so the DSL stays
    syntactically valid (the grammar still requires a CNAME).
    """
    nid = _ref_target(graph, nid)
    cid = id_map.get(nid)
    if cid:
        return f"#{cid}"
    # No id pre-assigned — synthesize from name or id as a last resort.
    node = graph.nodes.get(nid)
    fallback = _slugify(node.name) if node and node.name else _slugify(nid)
    return f"#{fallback or 'unknown'}"


def _ref_target(graph: ProcessGraph, nid: str) -> str:
    """Return the emitted node a ref should target.

    Join-only and one-in/one-out gateways are routing artifacts in DSL v2.
    They are not emitted as standalone nodes, so refs to them must point to the
    next emitted node in sequence.
    """
    seen: set[str] = set()
    current = nid
    while current not in seen:
        seen.add(current)
        node = graph.nodes.get(current)
        succs = graph.succs.get(current, [])
        if node is None or not _is_gateway(node) or len(succs) != 1:
            return current
        current = succs[0]
    return nid


# ── Graph partitioning ───────────────────────────────────────────────────────


def _wrapped_processes(data: dict) -> list[dict] | None:
    """Return wrapped process payloads, if the LLM emitted a collection."""
    for key in ("processos", "processes"):
        wrapped = data.get(key)
        if isinstance(wrapped, list):
            return [item for item in wrapped if isinstance(item, dict)]
    return None


def _weak_components(graph: ProcessGraph) -> list[set[str]]:
    """Return weakly connected components in JSON node order."""
    seen: set[str] = set()
    components: list[set[str]] = []

    for start in graph.nodes:
        if start in seen:
            continue
        component: set[str] = set()
        queue = deque([start])
        while queue:
            nid = queue.popleft()
            if nid in seen:
                continue
            seen.add(nid)
            component.add(nid)
            for nxt in (*graph.succs.get(nid, []), *graph.preds.get(nid, [])):
                if nxt in graph.nodes and nxt not in seen:
                    queue.append(nxt)
        components.append(component)
    return components


def _component_start(graph: ProcessGraph, node_ids: set[str]) -> str | None:
    """Pick the start node for one disconnected component."""
    if not node_ids:
        return None

    ordered = [nid for nid in graph.nodes if nid in node_ids]
    start_events = [nid for nid in ordered if graph.nodes[nid].type == "startEvent"]
    for nid in start_events:
        if not [pred for pred in graph.preds.get(nid, []) if pred in node_ids]:
            return nid
    if start_events:
        return start_events[0]

    for nid in ordered:
        if not [pred for pred in graph.preds.get(nid, []) if pred in node_ids]:
            return nid
    return ordered[0]


def _subgraph(
    graph: ProcessGraph,
    node_ids: set[str],
    *,
    name: str,
) -> ProcessGraph:
    """Create a ProcessGraph limited to one weak component."""
    nodes = {nid: graph.nodes[nid] for nid in graph.nodes if nid in node_ids}
    edges = [
        edge
        for edge in graph.edges
        if edge.source in node_ids and edge.target in node_ids
    ]
    succs, preds, edge_map = build_adjacency(nodes, edges)
    lanes = [
        Lane(lane.name, [nid for nid in lane.node_ids if nid in node_ids])
        for lane in graph.lanes
        if any(nid in node_ids for nid in lane.node_ids)
    ]
    return ProcessGraph(
        name=name,
        nodes=nodes,
        edges=edges,
        succs=succs,
        preds=preds,
        edge_map=edge_map,
        lanes=lanes,
        start_id=_component_start(graph, node_ids),
    )


# ── Linearize (graph → flat list of step emissions) ──────────────────────────


def _linearize(
    graph: ProcessGraph,
    start_id: str,
    *,
    end_boundary: str | None,
    visited: set[str],
    id_map: dict[str, str],
    node_lane: dict[str, str],
    ambient_lane: str | None,
) -> list[str]:
    """Walk a graph segment, emitting one DSL step per visited node.

    `ambient_lane` is the surrounding scope's lane; when an emitted element
    belongs to a different lane, an inline `(lane="...")` prop is added.
    """
    parts: list[str] = []
    current: str | None = start_id

    while current is not None and current != end_boundary:
        node = graph.nodes.get(current)
        if node is None:
            break

        if current in visited:
            parts.append(_ref_for(current, graph, id_map))
            break
        visited.add(current)

        succs = graph.succs.get(current, [])

        # Fork gateway
        if _is_gateway(node) and len(succs) > 1:
            parts.append(_emit_gateway_block(
                graph, current, visited, id_map, node_lane, ambient_lane,
            ))
            join_id = find_join(graph, current)
            if join_id is not None:
                # If the inner fork's join equals the OUTER branch boundary,
                # do not advance past it — let the while loop's boundary
                # check terminate this segment. Without this, the inner
                # join-advance walks into the OUTER scope's territory and
                # swallows the rest of the process (see handbook usage case).
                if end_boundary is not None and join_id == end_boundary:
                    current = end_boundary
                    continue
                join_was_visited = join_id in visited
                visited.add(join_id)
                join_node = graph.nodes.get(join_id)
                join_succs = graph.succs.get(join_id, [])
                if len(join_succs) == 1:
                    if join_node and not _is_gateway(join_node):
                        parts.append(_emit_with_lane(
                            join_node, id_map, node_lane, ambient_lane,
                        ))
                    current = join_succs[0]
                elif len(join_succs) > 1:
                    if join_was_visited:
                        parts.append(_ref_for(join_id, graph, id_map))
                        current = None
                    else:
                        current = join_id
                        visited.discard(join_id)
                else:
                    if join_node and not _is_gateway(join_node):
                        parts.append(_emit_with_lane(
                            join_node, id_map, node_lane, ambient_lane,
                        ))
                    current = None
            else:
                current = None
            continue

        # Pure join gateway (out-degree <= 1): skip emission
        if _is_gateway(node) and classify_gateway(current, graph.succs, graph.preds) in (
            "join",
            "both",
        ):
            current = succs[0] if len(succs) == 1 else None
            continue

        # Degenerate gateway with one input/output: keep routing, emit no fake task.
        if _is_gateway(node):
            current = succs[0] if len(succs) == 1 else None
            continue

        parts.append(_emit_with_lane(node, id_map, node_lane, ambient_lane))
        current = succs[0] if len(succs) == 1 else None

    return parts


def _emit_with_lane(
    node: Node,
    id_map: dict[str, str],
    node_lane: dict[str, str],
    ambient_lane: str | None,
) -> str:
    """Emit element, adding `(lane="...")` prop only if it differs from ambient."""
    nlane = node_lane.get(node.id)
    override = nlane if (nlane and nlane != ambient_lane) else None
    return _emit_element(node, id_map, override)


def _emit_gateway_block(
    graph: ProcessGraph,
    fork_id: str,
    visited: set[str],
    id_map: dict[str, str],
    node_lane: dict[str, str],
    ambient_lane: str | None,
) -> str:
    node = graph.nodes[fork_id]
    keyword = _GATEWAY_DSL[node.type]
    name_part = f' "{_esc(node.name)}"' if node.name else ""
    id_part = f" #{id_map[fork_id]}" if fork_id in id_map else ""
    join_id = find_join(graph, fork_id)
    branch_starts = graph.succs.get(fork_id, [])
    is_parallel = keyword == "and"
    is_event = keyword == "event"

    branch_strs: list[str] = []
    branch_visited_sets: list[set[str]] = []
    for branch_start in branch_starts:
        branch_visited = visited.copy()
        branch_parts = _linearize(
            graph,
            branch_start,
            end_boundary=join_id,
            visited=branch_visited,
            id_map=id_map,
            node_lane=node_lane,
            ambient_lane=ambient_lane,
        )
        branch_visited_sets.append(branch_visited)

        body = " -> ".join(branch_parts) if branch_parts else "()"

        if is_parallel:
            branch_strs.append(f"    {body}")
        elif is_event:
            branch_node = graph.nodes.get(branch_start)
            spec = _branch_event_spec(branch_node)
            branch_strs.append(f"    [{spec}] -> {body}")
        else:
            edge = graph.edge_map.get((fork_id, branch_start))
            cond = _extract_condition(edge)
            branch_strs.append(f"    [{cond}] -> {body}")

    for bv in branch_visited_sets:
        visited.update(bv)

    sep = ";\n" if is_parallel else "\n"
    inner = sep.join(branch_strs)
    return f"{keyword}{name_part}{id_part} {{\n{inner}\n  }}"


def _branch_event_spec(node: Node | None) -> str:
    """Render the event_spec for an eventBasedGateway branch (catch event)."""
    if node is None or node.type not in _EVENT_DSL:
        return ":message"
    _, kind = _EVENT_DSL[node.type]
    if not kind:
        return ":message"
    name = node.name or kind
    return f':{kind}("{_esc(name)}")'


# ── Top-level emission (process / pool / collaboration) ─────────────────────


def _emit_lane_partitioned_body(
    graph: ProcessGraph,
    id_map: dict[str, str],
    node_lane: dict[str, str],
) -> str:
    """Emit body as @lane scopes when multiple lanes are present.

    Single-lane processes (or processes whose start node has no lane) emit a
    flat flow without @lane wrappers. Multi-lane processes group consecutive
    top-level steps by the lane of their head node; lane transitions close
    the previous block and open a new one prefixed with `->`.
    """
    if graph.start_id is None:
        return ""

    visited: set[str] = set()
    # For partitioning we need head-lane per emitted top-level step.
    # We re-walk top-level explicitly here so we can group by lane.
    segments: list[tuple[str | None, str]] = []  # (lane_name, emission_str)
    current: str | None = graph.start_id
    while current is not None:
        node = graph.nodes.get(current)
        if node is None:
            break
        if current in visited:
            segments.append((node_lane.get(current), _ref_for(current, graph, id_map)))
            break
        visited.add(current)
        succs = graph.succs.get(current, [])

        if _is_gateway(node) and len(succs) > 1:
            ambient = node_lane.get(current)
            block = _emit_gateway_block(
                graph, current, visited, id_map, node_lane, ambient,
            )
            segments.append((ambient, block))
            join_id = find_join(graph, current)
            if join_id is not None:
                join_was_visited = join_id in visited
                visited.add(join_id)
                join_node = graph.nodes.get(join_id)
                join_succs = graph.succs.get(join_id, [])
                if len(join_succs) == 1:
                    if join_node and not _is_gateway(join_node):
                        segments.append((
                            node_lane.get(join_id),
                            _emit_with_lane(join_node, id_map, node_lane, node_lane.get(join_id)),
                        ))
                    current = join_succs[0]
                elif len(join_succs) > 1:
                    if join_was_visited:
                        segments.append((
                            node_lane.get(join_id),
                            _ref_for(join_id, graph, id_map),
                        ))
                        current = None
                    else:
                        current = join_id
                        visited.discard(join_id)
                else:
                    if join_node and not _is_gateway(join_node):
                        segments.append((
                            node_lane.get(join_id),
                            _emit_with_lane(join_node, id_map, node_lane, node_lane.get(join_id)),
                        ))
                    current = None
            else:
                current = None
            continue

        if _is_gateway(node) and classify_gateway(current, graph.succs, graph.preds) in (
            "join",
            "both",
        ):
            current = succs[0] if len(succs) == 1 else None
            continue

        # Degenerate gateway with one input/output: keep routing, emit no fake task.
        if _is_gateway(node):
            current = succs[0] if len(succs) == 1 else None
            continue

        seg_lane = node_lane.get(current)
        # When emitting at top level inside a lane block, ambient_lane==seg_lane
        # so no override prop is added.
        emission = _emit_element(node, id_map, None)
        segments.append((seg_lane, emission))
        current = succs[0] if len(succs) == 1 else None

    # Group consecutive same-lane segments
    if not segments:
        return ""

    distinct_lanes = {lane for lane, _ in segments if lane is not None}
    if not distinct_lanes:
        # No lanes anywhere — flat flow
        return "  " + " ->\n  ".join(em for _, em in segments)

    # Inherit lane for unattributed segments (gateways are filtered out of
    # lane.refs in load_llm, so they need to fall back to the surrounding
    # element's lane). Forward-fill, then backward-fill for leading None.
    filled: list[tuple[str | None, str]] = []
    prev_lane: str | None = None
    for lane, em in segments:
        eff = lane if lane is not None else prev_lane
        filled.append((eff, em))
        if eff is not None:
            prev_lane = eff
    next_lane: str | None = None
    for i in range(len(filled) - 1, -1, -1):
        lane, em = filled[i]
        if lane is None and next_lane is not None:
            filled[i] = (next_lane, em)
        elif lane is not None:
            next_lane = lane

    groups: list[tuple[str | None, list[str]]] = []
    for lane, em in filled:
        if groups and groups[-1][0] == lane:
            groups[-1][1].append(em)
        else:
            groups.append((lane, [em]))

    lines: list[str] = []
    for idx, (lane, ems) in enumerate(groups):
        body = " ->\n    ".join(ems)
        lane_label = lane if lane is not None else "(unassigned)"
        prefix = "-> " if idx > 0 else ""
        lines.append(f'  @lane "{_esc(lane_label)}" {{\n    {prefix}{body}\n  }}')
    return "\n".join(lines)


def _emit_process(graph: ProcessGraph, wrapper: str = "process") -> str:
    id_map = _assign_ids(graph)
    node_lane = _build_node_lane(graph)
    name = graph.name or "Unnamed Process"

    has_lanes = bool(graph.lanes) and any(node_lane.values())

    if has_lanes:
        body = _emit_lane_partitioned_body(graph, id_map, node_lane)
    else:
        if graph.start_id is None:
            body = '  note "(empty process — no start event)"'
        else:
            visited: set[str] = set()
            parts = _linearize(
                graph,
                graph.start_id,
                end_boundary=None,
                visited=visited,
                id_map=id_map,
                node_lane=node_lane,
                ambient_lane=None,
            )
            body = "  " + " ->\n  ".join(parts) if parts else '  note "(empty flow)"'

    return f'{wrapper} "{_esc(name)}" {{\n{body}\n}}'


def _emit_process_collection(graph: ProcessGraph) -> str:
    """Emit all weak components without inventing sequence flows between them."""
    components = _weak_components(graph)
    if len(components) <= 1:
        return _emit_process(graph)

    blocks = []
    for idx, component in enumerate(components, start=1):
        name = graph.name if idx == 1 else f"{graph.name} - componente {idx}"
        blocks.append(_emit_process(_subgraph(graph, component, name=name)))
    return "\n\n".join(blocks)


# ── Public API ───────────────────────────────────────────────────────────────


def convert(data: dict) -> str:
    """Convert a BPMN JSON dict to DSL v2 text.

    Accepts the SOTA LLM JSON format, including wrapped multi-process payloads
    via `processos`/`processes`.
    """
    wrapped = _wrapped_processes(data)
    if wrapped is not None:
        blocks = [_emit_process_collection(load_llm(process)) for process in wrapped]
        return "\n\n".join(block for block in blocks if block)

    return _emit_process_collection(load_llm(data))


# Back-compat alias for callers that imported the old internal name.
emit_process = _emit_process


def convert_file(json_path: str | Path, validate: bool = True) -> str:
    """Load JSON, convert, optionally round-trip through the parser."""
    path = Path(json_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    dsl_text = convert(data)

    if validate:
        from src.dsl.parser import parse

        parse(dsl_text)
    return dsl_text
