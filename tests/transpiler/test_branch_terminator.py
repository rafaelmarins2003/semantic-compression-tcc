from lxml import etree

from src.transpiler.xml import transpile
from src.transpiler.xsd import validate_bpmn_xsd

NS = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"


def _flows(xml: str) -> tuple[etree._Element, list[tuple[str, str]]]:
    root = etree.fromstring(xml.encode())
    return root, [(f.get("sourceRef"), f.get("targetRef")) for f in root.iter(NS + "sequenceFlow")]


def test_end_event_has_no_outgoing_flow():
    xml = transpile(
        'process "P" {\n'
        '  start -> task "Check" -> xor "Ok?" {\n'
        '    [yes] -> end "Done"\n'
        '    [no] -> task "Fix"\n'
        '  } -> end "After"\n'
        "}"
    )
    root, flows = _flows(xml)
    fins = {e.get("id") for e in root.iter(NS + "endEvent")}
    assert not [f for f in flows if f[0] in fins]
    assert validate_bpmn_xsd(xml) == []


def test_loop_back_ref_does_not_reach_merge():
    xml = transpile(
        'process "P" {\n'
        '  start -> task "Monitor" -> xor "Delivered?" {\n'
        '    [yes] -> end\n'
        '    [no] -> #"Monitor"\n'
        "  }\n"
        "}"
    )
    root, flows = _flows(xml)
    monitor = next(e.get("id") for e in root.iter(NS + "task") if e.get("name") == "Monitor")
    gateways = [g.get("id") for g in root.iter(NS + "exclusiveGateway")]
    # Sem merge: os dois ramos terminam, então só o split existe.
    assert len(gateways) == 1
    assert [f for f in flows if f[0] == monitor] == [(monitor, gateways[0])]
    assert validate_bpmn_xsd(xml) == []
