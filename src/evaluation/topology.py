"""Eixo 2 — equivalência topológica JSON (original) ↔ XML (gerado).

Prova que o pipeline determinístico json_to_dsl → dsl_to_xml preserva a lógica
de fluxo, e não só a contagem de nós.

O transpiler transforma o grafo de propósito (gateways de join sumem, cada fork
vira par split+join, convergências viram refs). Então NÃO comparamos iso
nó-a-nó. Comparamos a relação **direct-follows projetada sobre nós emitíveis**
(tasks/eventos/subprocess), pulando gateways: "qual atividade segue qual",
ignorando a representação de roteamento. É o que captura preservação de lógica.

Identidade de nó = rótulo (nome). Eventos sem nome usam `<categoria>` derivada
do tipo, idêntico nos dois lados (neutraliza os nomes-default "start"/"end" que
o emissor XML coloca em eventos anônimos).
"""

from __future__ import annotations

import json
from collections import Counter, deque

from lxml import etree

from src.data.deterministic.graph import ProcessGraph, load_llm
from src.data.deterministic.json_to_dsl import _wrapped_processes

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"

_EVENT_CAT = {
    "startEvent": "start",
    "startMessageEvent": "start",
    "endEvent": "end",
    "endMessageEvent": "end",
    "endErrorEvent": "end",
    "intermediateCatchEvent": "catch",
    "catchEvent": "catch",
    "catchMessageEvent": "catch",
    "catchTimerEvent": "catch",
    "catchSignalEvent": "catch",
    "catchErrorEvent": "catch",
    "catchEscalationEvent": "catch",
    "intermediateThrowEvent": "throw",
    "throwEvent": "throw",
    "throwMessageEvent": "throw",
    "throwSignalEvent": "throw",
}
_DEFAULT_EVENT_NAMES = {"start", "end"}  # nomes que o emissor XML usa p/ eventos anônimos


def _category(node_type: str) -> str | None:
    """Map a node type/tag to 'task' | 'event:<kind>' | 'subprocess' | None (gateway/other)."""
    if "Gateway" in node_type:
        return None
    if node_type in _EVENT_CAT:
        return f"event:{_EVENT_CAT[node_type]}"
    if node_type == "subProcess":
        return "subprocess"
    if node_type == "task" or node_type.endswith("Task"):
        return "task"
    return None


def _label(category: str, name: str) -> str:
    """Stable cross-format label. Anonymous events collapse to their category."""
    n = (name or "").strip()
    if category.startswith("event:"):
        if not n or n in _DEFAULT_EVENT_NAMES:
            return f"<{category.split(':', 1)[1]}>"
        return n
    return n or f"<{category}>"


def _direct_follows(
    nodes: dict[str, tuple[str, str]],  # id -> (category|None, label)
    succs: dict[str, list[str]],
) -> Counter:
    """Direct-follows multiset over emittable nodes, skipping routing gateways.

    For each emittable node `a`, walk forward through non-emittable nodes until
    the first emittable node(s) `b` are reached; record edge (label_a, label_b).
    """
    df: Counter = Counter()
    emittable = [nid for nid, (cat, _) in nodes.items() if cat is not None]
    for a in emittable:
        a_label = nodes[a][1]
        seen: set[str] = set()
        queue = deque(succs.get(a, []))
        while queue:
            n = queue.popleft()
            if n in seen:
                continue
            seen.add(n)
            cat = nodes.get(n, (None, ""))[0]
            if cat is not None:
                df[(a_label, nodes[n][1])] += 1
            else:
                queue.extend(succs.get(n, []))  # routing node: traverse through
    return df


def _node_multiset(nodes: dict[str, tuple[str, str]]) -> Counter:
    """Multiset of emittable node categories (gateways excluded)."""
    return Counter(cat for cat, _ in nodes.values() if cat is not None)


def _json_graph_nodes(graph: ProcessGraph) -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    for nid, node in graph.nodes.items():
        cat = _category(node.type)
        out[nid] = (cat, _label(cat, node.name) if cat else "")
    return out


def json_direct_follows(data: dict) -> tuple[Counter, Counter]:
    """Return (direct_follows, node_multiset) for the original JSON.

    Aggregates across wrapped multi-process payloads (processos/processes).
    """
    procs = _wrapped_processes(data) or [data]
    df: Counter = Counter()
    nm: Counter = Counter()
    for p in procs:
        graph = load_llm(p)
        nodes = _json_graph_nodes(graph)
        df += _direct_follows(nodes, graph.succs)
        nm += _node_multiset(nodes)
    return df, nm


def xml_direct_follows(xml_text: str) -> tuple[Counter, Counter]:
    """Return (direct_follows, node_multiset) for generated BPMN XML.

    Aggregates across all <process> elements in the document.
    """
    root = etree.fromstring(xml_text.encode("utf-8"))
    nodes: dict[str, tuple[str, str]] = {}
    succs: dict[str, list[str]] = {}
    for el in root.iter():
        if not isinstance(el.tag, str) or not el.tag.startswith(f"{{{BPMN_NS}}}"):
            continue
        local = el.tag.split("}", 1)[1]
        nid = el.get("id")
        if local == "sequenceFlow":
            src, tgt = el.get("sourceRef"), el.get("targetRef")
            if src and tgt:
                succs.setdefault(src, []).append(tgt)
            continue
        if nid is None:
            continue
        cat = _category(local)
        if cat is not None or "Gateway" in local:
            nodes[nid] = (cat, _label(cat, el.get("name", "")) if cat else "")
    return _direct_follows(nodes, succs), _node_multiset(nodes)


def _prf(reference: Counter, candidate: Counter) -> tuple[float, float, float]:
    """Precision/recall/F1 of candidate vs reference, over multisets."""
    inter = sum((reference & candidate).values())
    p = inter / sum(candidate.values()) if candidate else 1.0
    r = inter / sum(reference.values()) if reference else 1.0
    f1 = 2 * p * r / (p + r) if (p + r) else 1.0
    return p, r, f1


def compare(data: dict, xml_text: str) -> dict:
    """Compare original JSON vs generated XML topology. Higher is better."""
    df_json, nm_json = json_direct_follows(data)
    df_xml, nm_xml = xml_direct_follows(xml_text)
    p, r, f1 = _prf(df_json, df_xml)
    return {
        "nodes_match": nm_json == nm_xml,
        "node_delta": dict((nm_xml - nm_json) + (nm_json - nm_xml)),
        "df_exact": df_json == df_xml,
        "df_precision": p,
        "df_recall": r,
        "df_f1": f1,
        "df_json_size": sum(df_json.values()),
        "df_xml_size": sum(df_xml.values()),
        "df_missing": dict(df_json - df_xml),  # edges in JSON not in XML (lost logic)
        "df_extra": dict(df_xml - df_json),  # edges in XML not in JSON (invented)
    }


def compare_json_text(json_text: str, xml_text: str) -> dict:
    return compare(json.loads(json_text), xml_text)
