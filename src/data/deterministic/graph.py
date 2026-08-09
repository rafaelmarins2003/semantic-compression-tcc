"""Graph data structures and normalization for BPMN process JSON.

Normalizes BPMN JSON (from SOTA LLM output) into a common ProcessGraph
representation that the json_to_dsl converter can linearize.

Supported input format: SOTA LLM JSON with flat nodes/flows arrays.
"""

from __future__ import annotations

import warnings
from collections import defaultdict
from dataclasses import dataclass, field

# ── Data structures ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Node:
    id: str
    type: str  # normalized camelCase: "startEvent", "manualTask", "exclusiveGateway", ...
    name: str
    doc: str = ""
    lane: str = ""


@dataclass(frozen=True)
class Edge:
    id: str
    source: str
    target: str
    condition: str = ""
    label: str = ""


@dataclass
class Lane:
    name: str
    node_ids: list[str] = field(default_factory=list)


@dataclass
class ProcessGraph:
    """Normalized graph representation of a single BPMN process/pool."""

    name: str
    nodes: dict[str, Node]
    edges: list[Edge]
    succs: dict[str, list[str]]
    preds: dict[str, list[str]]
    edge_map: dict[tuple[str, str], Edge]
    lanes: list[Lane]
    start_id: str | None


# ── Graph construction ────────────────────────────────────────────────────────


def build_adjacency(
    nodes: dict[str, Node], edges: list[Edge]
) -> tuple[dict[str, list[str]], dict[str, list[str]], dict[tuple[str, str], Edge]]:
    """Build succs, preds, and edge_map from nodes and edges."""
    succs: dict[str, list[str]] = defaultdict(list)
    preds: dict[str, list[str]] = defaultdict(list)
    edge_map: dict[tuple[str, str], Edge] = {}

    for edge in edges:
        if edge.source not in nodes:
            warnings.warn(f"Edge {edge.id} references unknown source node {edge.source!r}")
            continue
        if edge.target not in nodes:
            warnings.warn(f"Edge {edge.id} references unknown target node {edge.target!r}")
            continue
        succs[edge.source].append(edge.target)
        preds[edge.target].append(edge.source)
        edge_map[(edge.source, edge.target)] = edge

    return dict(succs), dict(preds), edge_map


def find_start(nodes: dict[str, Node], preds: dict[str, list[str]]) -> str | None:
    """Find the start event node. Falls back to node with in-degree 0."""
    # Prefer explicit startEvent nodes
    start_candidates = [n for n in nodes.values() if n.type == "startEvent"]
    if len(start_candidates) == 1:
        return start_candidates[0].id
    if len(start_candidates) > 1:
        # Pick one with in-degree 0
        for c in start_candidates:
            if not preds.get(c.id):
                return c.id
        return start_candidates[0].id

    # No startEvent — fall back to in-degree 0 node
    for nid, node in nodes.items():
        if not preds.get(nid):
            return nid
    return None


def classify_gateway(node_id: str, succs: dict[str, list[str]], preds: dict[str, list[str]]) -> str:
    """Classify a gateway by in/out degree: 'fork', 'join', 'both', or 'none'."""
    out_degree = len(succs.get(node_id, []))
    in_degree = len(preds.get(node_id, []))
    if out_degree > 1 and in_degree > 1:
        return "both"
    if out_degree > 1:
        return "fork"
    if in_degree > 1:
        return "join"
    return "none"


def find_orphans(
    nodes: dict[str, Node], start_id: str | None, succs: dict[str, list[str]]
) -> set[str]:
    """Find node IDs not reachable from start via BFS."""
    if start_id is None:
        return set(nodes.keys())
    visited = set()
    queue = [start_id]
    while queue:
        nid = queue.pop(0)
        if nid in visited:
            continue
        visited.add(nid)
        for s in succs.get(nid, []):
            queue.append(s)
    return set(nodes.keys()) - visited


# ── LLM JSON normalization ───────────────────────────────────────────────────

