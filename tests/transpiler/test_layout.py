"""Tests for deterministic BPMN DI layout generation."""

from __future__ import annotations

from lxml import etree

from src.transpiler import transpile
from src.transpiler.layout import add_layout
from src.transpiler.xsd import validate_bpmn_xsd

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
DI_NS = "http://www.omg.org/spec/DD/20100524/DI"
NS = {"bpmn": BPMN_NS, "bpmndi": BPMNDI_NS, "dc": DC_NS, "di": DI_NS}


def _xml(text: str) -> etree._Element:
    return etree.fromstring(text.encode("utf-8"))


def test_add_layout_adds_shapes_edges_and_keeps_xsd_valid():
    xml = add_layout(transpile('process "P" { start -> task "A" -> end }'))
    root = _xml(xml)

    assert validate_bpmn_xsd(xml) == []
    assert root.find(".//bpmndi:BPMNDiagram", NS) is not None
    assert len(root.findall(".//bpmndi:BPMNShape", NS)) == 3
    assert len(root.findall(".//bpmndi:BPMNEdge", NS)) == 2
    assert len(root.findall(".//di:waypoint", NS)) == 4
    assert len(root.findall(".//dc:Bounds", NS)) == 3


def test_add_layout_is_idempotent():
    first = add_layout(transpile('process "P" { start -> task "A" -> end }'))
    second = add_layout(first)
    root = _xml(second)

    assert validate_bpmn_xsd(second) == []
    assert len(root.findall(".//bpmndi:BPMNDiagram", NS)) == 1
    assert len(root.findall(".//bpmndi:BPMNShape", NS)) == 3
    assert len(root.findall(".//bpmndi:BPMNEdge", NS)) == 2


def test_add_layout_handles_loops_without_rank_inflation():
    xml = add_layout(
        transpile(
            """
            process "P" {
              start -> task "A" #a -> xor "Decide" {
                ["yes"] -> task "B" -> end
                ["no"] -> #a
              }
            }
            """
        )
    )
    root = _xml(xml)
    xs = [
        int(shape.find("dc:Bounds", NS).get("x"))
        for shape in root.findall(".//bpmndi:BPMNShape", NS)
    ]

    assert validate_bpmn_xsd(xml) == []
    # num DAG o rank máximo é n-1; sem remoção de ciclos o back-edge inflava até ~2n
    assert max(xs) <= 160 + (len(xs) - 1) * 190


def test_empty_and_branch_keeps_the_fork_parallel():
    """Branch vazio num `and` era descartado: o fork ficava com 1 saída e o
    paralelismo virava sequência, perdendo arestas direct-follows."""
    xml = transpile('process "P" { start -> and { (); task "B" } -> end }')
    root = _xml(xml)

    forks = [
        el.get("id")
        for el in root.iter(f"{{{BPMN_NS}}}parallelGateway")
        if sum(
            1 for f in root.iter(f"{{{BPMN_NS}}}sequenceFlow") if f.get("sourceRef") == el.get("id")
        )
        > 1
    ]

    assert validate_bpmn_xsd(xml) == []
    assert len(forks) == 1, "o fork deve manter duas saídas com branch vazio"


