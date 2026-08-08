"""Add a deterministic BPMN DI layout to logical BPMN XML."""

from __future__ import annotations

from collections import defaultdict, deque

from lxml import etree

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
DI_NS = "http://www.omg.org/spec/DD/20100524/DI"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

NSMAP = {
    "bpmn": BPMN_NS,
    "bpmndi": BPMNDI_NS,
    "dc": DC_NS,
    "di": DI_NS,
    "xsi": XSI_NS,
}

NODE_SIZE = {
    "startEvent": (36, 36),
    "endEvent": (36, 36),
    "intermediateCatchEvent": (36, 36),
    "intermediateThrowEvent": (36, 36),
    "exclusiveGateway": (50, 50),
    "parallelGateway": (50, 50),
    "inclusiveGateway": (50, 50),
    "eventBasedGateway": (50, 50),
    "subProcess": (150, 90),
    "callActivity": (150, 90),
    "textAnnotation": (120, 50),
}

TASK_TAGS = {
    "task",
    "manualTask",
    "serviceTask",
    "userTask",
    "scriptTask",
    "sendTask",
    "receiveTask",
    "businessRuleTask",
}


def add_layout(xml_text: str) -> str:
    """Return BPMN XML with deterministic BPMNDiagram/BPMNPlane DI elements."""
    root = etree.fromstring(xml_text.encode("utf-8"))
    _remove_existing_diagrams(root)

    processes = root.findall(_bpmn("process"))
    if not processes:
        return etree.tostring(root, encoding="unicode", pretty_print=True)

    plane_ref = _plane_reference(root, processes)
    diagram = etree.SubElement(
        root,
        _bpmndi("BPMNDiagram"),
        {"id": _unique_id(root, "BPMNDiagram_1")},
        nsmap=NSMAP,
    )
    plane = etree.SubElement(
        diagram,
        _bpmndi("BPMNPlane"),
        {
            "id": _unique_id(root, "BPMNPlane_1"),
            "bpmnElement": plane_ref,
        },
    )

    y_cursor = 100
    for process in processes:
        y_cursor = _layout_process(root, plane, process, y_cursor)

    return etree.tostring(root, encoding="unicode", pretty_print=True)


def layout(process_xml: str) -> str:
    """Compatibility wrapper: return only the BPMN DI fragment for a process fragment."""
    wrapped = (
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" '
        'xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" '
        'xmlns:di="http://www.omg.org/spec/DD/20100524/DI" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'id="Definitions_Layout" targetNamespace="http://www.omg.org/spec/BPMN/20100524/MODEL">'
        f"{process_xml}</bpmn:definitions>"
    )
    root = etree.fromstring(add_layout(wrapped).encode("utf-8"))
    diagrams = root.findall(_bpmndi("BPMNDiagram"))
    return "\n".join(etree.tostring(el, encoding="unicode", pretty_print=True) for el in diagrams)


def _layout_process(
    root: etree._Element,
    plane: etree._Element,
    process: etree._Element,
    y_origin: int,
) -> int:
    nodes = _flow_nodes(process)
    flows = process.findall(_bpmn("sequenceFlow"))
    if not nodes:
        return y_origin + 120

    ranks = _node_ranks(nodes, flows)
    lane_by_node, lane_order = _lane_members(process)
    positions = _node_positions(nodes, ranks, lane_by_node, lane_order, y_origin)

    participant = _participant_for(root, process.get("id", ""))
    height = max(120, max(y + h for _, (x, y, _, h) in positions.items()) - y_origin + 80)
    width = max(360, max(x + w for _, (x, _, w, _) in positions.items()) + 120)

    if participant is not None:
        _add_shape(plane, root, participant.get("id"), 80, y_origin - 45, width, height)

    for lane in process.findall(f"{_bpmn('laneSet')}/{_bpmn('lane')}"):
        lane_name = lane.get("name", lane.get("id", ""))
        lane_index = lane_order.index(lane_name) if lane_name in lane_order else 0
        _add_shape(
            plane,
            root,
            lane.get("id"),
            110,
            y_origin + lane_index * 120 - 20,
            width - 60,
            120,
            {"isHorizontal": "true"},
        )

    for node in nodes:
        x, y, width_, height_ = positions[node.get("id")]
        _add_shape(plane, root, node.get("id"), x, y, width_, height_)

    for flow in flows:
        source = positions.get(flow.get("sourceRef"))
        target = positions.get(flow.get("targetRef"))
        if source is None or target is None:
            continue
        _add_edge(plane, root, flow.get("id"), source, target)

    return y_origin + height + 90


def _flow_nodes(process: etree._Element) -> list[etree._Element]:
    return [
        child
        for child in process
        if isinstance(child.tag, str)
        and child.tag.startswith(f"{{{BPMN_NS}}}")
        and _local_name(child) in TASK_TAGS | set(NODE_SIZE)
    ]


def _node_ranks(nodes: list[etree._Element], flows: list[etree._Element]) -> dict[str, int]:
    node_ids = [node.get("id") for node in nodes if node.get("id")]
    node_set = set(node_ids)
    succs: dict[str, list[str]] = defaultdict(list)
    indegree = {node_id: 0 for node_id in node_ids}

    for flow in flows:
        source = flow.get("sourceRef")
        target = flow.get("targetRef")
        if source in node_set and target in node_set:
            succs[source].append(target)
            indegree[target] += 1

    starts = [
        node.get("id")
        for node in nodes
        if _local_name(node) == "startEvent" or indegree.get(node.get("id"), 0) == 0
    ] or node_ids[:1]
    _drop_back_edges(succs, starts)

    queue = deque(starts)
    ranks = {node_id: 0 for node_id in queue}

    while queue:
        current = queue.popleft()
        for target in succs.get(current, []):
            next_rank = ranks[current] + 1
            if next_rank > ranks.get(target, -1):
                ranks[target] = next_rank
                queue.append(target)

    fallback_rank = max(ranks.values(), default=0) + 1
    for node_id in node_ids:
        if node_id not in ranks:
            ranks[node_id] = fallback_rank
            fallback_rank += 1
    return ranks


