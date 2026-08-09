"""Transpile BPMN-DSL parse trees to BPMN 2.0 XML.

This module intentionally emits a compact BPMN XML model without DI/layout.
It is the deterministic bridge after the LLM JSON -> DSL step.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from lark import Tree
from lxml import etree

from src.dsl.parser import parse, parse_file, unquote

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
_CNAME_RE = re.compile(r"[^a-z0-9_]")
# XML 1.0 NameChar set (sem ':'): ids precisam ser NCName/xs:ID validos.
# str.isalnum() do Python aceita chars (ex.: U+00BA) que NAO sao NameChar,
# entao restringimos ids a este conjunto para garantir validade XSD.
_XML_NAME_CHAR = re.compile(
    "[A-Za-z0-9_.\\-"
    "\u00b7\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u02ff"
    "\u0300-\u036f\u0370-\u037d\u037f-\u1fff"
    "\u200c\u200d\u203f\u2040"
    "\u2070-\u218f\u2c00-\u2fef\u3001-\ud7ff"
    "\uf900-\ufdcf\ufdf0-\ufffd]"
)


def _q(tag: str) -> str:
    return f"{{{BPMN_NS}}}{tag}"


def _slugify(value: str) -> str:
    value = (value or "").lower().strip()
    value = _CNAME_RE.sub("_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    if value and value[0].isdigit():
        value = "n_" + value
    return value


@dataclass
class XmlContext:
    """Document-wide XML id allocator."""

    counters: Counter = field(default_factory=Counter)
    used_ids: set[str] = field(default_factory=set)

    def new_id(self, prefix: str) -> str:
        while True:
            self.counters[prefix] += 1
            candidate = f"{prefix}_{self.counters[prefix]}"
            if candidate not in self.used_ids:
                self.used_ids.add(candidate)
                return candidate

    def named_id(self, prefix: str, name: str) -> str:
        base = f"{prefix}_{_safe_id(name)}"
        candidate = base
        suffix = 2
        while candidate in self.used_ids:
            candidate = f"{base}_{suffix}"
            suffix += 1
        self.used_ids.add(candidate)
        return candidate


@dataclass
class ProcessEmitter:
    """Stateful BPMN process emitter."""

    process_el: etree._Element
    context: XmlContext
    explicit_ids: dict[str, str] = field(default_factory=dict)
    slug_ids: dict[str, str] = field(default_factory=dict)
    declared_ids: set[str] = field(default_factory=set)
    lane_members: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    current_lane: str | None = None

    def new_id(self, prefix: str) -> str:
        return self.context.new_id(prefix)

    def track_node(self, node_id: str) -> None:
        if self.current_lane:
            self.lane_members[self.current_lane].append(node_id)

    def _id_for(self, dsl_id: str, prefix: str) -> str:
        """Allocate (or reuse) the XML id for a node, keyed by its DSL id.

        A forward ref may have reserved this id already (see resolve_ref); in
        that case we reuse it so the declaration and the ref agree.
        """
        if dsl_id and dsl_id in self.explicit_ids:
            return self.explicit_ids[dsl_id]
        node_id = self.new_id(prefix)
        if dsl_id:
            self.explicit_ids[dsl_id] = node_id
        return node_id

    def register_name(self, name: str, node_id: str) -> None:
        slug = _slugify(name)
        if slug and slug not in self.slug_ids:
            self.slug_ids[slug] = node_id

    def resolve_ref(self, dsl_id: str) -> str:
        if dsl_id in self.explicit_ids:
            return self.explicit_ids[dsl_id]
        if dsl_id in self.slug_ids:
            return self.slug_ids[dsl_id]
        if dsl_id in self.declared_ids:
            # Forward ref: the target is declared later in the flow. Reserve a
            # stable id now; the declaration reuses it via _id_for. Resolution
            # is thus independent of textual order.
            node_id = self.new_id("Node")
            self.explicit_ids[dsl_id] = node_id
            return node_id
        raise ValueError(f"Unresolved DSL ref #{dsl_id}")

    def add_node(self, tag: str, name: str = "", dsl_id: str = "") -> str:
        node_id, _ = self.add_node_element(tag, name, dsl_id)
        return node_id

    def add_node_element(
        self, tag: str, name: str = "", dsl_id: str = ""
    ) -> tuple[str, etree._Element]:
        prefix = tag[0].upper() + tag[1:]
        node_id = self._id_for(dsl_id, prefix)
        attrs = {"id": node_id}
        if name:
            attrs["name"] = name
            self.register_name(name, node_id)
        el = etree.SubElement(self.process_el, _q(tag), attrs)
        self.track_node(node_id)
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
    context = XmlContext()
    root = etree.Element(
        _q("definitions"),
        nsmap={None: BPMN_NS, "xsi": XSI_NS},
        id=context.new_id("Definitions"),
        targetNamespace=BPMN_NS,
    )

    for child in tree.children:
        if not isinstance(child, Tree):
            continue
        if child.data == "process":
            _emit_process(root, child, context=context)
        elif child.data == "pool":
            _emit_pool(root, child, context=context)
        elif child.data == "collaboration":
            _emit_collaboration(root, child, context=context)

    return etree.tostring(root, encoding="unicode", pretty_print=True)


def _emit_collaboration(root: etree._Element, tree: Tree, context: XmlContext) -> None:
    collab_id = context.new_id("Collaboration")
    collaboration = etree.SubElement(root, _q("collaboration"), {"id": collab_id})
    refs: dict[str, str] = {}
    for pool_tree in _children(tree, "pool"):
        process_id = _emit_pool(root, pool_tree, context=context, global_refs=refs)
        pool_name = unquote(pool_tree.children[0])
        etree.SubElement(
            collaboration,
            _q("participant"),
            {
                "id": context.new_id("Participant"),
                "name": pool_name,
                "processRef": process_id,
            },
        )

    for idx, message_tree in enumerate(_children(tree, "message_flow"), start=1):
        name = _optional_name(message_tree)
        message_refs = _children(message_tree, "ref")
        if len(message_refs) != 2:
            continue
        source_ref = _ref_name(message_refs[0])
        target_ref = _ref_name(message_refs[1])
        attrs = {
            "id": context.new_id("MessageFlow"),
            "sourceRef": refs.get(source_ref, source_ref),
            "targetRef": refs.get(target_ref, target_ref),
        }
        if name:
            attrs["name"] = name
        etree.SubElement(collaboration, _q("messageFlow"), attrs)


def _emit_pool(
    root: etree._Element,
    tree: Tree,
    *,
    context: XmlContext,
    global_refs: dict[str, str] | None = None,
) -> str:
    return _emit_process(
        root,
        tree,
        tag_name="process",
        context=context,
        global_refs=global_refs,
    )


def _emit_process(
    root: etree._Element,
    tree: Tree,
    tag_name: str = "process",
    *,
    context: XmlContext,
    global_refs: dict[str, str] | None = None,
) -> str:
    name = unquote(tree.children[0])
    process_id = context.named_id("Process", name)
    process_el = etree.SubElement(root, _q(tag_name), {"id": process_id, "name": name})
    emitter = ProcessEmitter(process_el, context, declared_ids=_collect_declared_ids(tree))

    body = _first_tree(tree, {"flow", "laneset"})
    if body is None:
        return process_id

    if body.data == "laneset":
        exits: list[str] = []
        lane_names: list[str] = []
        for lane_block in _children(body, "lane_block"):
            lane_name = unquote(lane_block.children[0])
            lane_names.append(lane_name)
            flow = _first_tree(lane_block, {"flow"})
            if flow is None:
                continue
            emitter.current_lane = lane_name
            exits = _emit_seq(emitter, flow, exits)
            emitter.current_lane = None
        _emit_lane_set_from_members(
            process_el,
            lane_names,
            emitter.lane_members,
            context,
        )
    else:
        _emit_seq(emitter, body, [])

    if global_refs is not None:
        global_refs.update(emitter.explicit_ids)

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
        tag, name, doc, dsl_id = _parse_task(step)
        node_id, el = emitter.add_node_element(tag, name, dsl_id)
        if doc:
            etree.SubElement(el, _q("documentation")).text = doc
        return StepResult([node_id], [node_id])

    if step.data in {"start_event", "end_event", "catch_event", "throw_event"}:
        tag, name, definition, dsl_id = _parse_event(step)
        node_id, el = emitter.add_node_element(tag, name, dsl_id)
        if definition:
            etree.SubElement(el, _q(definition))
        return StepResult([node_id], [node_id])

    if step.data in {"xor_gw", "and_gw", "or_gw", "event_gw"}:
        return _emit_gateway(emitter, step)

    if step.data == "subprocess":
        node_id = emitter.add_node("subProcess", unquote(step.children[0]), _node_id_opt(step))
        return StepResult([node_id], [node_id])

    if step.data == "call_activity":
        node_id = emitter.add_node("callActivity", unquote(step.children[0]), _node_id_opt(step))
        return StepResult([node_id], [node_id])

    if step.data == "note":
        node_id = emitter.add_node("textAnnotation", unquote(step.children[0]), _node_id_opt(step))
        return StepResult([node_id], [node_id])

    if step.data == "ref":
        ref = _ref_name(step)
        target_id = emitter.resolve_ref(ref)
        return StepResult([target_id], [target_id])

    node_id = emitter.add_node("task", step.data)
    return StepResult([node_id], [node_id])


def _emit_gateway(emitter: ProcessEmitter, tree: Tree) -> StepResult:
    tag = {
        "xor_gw": "exclusiveGateway",
        "and_gw": "parallelGateway",
        "or_gw": "inclusiveGateway",
        "event_gw": "eventBasedGateway",
    }[tree.data]
    name = _optional_name(tree)
    split_id = emitter.add_node(tag, name, _node_id_opt(tree))
    join_id = emitter.add_node(tag, f"{name} merge" if name else "")

    if tree.data == "and_gw":
        branches_root = _first_tree(tree, {"and_branches"})
        # `empty_branch` precisa entrar junto com `flow`: filtrar só por "flow"
        # descartava o branch vazio de um `and`, e o fork ficava com uma única
        # saída — o paralelismo virava sequência silenciosamente.
        branch_trees = (
            [
                child
                for child in branches_root.children
                if isinstance(child, Tree) and child.data in {"flow", "empty_branch"}
            ]
            if branches_root
            else []
        )
    elif tree.data == "event_gw":
        branch_trees = _children(tree, "event_branch")
    else:
        branch_trees = _children(tree, "cond_branch")

    for branch in branch_trees:
        if tree.data == "and_gw":
            condition = ""
            branch_target = branch
        elif tree.data == "event_gw":
            condition = ""
            branch_target = _first_tree(branch, {"flow", "empty_branch"})
        else:
            condition = str(branch.children[0]).strip()
            branch_target = _first_tree(branch, {"flow", "empty_branch"})
        if branch_target is None or branch_target.data == "empty_branch":
            emitter.add_flow(split_id, join_id, condition)
            continue

        exits = _emit_seq(emitter, branch_target, [split_id], incoming_condition=condition)
        for exit_id in exits:
            emitter.add_flow(exit_id, join_id)

    return StepResult([split_id], [join_id])


def _parse_task(tree: Tree) -> tuple[str, str, str, str]:
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
    return tag, name, doc, _node_id_opt(tree)


def _parse_event(tree: Tree) -> tuple[str, str, str, str]:
    spec = _first_tree(tree, {"event_spec"})
    kind = str(spec.children[0]) if spec else ""
    name_tokens = [c for c in tree.children if not isinstance(c, Tree)]
    name = unquote(name_tokens[0]) if name_tokens else ""
    if not name and spec and len(spec.children) > 1:
        name = unquote(spec.children[1])

    if tree.data == "start_event":
        tag = "startEvent"
    elif tree.data == "end_event":
        tag = "endEvent"
    elif tree.data == "catch_event":
        tag = "intermediateCatchEvent"
    else:
        tag = "intermediateThrowEvent"

    definition = {
        "none": "",
        "message": "messageEventDefinition",
        "timer": "timerEventDefinition",
        "error": "errorEventDefinition",
        "signal": "signalEventDefinition",
        "escalation": "escalationEventDefinition",
    }.get(kind, "")
    default_name = "start" if tree.data == "start_event" else "end"
    return tag, name or default_name, definition, _node_id_opt(tree)


def _emit_lane_set_from_members(
    process_el: etree._Element,
    lane_names: list[str],
    lane_members: dict[str, list[str]],
    context: XmlContext,
) -> None:
    lane_set = etree.Element(_q("laneSet"), {"id": context.new_id("LaneSet")})
    for lane_name in lane_names:
        lane_el = etree.SubElement(
            lane_set,
            _q("lane"),
            {"id": context.new_id("Lane"), "name": lane_name},
        )
        for node_id in lane_members.get(lane_name, []):
            etree.SubElement(lane_el, _q("flowNodeRef")).text = node_id
    process_el.insert(0, lane_set)


def _optional_name(tree: Tree) -> str:
    if tree.children and not isinstance(tree.children[0], Tree):
        return unquote(tree.children[0])
    return ""


def _node_id_opt(tree: Tree) -> str:
    id_tree = _first_tree(tree, {"id_opt"})
    if id_tree is None or not id_tree.children:
        return ""
    return str(id_tree.children[0])


def _collect_declared_ids(tree: Tree) -> set[str]:
    """All explicit `#id` declarations in a process subtree (enables forward refs)."""
    ids: set[str] = set()
    for sub in tree.iter_subtrees():
        if sub.data == "id_opt" and sub.children:
            ids.add(str(sub.children[0]))
    return ids


def _ref_name(tree: Tree) -> str:
    return str(tree.children[0]) if tree.children else ""


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
    cleaned = "".join(c if c.isalnum() and _XML_NAME_CHAR.match(c) else "_" for c in value).strip(
        "_"
    )
    return cleaned or "Unnamed"