# Normalize type names to standard camelCase BPMN types.
_TYPE_ALIASES = {
    # Tasks
    "Task": "task",
    "task": "task",
    "manualTask": "manualTask",
    "Manual": "manualTask",
    "serviceTask": "serviceTask",
    "Service": "serviceTask",
    "userTask": "userTask",
    "User": "userTask",
    "scriptTask": "scriptTask",
    "Script": "scriptTask",
    "sendTask": "sendTask",
    "Send": "sendTask",
    "receiveTask": "receiveTask",
    "Receive": "receiveTask",
    "businessRuleTask": "businessRuleTask",
    "BusinessRule": "businessRuleTask",
    # Events
    "startEvent": "startEvent",
    "StartEvent": "startEvent",
    "StartNoneEvent": "startEvent",
    "StartMessageEvent": "startMessageEvent",
    "endEvent": "endEvent",
    "EndEvent": "endEvent",
    "EndNoneEvent": "endEvent",
    "EndMessageEvent": "endMessageEvent",
    "EndErrorEvent": "endErrorEvent",
    "intermediateCatchEvent": "catchEvent",
    "IntermediateCatchEvent": "catchEvent",
    "intermediateThrowEvent": "throwEvent",
    "IntermediateThrowEvent": "throwEvent",
    "IntermediateMessageEventCatching": "catchMessageEvent",
    "IntermediateMessageEventThrowing": "throwMessageEvent",
    "IntermediateTimerEvent": "catchTimerEvent",
    "IntermediateSignalEventCatching": "catchSignalEvent",
    "IntermediateSignalEventThrowing": "throwSignalEvent",
    "IntermediateErrorEvent": "catchErrorEvent",
    "IntermediateEscalationEvent": "catchEscalationEvent",
    # Gateways
    "exclusiveGateway": "exclusiveGateway",
    "ExclusiveGateway": "exclusiveGateway",
    "parallelGateway": "parallelGateway",
    "ParallelGateway": "parallelGateway",
    "inclusiveGateway": "inclusiveGateway",
    "InclusiveGateway": "inclusiveGateway",
    "eventBasedGateway": "eventBasedGateway",
    "EventBasedGateway": "eventBasedGateway",
    "complexGateway": "exclusiveGateway",
    "ComplexGateway": "exclusiveGateway",
    # Subprocess
    "subProcess": "subProcess",
    "SubProcess": "subProcess",
}


def _normalize_type(raw_type: str) -> str:
    normalized = _TYPE_ALIASES.get(raw_type)
    if normalized is None:
        warnings.warn(f"Unknown node type {raw_type!r}, mapping to 'task'")
        return "task"
    return normalized


def _free_node_id(nodes: dict[str, Node], preferred: str) -> str:
    """Id livre para nó sintético. Sem isto, um nó real chamado `X_split` era
    sobrescrito em silêncio pelo gateway inserido para `X`."""
    if preferred not in nodes:
        return preferred
    suffix = 2
    while f"{preferred}_{suffix}" in nodes:
        suffix += 1
    return f"{preferred}_{suffix}"


