"""Tests for BPMN-DSL to BPMN XML transpilation."""

from lxml import etree

from src.transpiler import transpile, transpile_file

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
NS = {"bpmn": BPMN_NS}


def _xml(text: str):
    return etree.fromstring(text.encode("utf-8"))


def test_transpile_simple_process():
    root = _xml(transpile('process "P" { start -> task "A" -> end }'))

    assert root.find(".//bpmn:process", NS).get("name") == "P"
    assert root.find(".//bpmn:startEvent", NS) is not None
    assert root.find(".//bpmn:task[@name='A']", NS) is not None
    assert root.find(".//bpmn:endEvent", NS) is not None
    assert len(root.findall(".//bpmn:sequenceFlow", NS)) == 2


def test_transpile_xor_gateway_with_conditions():
    root = _xml(
        transpile(
            """
            process "P" {
              start ->
              xor "Decision" {
                [yes] -> task "A"
                [no] -> task "B"
              } ->
              end
            }
            """
        )
    )

    assert root.find(".//bpmn:exclusiveGateway[@name='Decision']", NS) is not None
    conditions = [el.text for el in root.findall(".//bpmn:conditionExpression", NS)]
    assert conditions == ["yes", "no"]


def test_transpile_laneset():
    root = _xml(
        transpile(
            """
            process "P" {
              lane "Sales" { start, task "A" }
              lane "Ops" { task "B", end }
              start -> task "A" -> task "B" -> end
            }
            """
        )
    )

    lanes = root.findall(".//bpmn:lane", NS)
    assert [lane.get("name") for lane in lanes] == ["Sales", "Ops"]
    assert len(root.findall(".//bpmn:flowNodeRef", NS)) == 4


def test_transpile_collaboration_file():
    root = _xml(transpile_file("examples/collaboration.bpmndsl"))

    assert root.find(".//bpmn:collaboration", NS) is not None
    participants = root.findall(".//bpmn:participant", NS)
    assert [p.get("name") for p in participants] == ["Customer", "Online Shop"]
    assert len(root.findall(".//bpmn:process", NS)) == 2
