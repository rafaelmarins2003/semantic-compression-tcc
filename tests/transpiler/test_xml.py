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
    root = _xml(transpile('process "P" { start -> catch:none "Wait for completion" -> end }'))

    event = root.find(".//bpmn:intermediateCatchEvent", NS)
    assert event is not None
    assert event.get("name") == "Wait for completion"
    assert len(event) == 0


def test_transpile_multiple_processes_use_document_wide_unique_ids():
    root = _xml(
        transpile(
            """
            process "A" {
              @lane "One" { start -> end }
            }
            process "B" {
              @lane "Two" { start -> end }
            }
            """
        )
    )

    ids = [el.get("id") for el in root.xpath("//*[@id]")]
    assert len(ids) == len(set(ids))
    assert len(root.findall(".//bpmn:process", NS)) == 2


def test_transpile_ref_can_resolve_previous_node_by_name_slug():
    root = _xml(
        transpile(
            """
            process "P" {
              start ->
              user "Acessar página License Seat Links" ->
              task "Revisar retorno" ->
              #acessar_p_gina_license_seat_links
            }
            """
        )
    )

    target = root.find(".//bpmn:userTask[@name='Acessar página License Seat Links']", NS)
    assert target is not None
    loop_flow = root.find(
        f".//bpmn:sequenceFlow[@targetRef='{target.get('id')}']",
        NS,
    )
    assert loop_flow is not None


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


def test_transpile_redeclared_ref_emits_single_node():
    """Redeclarar um `#id` refere-se ao mesmo nó — não emite um segundo.

    Regressão de bug real (2026-08-23): um segundo elemento com o id já usado
    produz `xs:ID` duplicado, isto é, DSL que parseia, transpila e **não valida**
    — furando a garantia de validade por construção. O corpus não pegou porque
    `json_to_dsl` só emite a forma `#ref` nua; modelos de linguagem repetem o
    texto completo do nó ao fechar um laço, e foi assim que apareceu.
    """
    root = _xml(
        transpile(
            """
            process "P" {
              start ->
              task "Conferir itens" #t1 ->
              xor "Tudo conferido?" {
                [sim] -> ()
                [não] -> task "Selecionar mais" -> task "Conferir itens" #t1
              } ->
              end
            }
            """
        )
    )

    ids = [el.get("id") for el in root.xpath("//*[@id]")]
    assert len(ids) == len(set(ids)), "id repetido viola xs:ID"

    alvos = root.findall(".//bpmn:task[@name='Conferir itens']", NS)
    assert len(alvos) == 1, "a redeclaração criou um nó em vez de referenciar o existente"

    # O laço tem de existir: a segunda ocorrência vira aresta de volta ao mesmo nó.
    entradas = root.findall(f".//bpmn:sequenceFlow[@targetRef='{alvos[0].get('id')}']", NS)
    assert len(entradas) >= 2, "sem aresta de retorno, o laço se perdeu"


def test_transpile_redeclared_ref_is_xsd_valid():
    """O caso mínimo que falhava, agora conferido contra o esquema oficial."""
    from src.transpiler.xsd import validate_bpmn_xsd

    xml = transpile(
        'process "P" { start -> task "A" #a -> xor "Q" { [s] -> () [n] -> task "A" #a } -> end }'
    )
    assert validate_bpmn_xsd(xml) == []
