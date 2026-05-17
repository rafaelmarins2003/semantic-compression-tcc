"""Transpile BPMN-DSL parse trees to BPMN 2.0 XML.

This module intentionally emits a compact BPMN XML model without DI/layout.
It is the deterministic bridge after the LLM JSON -> DSL step.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from lark import Tree
from lxml import etree

from src.dsl.parser import parse, parse_file, unquote

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"


def _q(tag: str) -> str:
    return f"{{{BPMN_NS}}}{tag}"


@dataclass
class EmittedNode:
    id: str
    tag: str
    name: str


@dataclass
class LaneDecl:
    name: str
    members: list[tuple[str, str]]


@dataclass
class ProcessEmitter:
    """Stateful BPMN process emitter."""

    process_el: etree._Element
    counters: Counter = field(default_factory=Counter)
    emitted_nodes: list[EmittedNode] = field(default_factory=list)

    def new_id(self, prefix: str) -> str:
        self.counters[prefix] += 1
        return f"{prefix}_{self.counters[prefix]}"

    def add_node(self, tag: str, name: str = "") -> str:
        prefix = tag[0].upper() + tag[1:]
        node_id = self.new_id(prefix)
        attrs = {"id": node_id}
        if name:
            attrs["name"] = name
        etree.SubElement(self.process_el, _q(tag), attrs)
        self.emitted_nodes.append(EmittedNode(node_id, tag, name))
        return node_id

    def add_node_element(self, tag: str, name: str = "") -> tuple[str, etree._Element]:
        prefix = tag[0].upper() + tag[1:]
        node_id = self.new_id(prefix)
        attrs = {"id": node_id}
        if name:
            attrs["name"] = name
        el = etree.SubElement(self.process_el, _q(tag), attrs)
        self.emitted_nodes.append(EmittedNode(node_id, tag, name))
        return node_id, el

    def add_flow(self, source_id: str, target_id: str, condition: str = "") -> str:
        flow_id = self.new_id("SequenceFlow")
        flow = etree.SubElement(
            self.process_el,
            _q("sequenceFlow"),
            {"id": flow_id, "sourceRef": source_id, "targetRef": target_id},
        )
        if condition and condition != "default":
            etree.SubElement(flow, _q("conditionExpression")).text = condition
        return flow_id


def transpile(text: str) -> str:
    """Parse BPMN-DSL text and return BPMN XML as a Unicode string."""
    return transpile_tree(parse(text))


def transpile_file(path: str | Path) -> str:
    """Parse a BPMN-DSL file and return BPMN XML as a Unicode string."""
    return transpile_tree(parse_file(path))


def transpile_tree(tree: Tree) -> str:
    """Convert an already parsed DSL tree to BPMN XML."""
    root = etree.Element(
        _q("definitions"),
        nsmap={None: BPMN_NS, "xsi": XSI_NS},
        id="Definitions_1",
        targetNamespace=BPMN_NS,
    )

    for child in tree.children:
        if not isinstance(child, Tree):
            continue
        if child.data == "process":
            _emit_process(root, child)
        elif child.data == "pool":
            _emit_pool(root, child)
        elif child.data == "collaboration":
            _emit_collaboration(root, child)

    return etree.tostring(root, encoding="unicode", pretty_print=True)


def _emit_collaboration(root: etree._Element, tree: Tree) -> None:
    collab_id = "Collaboration_1"
    collaboration = etree.SubElement(root, _q("collaboration"), {"id": collab_id})
    for pool_tree in _children(tree, "pool"):
        process_id = _emit_pool(root, pool_tree)
        pool_name = unquote(pool_tree.children[0])
        etree.SubElement(
            collaboration,
            _q("participant"),
            {
                "id": f"Participant_{process_id}",
                "name": pool_name,
                "processRef": process_id,
            },
        )


def _emit_pool(root: etree._Element, tree: Tree) -> str:
    return _emit_process(root, tree, tag_name="process")


def _emit_process(root: etree._Element, tree: Tree, tag_name: str = "process") -> str:
    name = unquote(tree.children[0])
    process_id = f"Process_{_safe_id(name)}"
    process_el = etree.SubElement(root, _q(tag_name), {"id": process_id, "name": name})
    emitter = ProcessEmitter(process_el)

    body = _first_tree(tree, {"seq", "laneset"})
    if body is None:
        return process_id

    lane_decls: list[LaneDecl] = []
    seq = body
    if body.data == "laneset":
        lane_decls = _parse_lanes(body)
        seq = _first_tree(body, {"seq"})

    if seq is not None:
        _emit_seq(emitter, seq, [])

    if lane_decls:
        _emit_lane_set(process_el, lane_decls, emitter.emitted_nodes)

    return process_id


def _emit_seq(
    emitter: ProcessEmitter,
    seq: Tree,
    incoming: list[str],
    incoming_condition: str = "",
) -> list[str]:
    exits = incoming
    first = True
    for step in (c for c in seq.children if isinstance(c, Tree)):
        next_exits = _emit_step(emitter, step)
        for source_id in exits:
            for target_id in next_exits.entry_ids:
                condition = incoming_condition if first else next_exits.condition
                emitter.add_flow(source_id, target_id, condition)
        exits = next_exits.exit_ids
        first = False
    return exits


@dataclass
class StepResult:
    entry_ids: list[str]
    exit_ids: list[str]
    condition: str = ""


def _emit_step(emitter: ProcessEmitter, step: Tree) -> StepResult:
    if step.data == "task":
        tag, name, doc = _parse_task(step)
        node_id, el = emitter.add_node_element(tag, name)
        if doc:
            etree.SubElement(el, _q("documentation")).text = doc
        return StepResult([node_id], [node_id])

    if step.data in {"start_event", "end_event", "catch_event", "throw_event"}:
        tag, name, definition = _parse_event(step)
        node_id, el = emitter.add_node_element(tag, name)
        if definition:
            etree.SubElement(el, _q(definition))
        return StepResult([node_id], [node_id])

    if step.data in {"xor_gw", "and_gw", "or_gw"}:
        return _emit_gateway(emitter, step)

    if step.data == "subprocess":
        node_id = emitter.add_node("subProcess", unquote(step.children[0]))
        return StepResult([node_id], [node_id])

    if step.data == "call_activity":
        node_id = emitter.add_node("callActivity", unquote(step.children[0]))
        return StepResult([node_id], [node_id])

    if step.data == "note":
        node_id = emitter.add_node("textAnnotation", unquote(step.children[0]))
        return StepResult([node_id], [node_id])

    if step.data == "ref":
        node_id = emitter.add_node("task", f"ref: {unquote(step.children[0])}")
        return StepResult([node_id], [node_id])

    node_id = emitter.add_node("task", step.data)
    return StepResult([node_id], [node_id])


def _emit_gateway(emitter: ProcessEmitter, tree: Tree) -> StepResult:
    tag = {
        "xor_gw": "exclusiveGateway",
        "and_gw": "parallelGateway",
        "or_gw": "inclusiveGateway",
    }[tree.data]
    name = _optional_name(tree)
    split_id = emitter.add_node(tag, name)
    join_id = emitter.add_node(tag, f"{name} merge" if name else "")

    branch_trees = _children(tree, "branch")
    if tree.data == "and_gw":
        branches_root = _first_tree(tree, {"and_branches"})
        branch_trees = _children(branches_root, "seq") if branches_root else []

    for branch in branch_trees:
        if tree.data == "and_gw":
            condition = ""
            branch_seq = branch
        else:
            condition = str(branch.children[0]).strip()
            branch_seq = _first_tree(branch, {"seq"})
        if branch_seq is None:
            emitter.add_flow(split_id, join_id, condition)
            continue

        exits = _emit_seq(emitter, branch_seq, [split_id], incoming_condition=condition)
        for exit_id in exits:
            emitter.add_flow(exit_id, join_id)

    return StepResult([split_id], [join_id])


def _parse_task(tree: Tree) -> tuple[str, str, str]:
    keyword = str(tree.children[0])
    name = unquote(tree.children[1])
    tag = {
        "task": "task",
        "manual": "manualTask",
        "service": "serviceTask",
        "user": "userTask",
        "script": "scriptTask",
        "send": "sendTask",
        "receive": "receiveTask",
        "rule": "businessRuleTask",
    }.get(keyword, "task")
    doc = ""
    for props in _children(tree, "props"):
        for prop in _children(props, "prop"):
            if str(prop.children[0]) in {"doc", "documentation"}:
                doc = unquote(prop.children[1])
    return tag, name, doc


def _parse_event(tree: Tree) -> tuple[str, str, str]:
    spec = _first_tree(tree, {"event_spec"})
    kind = str(spec.children[0]) if spec else ""
    name = unquote(spec.children[1]) if spec else ""

    if tree.data == "start_event":
        tag = "startEvent"
    elif tree.data == "end_event":
        tag = "endEvent"
    elif tree.data == "catch_event":
        tag = "intermediateCatchEvent"
    else:
        tag = "intermediateThrowEvent"

    definition = {
        "message": "messageEventDefinition",
        "timer": "timerEventDefinition",
        "error": "errorEventDefinition",
        "signal": "signalEventDefinition",
        "escalation": "escalationEventDefinition",
    }.get(kind, "")
    return tag, name or ("start" if tree.data == "start_event" else "end"), definition


def _parse_lanes(tree: Tree) -> list[LaneDecl]:
    lanes = []
    for lane in _children(tree, "lane"):
        name = unquote(lane.children[0])
        members = []
        lane_members = _first_tree(lane, {"lane_members"})
        if lane_members is not None:
            for member in (c for c in lane_members.children if isinstance(c, Tree)):
                members.append(_lane_signature(member))
        lanes.append(LaneDecl(name, members))
    return lanes


def _lane_signature(tree: Tree) -> tuple[str, str]:
    if tree.data == "task":
        tag, name, _ = _parse_task(tree)
        return tag, name
    if tree.data in {"start_event", "end_event", "catch_event", "throw_event"}:
        tag, name, _ = _parse_event(tree)
        return tag, name
    if tree.data == "subprocess":
        return "subProcess", unquote(tree.children[0])
    if tree.data == "call_activity":
        return "callActivity", unquote(tree.children[0])
    if tree.data == "note":
        return "textAnnotation", unquote(tree.children[0])
    return tree.data, ""


def _emit_lane_set(
    process_el: etree._Element, lane_decls: list[LaneDecl], emitted_nodes: list[EmittedNode]
) -> None:
    by_signature: dict[tuple[str, str], list[str]] = defaultdict(list)
    for node in emitted_nodes:
        by_signature[(node.tag, node.name)].append(node.id)

    lane_set = etree.Element(_q("laneSet"), {"id": "LaneSet_1"})
    for idx, lane_decl in enumerate(lane_decls, start=1):
        lane_el = etree.SubElement(
            lane_set,
            _q("lane"),
            {"id": f"Lane_{idx}", "name": lane_decl.name},
        )
        seen = set()
        for signature in lane_decl.members:
            for node_id in by_signature.get(signature, []):
                if node_id in seen:
                    continue
                etree.SubElement(lane_el, _q("flowNodeRef")).text = node_id
                seen.add(node_id)

    process_el.insert(0, lane_set)


def _optional_name(tree: Tree) -> str:
    if tree.children and not isinstance(tree.children[0], Tree):
        return unquote(tree.children[0])
    return ""


def _children(tree: Tree | None, data: str) -> list[Tree]:
    if tree is None:
        return []
    return [c for c in tree.children if isinstance(c, Tree) and c.data == data]


def _first_tree(tree: Tree, names: set[str]) -> Tree | None:
    for child in tree.children:
        if isinstance(child, Tree) and child.data in names:
            return child
    return None


def _safe_id(value: str) -> str:
    cleaned = "".join(c if c.isalnum() else "_" for c in value).strip("_")
    return cleaned or "Unnamed"