def _normalize_implicit_splits(nodes: dict[str, Node], edges: list[Edge]) -> list[Edge]:
    """Insere um gateway sintético onde um nó comum tem mais de uma saída.

    Em BPMN, várias sequence flows saindo de uma atividade sem gateway são um
    split não controlado. A DSL só expressa bifurcação por bloco de gateway
    explícito, então sem esta normalização `json_to_dsl` emitia um sucessor e
    **descartava os demais** — perda de lógica silenciosa.

    O tipo segue a intenção observável: todas as saídas com **condição** indicam
    escolha exclusiva; caso contrário, paralelismo (a leitura padrão da BPMN).
    `label` não conta — é legenda de exibição, e um fork paralelo com ramos
    nomeados viraria XOR indevidamente.

    Como a projeção direct-follows pula gateways, isto não altera o lado JSON da
    comparação topológica — só faz o lado DSL/XML parar de perder arestas.
    """
    outgoing: dict[str, list[Edge]] = {}
    for edge in edges:
        outgoing.setdefault(edge.source, []).append(edge)

    normalized: list[Edge] = []
    handled: set[str] = set()
    for source, group in outgoing.items():
        node = nodes.get(source)
        if len(group) < 2 or node is None or "Gateway" in node.type:
            continue
        handled.add(source)
        gateway_id = _free_node_id(nodes, f"{source}_split")
        all_conditional = all(edge.condition for edge in group)
        nodes[gateway_id] = Node(
            id=gateway_id,
            type="exclusiveGateway" if all_conditional else "parallelGateway",
            name="",
            lane=node.lane,
        )
        normalized.append(Edge(id=f"f_{source}_{gateway_id}", source=source, target=gateway_id))
        for edge in group:
            normalized.append(
                Edge(
                    id=edge.id,
                    source=gateway_id,
                    target=edge.target,
                    condition=edge.condition,
                    label=edge.label,
                )
            )

    if not handled:
        return edges
    return [edge for edge in edges if edge.source not in handled] + normalized


def load_llm(data: dict) -> ProcessGraph:
    """Normalize SOTA-LLM-format JSON into a ProcessGraph.

    Expected format:
      {"pool": "Name", "lanes": [...], "nodes": [...], "flows": [...]}

    Tolerates two known LLM deviations:
      - root wrapped in {"processos": [{...}]} or {"processes": [{...}]}
        when the LLM interpreted the input as multi-process. We unwrap and
        use the first process. A warning is emitted so the runner records it.
    """
    # Unwrap multi-process containers (~0.2% of LLM outputs do this)
    for wrapper_key in ("processos", "processes"):
        wrapped = data.get(wrapper_key)
        if isinstance(wrapped, list) and wrapped and isinstance(wrapped[0], dict):
            warnings.warn(
                f"Unwrapped {wrapper_key!r} container with {len(wrapped)} process(es); "
                "using only the first."
            )
            data = wrapped[0]
            break

    process_name = data.get("pool", data.get("process", "Unnamed Process"))
    lane_names_by_id = {
        raw_lane.get("id"): raw_lane.get("name", "")
        for raw_lane in data.get("lanes", [])
        if raw_lane.get("id")
    }

    # Nodes
    nodes = {}
    for raw_node in data.get("nodes", []):
        nid = raw_node["id"]
        ntype = _normalize_type(raw_node["type"])
        name = raw_node.get("name", "")
        doc = raw_node.get("doc", "")
        raw_lane = raw_node.get("lane", "")
        lane = lane_names_by_id.get(raw_lane, raw_lane)
        nodes[nid] = Node(id=nid, type=ntype, name=name, doc=doc, lane=lane)

    # Edges
    edges = []
    for raw_flow in data.get("flows", []):
        eid = raw_flow.get("id", f"f_{raw_flow['from']}_{raw_flow['to']}")
        source = raw_flow.get("from", raw_flow.get("source", ""))
        target = raw_flow.get("to", raw_flow.get("target", ""))
        condition = raw_flow.get("cond", raw_flow.get("condition", ""))
        label = raw_flow.get("label", "")
        edges.append(Edge(id=eid, source=source, target=target, condition=condition, label=label))

    edges = _normalize_implicit_splits(nodes, edges)

    succs, preds, edge_map = build_adjacency(nodes, edges)
    start_id = find_start(nodes, preds)

    # Lanes — filter out gateways from lane refs
    lanes = []
    for raw_lane in data.get("lanes", []):
        lane_name = raw_lane.get("name", "")
        refs = raw_lane.get("refs", [])
        # Filter out gateways and unknown refs
        filtered = [r for r in refs if r in nodes and "Gateway" not in nodes[r].type]
        lanes.append(Lane(name=lane_name, node_ids=filtered))

    return ProcessGraph(
        name=process_name,
        nodes=nodes,
        edges=edges,
        succs=succs,
        preds=preds,
        edge_map=edge_map,
        lanes=lanes,
        start_id=start_id,
    )