def _drop_back_edges(succs: dict[str, list[str]], starts: list[str]) -> None:
    """Remoção de ciclos (passo 1 do Sugiyama): descarta arestas de retorno via DFS.

    Sem isso, o ranking longest-path infla os ranks de nós em ciclo até ~n,
    esticando o diagrama. Ciclos não alcançáveis a partir de `starts` ficam
    intactos, mas o BFS de ranking também nunca os visita.
    """
    visiting: set[str] = set()
    visited: set[str] = set()
    back_edges: list[tuple[str, str]] = []

    for start in starts:
        if start in visited:
            continue
        visiting.add(start)
        stack = [(start, 0)]
        while stack:
            node, i = stack[-1]
            children = succs.get(node, [])
            if i < len(children):
                stack[-1] = (node, i + 1)
                child = children[i]
                if child in visiting:
                    back_edges.append((node, child))
                elif child not in visited:
                    visiting.add(child)
                    stack.append((child, 0))
            else:
                visiting.discard(node)
                visited.add(node)
                stack.pop()

    for source, target in back_edges:
        succs[source].remove(target)


def _lane_members(process: etree._Element) -> tuple[dict[str, str], list[str]]:
    lane_by_node = {}
    lane_order = []
    for lane in process.findall(f"{_bpmn('laneSet')}/{_bpmn('lane')}"):
        lane_name = lane.get("name", lane.get("id", ""))
        lane_order.append(lane_name)
        for ref in lane.findall(_bpmn("flowNodeRef")):
            if ref.text:
                lane_by_node[ref.text] = lane_name
    return lane_by_node, lane_order


def _node_positions(
    nodes: list[etree._Element],
    ranks: dict[str, int],
    lane_by_node: dict[str, str],
    lane_order: list[str],
    y_origin: int,
) -> dict[str, tuple[int, int, int, int]]:
    lane_index = {name: idx for idx, name in enumerate(lane_order)}
    used_slots: dict[tuple[int, int], int] = defaultdict(int)
    positions = {}

    for node in nodes:
        node_id = node.get("id")
        rank = ranks[node_id]
        lane = lane_by_node.get(node_id)
        row = lane_index.get(lane, 0)
        slot = used_slots[(rank, row)]
        used_slots[(rank, row)] += 1

        width, height = NODE_SIZE.get(_local_name(node), (120, 80))
        x = 160 + rank * 190
        y = y_origin + row * 120 + 20 + slot * 95
        positions[node_id] = (x, y, width, height)

    return positions


def _add_shape(
    plane: etree._Element,
    root: etree._Element,
    bpmn_id: str | None,
    x: int,
    y: int,
    width: int,
    height: int,
    attrs: dict[str, str] | None = None,
) -> None:
    if not bpmn_id:
        return
    shape_attrs = {
        "id": _unique_id(root, f"{bpmn_id}_di"),
        "bpmnElement": bpmn_id,
        **(attrs or {}),
    }
    shape = etree.SubElement(plane, _bpmndi("BPMNShape"), shape_attrs)
    etree.SubElement(
        shape,
        _dc("Bounds"),
        {"x": str(x), "y": str(y), "width": str(width), "height": str(height)},
    )


def _add_edge(
    plane: etree._Element,
    root: etree._Element,
    flow_id: str | None,
    source: tuple[int, int, int, int],
    target: tuple[int, int, int, int],
) -> None:
    if not flow_id:
        return
    sx, sy, sw, sh = source
    tx, ty, _, th = target
    edge = etree.SubElement(
        plane,
        _bpmndi("BPMNEdge"),
        {"id": _unique_id(root, f"{flow_id}_di"), "bpmnElement": flow_id},
    )
    etree.SubElement(edge, _di("waypoint"), {"x": str(sx + sw), "y": str(sy + sh // 2)})
    etree.SubElement(edge, _di("waypoint"), {"x": str(tx), "y": str(ty + th // 2)})


def _participant_for(root: etree._Element, process_id: str) -> etree._Element | None:
    for participant in root.findall(f"{_bpmn('collaboration')}/{_bpmn('participant')}"):
        if participant.get("processRef") == process_id:
            return participant
    return None


def _plane_reference(root: etree._Element, processes: list[etree._Element]) -> str:
    collaboration = root.find(_bpmn("collaboration"))
    if collaboration is not None and collaboration.get("id"):
        return collaboration.get("id")
    return processes[0].get("id", "")


def _remove_existing_diagrams(root: etree._Element) -> None:
    for diagram in root.findall(_bpmndi("BPMNDiagram")):
        root.remove(diagram)


def _unique_id(root: etree._Element, preferred: str) -> str:
    used = {el.get("id") for el in root.xpath("//*[@id]")}
    candidate = preferred
    suffix = 2
    while candidate in used:
        candidate = f"{preferred}_{suffix}"
        suffix += 1
    return candidate


def _local_name(el: etree._Element) -> str:
    return el.tag.split("}", 1)[1] if "}" in el.tag else el.tag


def _bpmn(tag: str) -> str:
    return f"{{{BPMN_NS}}}{tag}"


def _bpmndi(tag: str) -> str:
    return f"{{{BPMNDI_NS}}}{tag}"


def _dc(tag: str) -> str:
    return f"{{{DC_NS}}}{tag}"


def _di(tag: str) -> str:
    return f"{{{DI_NS}}}{tag}"
