"""Gerador de diagramas em camadas para as figuras qualitativas."""

from src.evaluation.bpmn_grafo import tikz

XML = """<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL">
  <process id="p">
    <startEvent id="s" name="start"/>
    <exclusiveGateway id="g" name="Approved?"/>
    <task id="a" name="Pay &amp; close"/>
    <exclusiveGateway id="m" name="merge"/>
    <endEvent id="e"/>
    <sequenceFlow id="f1" sourceRef="s" targetRef="g"/>
    <sequenceFlow id="f2" sourceRef="g" targetRef="a" name="yes"/>
    <sequenceFlow id="f3" sourceRef="g" targetRef="m">
      <conditionExpression>no</conditionExpression>
    </sequenceFlow>
    <sequenceFlow id="f4" sourceRef="g" targetRef="m"/>
    <sequenceFlow id="f5" sourceRef="a" targetRef="m"/>
    <sequenceFlow id="f6" sourceRef="m" targetRef="e"/>
    <sequenceFlow id="f7" sourceRef="m" targetRef="ghost"/>
  </process>
</definitions>"""


def test_nodes_edges_and_labels():
    t = tikz(XML)
    assert t.count("->") >= 6 and "layered layout" in t
    assert r"Pay \& close" in t  # rótulo escapado
    assert "{yes}" in t and "{no}" in t  # condição por name e por conditionExpression
    assert "Approved?" in t and "merge" not in t  # convergência sem nome
    assert "start" not in t.split(r"\begin{document}")[1]  # nome padrão de evento omitido


def test_duplicate_flow_is_bent_and_dangling_flow_dropped():
    t = tikz(XML)
    assert t.count("bend right") == 1
    assert "ghost" not in t and "n6" not in t  # só 5 nós
