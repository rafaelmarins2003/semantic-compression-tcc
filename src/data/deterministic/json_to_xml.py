"""Convert BPMN process JSON directly to BPMN 2.0 XML.

This is the direct baseline for comparing:
    JSON -> XML
    JSON -> DSL -> XML
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from lxml import etree

from src.data.deterministic.graph import (
    Edge,
    Node,
    ProcessGraph,
    classify_gateway,
    load_llm,
)
from src.data.deterministic.json_to_dsl import _wrapped_processes
from src.transpiler.layout import BPMN_NS, BPMNDI_NS, DC_NS, DI_NS, XSI_NS, add_layout

NSMAP = {
    "bpmn": BPMN_NS,
    "bpmndi": BPMNDI_NS,
    "dc": DC_NS,
    "di": DI_NS,
    "xsi": XSI_NS,
}

TASK_TAGS = {
    "task": "task",
    "manualTask": "manualTask",
    "serviceTask": "serviceTask",
    "userTask": "userTask",
    "scriptTask": "scriptTask",
    "sendTask": "sendTask",
    "receiveTask": "receiveTask",
    "businessRuleTask": "businessRuleTask",
}

GATEWAY_TAGS = {
    "exclusiveGateway": "exclusiveGateway",
    "parallelGateway": "parallelGateway",
    "inclusiveGateway": "inclusiveGateway",
    "eventBasedGateway": "eventBasedGateway",
}

EVENT_TAGS = {
    "startEvent": ("startEvent", ""),
    "startMessageEvent": ("startEvent", "messageEventDefinition"),
    "endEvent": ("endEvent", ""),
    "endMessageEvent": ("endEvent", "messageEventDefinition"),
    "endErrorEvent": ("endEvent", "errorEventDefinition"),
    "catchEvent": ("intermediateCatchEvent", ""),
    "catchMessageEvent": ("intermediateCatchEvent", "messageEventDefinition"),
    "catchTimerEvent": ("intermediateCatchEvent", "timerEventDefinition"),
    "catchSignalEvent": ("intermediateCatchEvent", "signalEventDefinition"),
    "catchErrorEvent": ("intermediateCatchEvent", "errorEventDefinition"),
    "catchEscalationEvent": ("intermediateCatchEvent", "escalationEventDefinition"),
    "throwEvent": ("intermediateThrowEvent", ""),
    "throwMessageEvent": ("intermediateThrowEvent", "messageEventDefinition"),
    "throwSignalEvent": ("intermediateThrowEvent", "signalEventDefinition"),
}

_XML_ID_CHAR = re.compile(r"[^A-Za-z0-9_.-]")
_XML_ID_START = re.compile(r"^[A-Za-z_]")


class XmlIds:
    """Document-wide XML id allocator and raw-id mapper."""

    def __init__(self) -> None:
        self.used: set[str] = set()
        self.counters: Counter[str] = Counter()

    def new(self, prefix: str, preferred: str = "") -> str:
        base = _safe_xml_id(preferred or prefix)
        if not base.lower().startswith(prefix.lower()):
            base = f"{prefix}_{base}"
        candidate = base
        suffix = 2
        while candidate in self.used:
            candidate = f"{base}_{suffix}"
            suffix += 1
        self.used.add(candidate)
        return candidate

    def numbered(self, prefix: str) -> str:
        while True:
            self.counters[prefix] += 1
            candidate = f"{prefix}_{self.counters[prefix]}"
            if candidate not in self.used:
                self.used.add(candidate)
                return candidate


def convert(data: dict, *, include_layout: bool = True) -> str:
    """Convert BPMN JSON to BPMN XML.

    Accepts the same normalized LLM JSON contract used by JSON -> DSL.
    """
    root = _build_definitions(data)
    xml_text = etree.tostring(root, encoding="unicode", pretty_print=True)
    return add_layout(xml_text) if include_layout else xml_text


def convert_file(path: str | Path, *, include_layout: bool = True) -> str:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return convert(data, include_layout=include_layout)


def json_to_process_xml(data: dict) -> str:
    """Compatibility helper: return collaboration/process XML without definitions."""
    root = _build_definitions(data)
    return "\n".join(etree.tostring(child, encoding="unicode", pretty_print=True) for child in root)


def assemble_bpmn(json_logic: dict) -> str:
    """Compatibility helper used by the first manual script version."""
    return convert(json_logic, include_layout=True)


def create_bpmn_from_pipeline(
    json_logic: str | dict,
    json_layout: str | dict | None = None,  # noqa: ARG001 - kept for compatibility
) -> str:
    """Build BPMN from the logical JSON output.

    Layout is deterministic here, so any external layout JSON is intentionally ignored.
    """
    if isinstance(json_logic, str):
        json_logic = json.loads(_clean_response_block(json_logic))
    return assemble_bpmn(json_logic)


def _build_definitions(data: dict) -> etree._Element:
    ids = XmlIds()
    root = etree.Element(
        _bpmn("definitions"),
        nsmap=NSMAP,
        id=ids.numbered("Definitions"),
        targetNamespace=BPMN_NS,
    )

    process_payloads = _wrapped_processes(data) or [data]
    graphs = [load_llm(payload) for payload in process_payloads]
    process_ids = []
    for graph in graphs:
        process_ids.append(_emit_process(root, graph, ids))

    _emit_collaboration(root, graphs, process_ids, ids)
    return root


def _emit_collaboration(
    root: etree._Element,
    graphs: list[ProcessGraph],
    process_ids: list[str],
    ids: XmlIds,
) -> None:
    if not graphs:
        return
    collaboration = etree.Element(
        _bpmn("collaboration"),
        {"id": ids.numbered("Collaboration")},
    )
    for graph, process_id in zip(graphs, process_ids, strict=True):
        etree.SubElement(
            collaboration,
            _bpmn("participant"),
            {
                "id": ids.numbered("Participant"),
                "name": graph.name or "Process",
                "processRef": process_id,
            },
        )
    root.insert(0, collaboration)


def _emit_process(root: etree._Element, graph: ProcessGraph, ids: XmlIds) -> str:
    process_id = ids.new("Process", graph.name or "Process")
    process = etree.SubElement(root, _bpmn("process"), {"id": process_id, "name": graph.name})

    node_ids = {raw_id: ids.new("Node", raw_id) for raw_id in graph.nodes}
    # Chaveado pela identidade do objeto, não por `edge.id`: dois flows com o mesmo
    # id de entrada colapsavam no dict e saíam com o mesmo xs:ID, quebrando o XSD.
    flow_ids = {id(edge): ids.new("Flow", edge.id) for edge in graph.edges}

    _emit_lanes(process, graph, node_ids, ids)

    for raw_id, node in graph.nodes.items():
        _emit_node(process, node, node_ids[raw_id], graph, node_ids, flow_ids)

    for edge in graph.edges:
        _emit_flow(process, edge, node_ids, flow_ids)

    return process_id


def _emit_lanes(
    process: etree._Element,
    graph: ProcessGraph,
    node_ids: dict[str, str],
    ids: XmlIds,
) -> None:
    members = _lane_members(graph)
    if not members:
        return

    lane_set = etree.SubElement(process, _bpmn("laneSet"), {"id": ids.numbered("LaneSet")})
    for lane_name, raw_node_ids in members.items():
        lane = etree.SubElement(
            lane_set,
            _bpmn("lane"),
            {"id": ids.new("Lane", lane_name or "Lane"), "name": lane_name or "Lane"},
        )
        for raw_node_id in raw_node_ids:
            if raw_node_id in node_ids:
                etree.SubElement(lane, _bpmn("flowNodeRef")).text = node_ids[raw_node_id]


def _lane_members(graph: ProcessGraph) -> dict[str, list[str]]:
    members: dict[str, list[str]] = {}
    seen_by_lane: dict[str, set[str]] = defaultdict(set)

    for lane in graph.lanes:
        if not lane.name:
            continue
        members.setdefault(lane.name, [])
        for raw_node_id in lane.node_ids:
            if raw_node_id in graph.nodes and raw_node_id not in seen_by_lane[lane.name]:
                members[lane.name].append(raw_node_id)
                seen_by_lane[lane.name].add(raw_node_id)

    for raw_node_id, node in graph.nodes.items():
        if node.lane and raw_node_id not in seen_by_lane[node.lane]:
            members.setdefault(node.lane, []).append(raw_node_id)
            seen_by_lane[node.lane].add(raw_node_id)

    return members


def _emit_node(
    process: etree._Element,
    node: Node,
    xml_id: str,
    graph: ProcessGraph,
    node_ids: dict[str, str],
    flow_ids: dict[int, str],
) -> None:
    tag, definition = _node_tag_and_definition(node.type)
    attrs = {"id": xml_id}
    if node.name:
        attrs["name"] = node.name
    if node.type in GATEWAY_TAGS:
        attrs["gatewayDirection"] = _gateway_direction(node.id, graph)

    element = etree.SubElement(process, _bpmn(tag), attrs)
    if node.doc:
        etree.SubElement(element, _bpmn("documentation")).text = node.doc

    for pred in graph.preds.get(node.id, []):
        edge = graph.edge_map.get((pred, node.id))
        if edge is not None:
            etree.SubElement(element, _bpmn("incoming")).text = flow_ids[id(edge)]

    for succ in graph.succs.get(node.id, []):
        edge = graph.edge_map.get((node.id, succ))
        if edge is not None:
            etree.SubElement(element, _bpmn("outgoing")).text = flow_ids[id(edge)]

    if definition:
        etree.SubElement(element, _bpmn(definition), {"id": f"{xml_id}_{definition}"})


def _emit_flow(
    process: etree._Element,
    edge: Edge,
    node_ids: dict[str, str],
    flow_ids: dict[int, str],
) -> None:
    source = node_ids.get(edge.source)
    target = node_ids.get(edge.target)
    if source is None or target is None:
        return

    attrs = {"id": flow_ids[id(edge)], "sourceRef": source, "targetRef": target}
    if edge.label:
        attrs["name"] = edge.label
    flow = etree.SubElement(process, _bpmn("sequenceFlow"), attrs)
    if edge.condition:
        condition = etree.SubElement(
            flow,
            _bpmn("conditionExpression"),
            {_xsi("type"): "bpmn:tFormalExpression"},
        )
        condition.text = edge.condition


def _node_tag_and_definition(node_type: str) -> tuple[str, str]:
    if node_type in TASK_TAGS:
        return TASK_TAGS[node_type], ""
    if node_type in GATEWAY_TAGS:
        return GATEWAY_TAGS[node_type], ""
    if node_type in EVENT_TAGS:
        return EVENT_TAGS[node_type]
    if node_type == "subProcess":
        return "subProcess", ""
    return "task", ""


def _gateway_direction(node_id: str, graph: ProcessGraph) -> str:
    return {
        "fork": "Diverging",
        "join": "Converging",
        "both": "Mixed",
        "none": "Unspecified",
    }[classify_gateway(node_id, graph.succs, graph.preds)]


def _safe_xml_id(value: str) -> str:
    cleaned = _XML_ID_CHAR.sub("_", str(value or "")).strip("._-")
    cleaned = re.sub(r"_+", "_", cleaned) or "id"
    if not _XML_ID_START.match(cleaned):
        cleaned = f"id_{cleaned}"
    return cleaned


def _clean_response_block(content: str) -> str:
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```xml"):
        content = content[6:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()


def _bpmn(tag: str) -> str:
    return f"{{{BPMN_NS}}}{tag}"


def _xsi(tag: str) -> str:
    return f"{{{XSI_NS}}}{tag}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert BPMN process JSON to BPMN XML.")
    parser.add_argument("input", help="Input JSON file")
    parser.add_argument("-o", "--output", help="Output .bpmn file")
    parser.add_argument("--no-layout", action="store_true", help="Emit only logical BPMN XML")
    args = parser.parse_args(argv)

    xml_text = convert_file(args.input, include_layout=not args.no_layout)
    if args.output:
        Path(args.output).write_text(xml_text, encoding="utf-8")
    else:
        print(xml_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
