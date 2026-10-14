"""Tests for quoted label references in BPMN-DSL."""

import pytest
from lxml import etree

from src.transpiler import transpile
from src.transpiler.xsd import validate_bpmn_xsd

NS = {"bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL"}


@pytest.mark.parametrize(
    "label,reference,expected_name",
    [
        ('"Test prototype"', '#"Test prototype"', "Test prototype"),
        ('"Test prototype"', '#"  TEST--prototype  "', "Test prototype"),
        (r'"Clicar em \"X\""', r'#"Clicar em \"X\""', 'Clicar em "X"'),
        ('"123 Review"', '#"123 Review"', "123 Review"),
    ],
    ids=["exact", "slug-normalization", "escaped-quotes", "numeric-prefix"],
)
def test_label_back_ref_reuses_node_and_is_xsd_valid(label, reference, expected_name):
    xml = transpile(f'process "P" {{ start -> task {label} -> task "Review" -> {reference} }}')
    assert validate_bpmn_xsd(xml) == []

    root = etree.fromstring(xml.encode("utf-8"))
    tasks = root.findall(".//bpmn:task", NS)
    assert [task.get("name") for task in tasks] == [expected_name, "Review"]
    target, source = tasks
    loop_flows = root.findall(
        f".//bpmn:sequenceFlow[@sourceRef='{source.get('id')}'][@targetRef='{target.get('id')}']",
        NS,
    )
    assert len(loop_flows) == 1
    assert len(root.findall(".//bpmn:sequenceFlow", NS)) == 3


def test_label_ref_requires_exact_slug_match():
    with pytest.raises(ValueError, match=r"^Unresolved DSL ref #test$"):
        transpile('process "P" { start -> task "Test prototype" -> #"Test" }')


def test_label_ref_in_message_flow_points_to_existing_nodes():
    """Sem exportar os slugs para a colaboração, `sourceRef` saía como o slug
    cru ("send_order"), sem elemento correspondente — e o XSD aceitava."""
    xml = transpile(
        'collaboration "C" {'
        ' pool "A" { start -> send "Send order" -> end }'
        ' pool "B" { start -> receive "Get order" -> end }'
        ' message "m" from #"Send order" to #"Get order" }'
    )
    assert validate_bpmn_xsd(xml) == []

    root = etree.fromstring(xml.encode("utf-8"))
    flow = root.find(".//bpmn:messageFlow", NS)
    send = root.find(".//bpmn:sendTask", NS)
    receive = root.find(".//bpmn:receiveTask", NS)
    assert flow.get("sourceRef") == send.get("id")
    assert flow.get("targetRef") == receive.get("id")


def test_explicit_id_wins_over_label_slug_in_message_flow():
    xml = transpile(
        'collaboration "C" {'
        ' pool "A" { start -> send "Notify" -> send "Other" #notify -> end }'
        ' pool "B" { start -> receive "Get" #get -> end }'
        ' message "m" from #notify to #get }'
    )
    root = etree.fromstring(xml.encode("utf-8"))
    other = root.find(".//bpmn:sendTask[@name='Other']", NS)
    assert root.find(".//bpmn:messageFlow", NS).get("sourceRef") == other.get("id")


def test_forward_label_ref_is_not_supported():
    """Decisão de 2026-10-12 (registro-tecnico, A2r): só rótulos já emitidos
    resolvem. Nas falhas do A2, 21 de 28 referências não resolvidas apontavam
    para trás e nenhuma para frente; suportar o caso futuro exigiria reservar
    ids por rótulo antes da emissão, sem caso observado que o justifique."""
    with pytest.raises(ValueError, match=r"^Unresolved DSL ref #later$"):
        transpile('process "P" { start -> #"Later" -> task "Later" -> end }')
