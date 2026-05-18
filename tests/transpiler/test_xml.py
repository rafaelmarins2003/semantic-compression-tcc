"""Tests for BPMN-DSL v2 to BPMN XML transpilation."""

from lxml import etree

from src.transpiler import transpile, transpile_file

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
NS = {"bpmn": BPMN_NS}


def _xml(text: str):
    return etree.fromstring(text.encode("utf-8"))


def test_transpile_simple_named_process():
    root = _xml(transpile('process "P" { start "Begin" -> task "A" -> end "Done" }'))

    assert root.find(".//bpmn:process", NS).get("name") == "P"
    assert root.find(".//bpmn:startEvent[@name='Begin']", NS) is not None
    assert root.find(".//bpmn:task[@name='A']", NS) is not None
    assert root.find(".//bpmn:endEvent[@name='Done']", NS) is not None
    assert len(root.findall(".//bpmn:sequenceFlow", NS)) == 2


def test_transpile_xor_gateway_with_empty_branch():
    root = _xml(
        transpile(
            """
            process "P" {
              start ->
              xor "Decision" {
                [yes] -> task "Approve"
                [skip] -> ()
              } ->
              task "Notify" ->
              end
            }
            """
        )
    )

    assert root.find(".//bpmn:exclusiveGateway[@name='Decision']", NS) is not None
    assert root.find(".//bpmn:task[@name='Notify']", NS) is not None
    conditions = [el.text for el in root.findall(".//bpmn:conditionExpression", NS)]
    assert conditions == ["yes", "skip"]


def test_transpile_v2_lane_blocks():
    root = _xml(
        transpile(
            """
            process "P" {
              @lane "Sales" {
                start -> task "Receive"
              }
              @lane "Operations" {
                -> service "Process" -> end
              }
            }
            """
        )
    )

    lanes = root.findall(".//bpmn:lane", NS)
    assert [lane.get("name") for lane in lanes] == ["Sales", "Operations"]
    assert [len(lane.findall("bpmn:flowNodeRef", NS)) for lane in lanes] == [2, 2]
    assert root.find(".//bpmn:serviceTask[@name='Process']", NS) is not None
    assert len(root.findall(".//bpmn:sequenceFlow", NS)) == 3


def test_transpile_event_gateway():
    root = _xml(
        transpile(
            """
            process "P" {
              start ->
              event "Wait" {
                [:message("approved")] -> catch:message "Approved"
                [:timer("PT30M")] -> catch:timer "Timed out"
              } ->
              end
            }
            """
        )
    )

    assert root.find(".//bpmn:eventBasedGateway[@name='Wait']", NS) is not None
    assert root.find(".//bpmn:messageEventDefinition", NS) is not None
    assert root.find(".//bpmn:timerEventDefinition", NS) is not None
    assert len(root.findall(".//bpmn:intermediateCatchEvent", NS)) == 2


def test_transpile_generic_intermediate_catch_event():
    root = _xml(
        transpile('process "P" { start -> catch:none "Wait for completion" -> end }')
    )

    event = root.find(".//bpmn:intermediateCatchEvent", NS)
    assert event is not None
    assert event.get("name") == "Wait for completion"
    assert len(event) == 0


def test_transpile_collaboration_message_flow():
    root = _xml(
        transpile(
            """
            collaboration "C" {
              pool "Customer" {
                start -> send "Send order" #send_order -> end
              }
              pool "Seller" {
                start:message "Receive order" #receive_order ->
                receive "Store order" #store_order ->
                end
              }
              message "Order" from #send_order to #receive_order
            }
            """
        )
    )

    participants = root.findall(".//bpmn:participant", NS)
    assert [participant.get("name") for participant in participants] == [
        "Customer",
        "Seller",
    ]
    message_flow = root.find(".//bpmn:messageFlow", NS)
    assert message_flow is not None
    assert message_flow.get("name") == "Order"
    assert message_flow.get("sourceRef").startswith("SendTask_")
    assert message_flow.get("targetRef").startswith("StartEvent_")


def test_transpile_file_uses_v2_grammar(tmp_path):
    path = tmp_path / "process.bpmndsl"
    path.write_text('process "P" { start -> user "Review" -> end }', encoding="utf-8")

    root = _xml(transpile_file(path))

    assert root.find(".//bpmn:userTask[@name='Review']", NS) is not None
