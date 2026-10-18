from src.evaluation.render import render
from src.transpiler.xml import transpile

NS = 'xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"'

# O mesmo processo que a DSL abaixo, escrito à mão como faria outro modelador:
# ids opacos, subtipo de tarefa diferente, nomes nos fluxos em vez de expressão.
MANUAL = f"""<definitions {NS} id="d">
  <process id="p">
    <startEvent id="sid-9"/>
    <manualTask id="sid-1" name="Check order"/>
    <exclusiveGateway id="sid-2" name="Complete?"/>
    <userTask id="sid-3" name="Request missing data"/>
    <endEvent id="sid-4" name="Order accepted"/>
    <sequenceFlow id="f1" sourceRef="sid-9" targetRef="sid-1"/>
    <sequenceFlow id="f2" sourceRef="sid-1" targetRef="sid-2"/>
    <sequenceFlow id="f3" sourceRef="sid-2" targetRef="sid-4" name="yes"/>
    <sequenceFlow id="f4" sourceRef="sid-2" targetRef="sid-3" name="no"/>
    <sequenceFlow id="f5" sourceRef="sid-3" targetRef="sid-1"/>
  </process>
</definitions>"""

DSL = """process "P" {
  start -> user "Check order" (doc="Look at every field") -> xor "Complete?" {
    [yes] -> end "Order accepted"
    [no] -> service "Request missing data" -> #"Check order"
  }
}"""


def test_same_process_renders_identically_regardless_of_origin():
    assert render(transpile(DSL)) == render(MANUAL)


def test_origin_conventions_are_removed():
    texto = render(transpile(DSL))
    for vestigio in ("Task_", "StartEvent", "merge", "Look at every field", "user", "service"):
        assert vestigio not in texto
    assert 'start event "start"' not in texto


def test_passthrough_gateway_is_bypassed():
    xml = f"""<definitions {NS} id="d"><process id="p">
      <startEvent id="s"/><exclusiveGateway id="g"/><task id="t" name="A"/><endEvent id="e"/>
      <sequenceFlow id="1" sourceRef="s" targetRef="g"/>
      <sequenceFlow id="2" sourceRef="g" targetRef="t"/>
      <sequenceFlow id="3" sourceRef="t" targetRef="e"/>
    </process></definitions>"""
    texto = render(xml)
    assert "decision" not in texto and "N1 -> N2" in texto


def test_lanes_become_actors():
    texto = render(
        transpile('process "P" { @lane "Clerk" { start -> task "Register claim" -> end } }')
    )
    assert "Actors: Clerk" in texto
    assert 'activity "Register claim" (by Clerk)' in texto