def test_nodes_of_different_sizes_share_a_vertical_center():
    """Eventos (36px) e tasks (80px) alinhados pelo topo deixavam as arestas tortas."""
    xml = add_layout(transpile('process "P" { start -> task "A" -> end }'))
    root = _xml(xml)

    centers = set()
    for shape in root.findall(".//bpmndi:BPMNShape", NS):
        bounds = shape.find("dc:Bounds", NS)
        centers.add(int(bounds.get("y")) + int(bounds.get("height")) // 2)

    assert validate_bpmn_xsd(xml) == []
    assert len(centers) == 1, f"centros verticais desalinhados: {sorted(centers)}"

    waypoint_ys = {int(wp.get("y")) for wp in root.findall(".//di:waypoint", NS)}
    assert len(waypoint_ys) == 1, f"arestas tortas: {sorted(waypoint_ys)}"


def test_parallel_branches_stay_inside_their_lane():
    """Altura de raia fixa em 120px fazia branches paralelos vazarem para a raia vizinha."""
    xml = add_layout(
        transpile(
            """
            process "P" {
              @lane "Sales" { start -> and { task "B1"; task "B2"; task "B3" } -> task "Join" }
              @lane "Ops" { -> service "S" -> end }
            }
            """
        )
    )
    root = _xml(xml)

    boxes = {}
    for shape in root.findall(".//bpmndi:BPMNShape", NS):
        bounds = shape.find("dc:Bounds", NS)
        boxes[shape.get("bpmnElement")] = (
            int(bounds.get("y")),
            int(bounds.get("height")),
        )
    lane_of = {
        ref.text: lane.get("id")
        for lane in root.findall(".//bpmn:lane", NS)
        for ref in lane.findall("bpmn:flowNodeRef", NS)
    }

    assert validate_bpmn_xsd(xml) == []
    assert lane_of, "o processo de teste precisa ter raias"
    for node_id, lane_id in lane_of.items():
        node_y, node_h = boxes[node_id]
        lane_y, lane_h = boxes[lane_id]
        assert lane_y <= node_y and node_y + node_h <= lane_y + lane_h, (
            f"{node_id} vazou de {lane_id}"
        )

    lane_boxes = sorted(boxes[lid] for lid in set(lane_of.values()))
    for (y1, h1), (y2, _) in zip(lane_boxes, lane_boxes[1:]):
        assert y1 + h1 <= y2, "raias sobrepostas"


def test_pool_encloses_its_lanes():
    """Achado da revisão: com altura de raia variável, a última raia ficava
    pendurada fora do pool e o próximo processo começava dentro dela."""
    from src.data.deterministic.json_to_xml import convert

    data = {
        "pool": "P",
        "lanes": [
            {"id": "L1", "name": "Sales", "refs": ["E01", "T1", "T2", "T3"]},
            {"id": "L2", "name": "Ops", "refs": ["T4", "E02"]},
        ],
        "nodes": [
            {"id": "E01", "type": "startEvent", "name": "S", "lane": "L1"},
            {"id": "G", "type": "parallelGateway", "name": "F", "lane": "L1"},
            {"id": "T1", "type": "userTask", "name": "a", "lane": "L1"},
            {"id": "T2", "type": "userTask", "name": "b", "lane": "L1"},
            {"id": "T3", "type": "userTask", "name": "c", "lane": "L1"},
            {"id": "GJ", "type": "parallelGateway", "name": "J", "lane": "L1"},
            {"id": "T4", "type": "userTask", "name": "d", "lane": "L2"},
            {"id": "E02", "type": "endEvent", "name": "E", "lane": "L2"},
        ],
        "flows": [
            {"id": "f0", "from": "E01", "to": "G"},
            {"id": "f1", "from": "G", "to": "T1"},
            {"id": "f2", "from": "G", "to": "T2"},
            {"id": "f3", "from": "G", "to": "T3"},
            {"id": "f4", "from": "T1", "to": "GJ"},
            {"id": "f5", "from": "T2", "to": "GJ"},
            {"id": "f6", "from": "T3", "to": "GJ"},
            {"id": "f7", "from": "GJ", "to": "T4"},
            {"id": "f8", "from": "T4", "to": "E02"},
        ],
    }
    root = _xml(convert(data))

    boxes = {}
    for shape in root.findall(".//bpmndi:BPMNShape", NS):
        bounds = shape.find("dc:Bounds", NS)
        boxes[shape.get("bpmnElement")] = (int(bounds.get("y")), int(bounds.get("height")))

    pool = next(v for k, v in boxes.items() if k.startswith("Participant"))
    lanes = [v for k, v in boxes.items() if k.startswith("Lane")]

    assert lanes, "o processo de teste precisa ter raias"
    for lane_y, lane_h in lanes:
        assert pool[0] <= lane_y and lane_y + lane_h <= pool[0] + pool[1], (
            f"raia {lane_y}..{lane_y + lane_h} fora do pool {pool[0]}..{pool[0] + pool[1]}"
        )


def test_add_layout_includes_lane_shapes():
    xml = add_layout(
        transpile(
            """
            process "P" {
              @lane "Sales" { start -> task "Receive" }
              @lane "Ops" { -> service "Process" -> end }
            }
            """
        )
    )
    root = _xml(xml)
    lane_ids = {lane.get("id") for lane in root.findall(".//bpmn:lane", NS)}
    shape_refs = {shape.get("bpmnElement") for shape in root.findall(".//bpmndi:BPMNShape", NS)}

    assert validate_bpmn_xsd(xml) == []
    assert lane_ids <= shape_refs
