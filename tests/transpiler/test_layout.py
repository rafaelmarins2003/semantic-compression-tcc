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
