"""Tests for direct JSON -> BPMN XML conversion."""

from __future__ import annotations

import json
import re

from lxml import etree

from src.data.deterministic.json_to_xml import (
    convert,
    create_bpmn_from_pipeline,
    json_to_process_xml,
)
from src.evaluation.topology import compare
from src.transpiler.xsd import validate_bpmn_xsd

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
NS = {"bpmn": BPMN_NS, "bpmndi": BPMNDI_NS}


def _xml(text: str) -> etree._Element:
    return etree.fromstring(text.encode("utf-8"))


def test_convert_accepts_flows_without_ids_and_adds_valid_layout():
    data = {
        "pool": "Linear",
        "nodes": [
            {"id": "S", "type": "startEvent", "name": "Start"},
            {"id": "A", "type": "task", "name": "Do A"},
            {"id": "E", "type": "endEvent", "name": "End"},
        ],
        "flows": [{"from": "S", "to": "A"}, {"from": "A", "to": "E"}],
    }

    xml = convert(data)
    root = _xml(xml)
    result = compare(data, xml)

    assert validate_bpmn_xsd(xml) == []
    assert root.find(".//bpmndi:BPMNDiagram", NS) is not None
    assert len(root.findall(".//bpmndi:BPMNEdge", NS)) == 2
    assert result["nodes_match"]
    assert result["df_exact"]


def test_convert_uses_existing_type_normalization_for_aliases():
    data = {
        "pool": "Typed",
        "nodes": [
            {"id": "S", "type": "StartMessageEvent", "name": "Request"},
            {"id": "R", "type": "BusinessRule", "name": "Check policy"},
            {"id": "T", "type": "IntermediateTimerEvent", "name": "PT30M"},
            {"id": "M", "type": "IntermediateSignalEventThrowing", "name": "Notify"},
            {"id": "E", "type": "EndErrorEvent", "name": "Failed"},
        ],
        "flows": [
            {"from": "S", "to": "R"},
            {"from": "R", "to": "T"},
            {"from": "T", "to": "M"},
            {"from": "M", "to": "E"},
        ],
    }

    root = _xml(convert(data))

    assert root.find(".//bpmn:startEvent/bpmn:messageEventDefinition", NS) is not None
    assert root.find(".//bpmn:businessRuleTask[@name='Check policy']", NS) is not None
    assert root.find(".//bpmn:intermediateCatchEvent/bpmn:timerEventDefinition", NS) is not None
    assert root.find(".//bpmn:intermediateThrowEvent/bpmn:signalEventDefinition", NS) is not None
    assert root.find(".//bpmn:endEvent/bpmn:errorEventDefinition", NS) is not None


def test_convert_sanitizes_llm_ids_and_keeps_xsd_valid():
    data = {
        "pool": "Clientes Antes de 1º de Fevereiro",
        "lanes": [{"id": "lane 1", "name": "Área & Risco", "refs": ["1 start", "task&x"]}],
        "nodes": [
            {"id": "1 start", "type": "startEvent", "name": ""},
            {"id": "task&x", "type": "userTask", "name": "Revisar"},
            {"id": "end event", "type": "endEvent", "name": ""},
        ],
        "flows": [
            {"id": "flow 1", "from": "1 start", "to": "task&x"},
            {"id": "flow & 2", "from": "task&x", "to": "end event"},
        ],
    }

    xml = convert(data)
    root = _xml(xml)
    ids = [el.get("id") for el in root.xpath("//*[@id]")]

    assert validate_bpmn_xsd(xml) == []
    assert len(ids) == len(set(ids))
    assert all(" " not in item and "&" not in item for item in ids)


def test_create_bpmn_from_pipeline_accepts_fenced_json_and_ignores_layout_json():
    data = {
        "pool": "P",
        "nodes": [
            {"id": "S", "type": "startEvent", "name": ""},
            {"id": "E", "type": "endEvent", "name": ""},
        ],
        "flows": [{"from": "S", "to": "E"}],
    }

    xml = create_bpmn_from_pipeline(
        "```json\n" + json.dumps(data) + "\n```",
        json_layout="not-json-because-layout-is-deterministic",
    )

    assert validate_bpmn_xsd(xml) == []


def test_json_to_process_xml_returns_fragment_without_definitions():
    fragment = json_to_process_xml(
        {
            "pool": "P",
            "nodes": [
                {"id": "S", "type": "startEvent", "name": ""},
                {"id": "E", "type": "endEvent", "name": ""},
            ],
            "flows": [{"from": "S", "to": "E"}],
        }
    )

    assert "<bpmn:definitions" not in fragment
    assert "<bpmn:process" in fragment


def test_duplicate_flow_ids_still_produce_unique_xml_ids():
    """Achado da revisão: dois flows com o mesmo id colapsavam e quebravam o xs:ID."""
    from src.data.deterministic.json_to_xml import convert
    from src.transpiler.xsd import validate_bpmn_xsd

    data = {
        "pool": "P",
        "lanes": [],
        "nodes": [
            {"id": "S", "type": "startEvent", "name": "S"},
            {"id": "A", "type": "userTask", "name": "A"},
            {"id": "E", "type": "endEvent", "name": "E"},
        ],
        "flows": [
            {"id": "f1", "from": "S", "to": "A"},
            {"id": "f1", "from": "A", "to": "E"},
        ],
    }

    xml = convert(data, include_layout=False)
    ids = re.findall(r'<bpmn:sequenceFlow id="([^"]+)"', xml) or re.findall(
        r'<sequenceFlow id="([^"]+)"', xml
    )

    assert validate_bpmn_xsd(xml) == []
    assert len(ids) == len(set(ids)) == 2
