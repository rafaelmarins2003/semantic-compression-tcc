"""Tests for JSON → BPMN-DSL converter.

Categories:
  A — graph utilities (build_adjacency, find_start, classify_gateway)
  B — find_join (BFS intersection gateway matching)
  C — emit_node (single node → DSL string)
  D — linearize integration (graph segment → DSL sequence)
  E — full convert (JSON dict → complete DSL with round-trip parse validation)
  F — error handling / edge cases
"""

import warnings

from src.data.manipulation.deterministic.graph import (
    Edge,
    Node,
    ProcessGraph,
    build_adjacency,
    classify_gateway,
    find_orphans,
    find_start,
)
from src.data.manipulation.deterministic.json_to_dsl import (
    convert,
    emit_node,
    find_join,
    linearize,
)
from src.dsl.parser import parse

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_graph(nodes_list, edges_list, lanes=None, name="Test Process") -> ProcessGraph:
    """Quick helper to build a ProcessGraph from raw tuples."""
    nodes = {}
    for n in nodes_list:
        if len(n) == 3:
            nid, ntype, nname = n
            nodes[nid] = Node(id=nid, type=ntype, name=nname)
        else:
            nid, ntype, nname, doc = n
            nodes[nid] = Node(id=nid, type=ntype, name=nname, doc=doc)

    edges = []
    for i, e in enumerate(edges_list):
        if len(e) == 2:
            src, tgt = e
            edges.append(Edge(id=f"f{i}", source=src, target=tgt))
        elif len(e) == 3:
            src, tgt, cond = e
            edges.append(Edge(id=f"f{i}", source=src, target=tgt, condition=cond))
        else:
            src, tgt, cond, label = e
            edges.append(Edge(id=f"f{i}", source=src, target=tgt, condition=cond, label=label))

    succs, preds, edge_map = build_adjacency(nodes, edges)
    start_id = find_start(nodes, preds)
    lane_objs = lanes or []

    return ProcessGraph(
        name=name,
        nodes=nodes,
        edges=edges,
        succs=succs,
        preds=preds,
        edge_map=edge_map,
        lanes=lane_objs,
        start_id=start_id,
    )


def _roundtrip(dsl_text: str):
    """Parse DSL text with the Lark parser — raises on syntax error."""
    return parse(dsl_text)


# ═══════════════════════════════════════════════════════════════════════════════
# Category A — Graph utilities
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildAdjacency:
    def test_simple_chain(self):
        nodes = {"A": Node("A", "task", "a"), "B": Node("B", "task", "b")}
        edges = [Edge("f1", "A", "B")]
        succs, preds, emap = build_adjacency(nodes, edges)
        assert succs["A"] == ["B"]
        assert preds["B"] == ["A"]
        assert ("A", "B") in emap

    def test_unknown_source_warns(self):
        nodes = {"B": Node("B", "task", "b")}
        edges = [Edge("f1", "GHOST", "B")]
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            succs, preds, emap = build_adjacency(nodes, edges)
            assert len(w) == 1
            assert "unknown source" in str(w[0].message)
        assert not succs
        assert not preds


class TestFindStart:
    def test_single_start_event(self):
        nodes = {
            "E01": Node("E01", "startEvent", "Start"),
            "T01": Node("T01", "task", "Do"),
        }
        preds: dict[str, list[str]] = {"T01": ["E01"]}
        assert find_start(nodes, preds) == "E01"

    def test_fallback_in_degree_zero(self):
        nodes = {
            "T01": Node("T01", "task", "First"),
            "T02": Node("T02", "task", "Second"),
        }
        preds: dict[str, list[str]] = {"T02": ["T01"]}
        assert find_start(nodes, preds) == "T01"


class TestClassifyGateway:
    def test_fork(self):
        succs = {"G": ["A", "B"]}
        preds = {"G": ["X"]}
        assert classify_gateway("G", succs, preds) == "fork"

    def test_join(self):
        succs = {"G": ["X"]}
        preds = {"G": ["A", "B"]}
        assert classify_gateway("G", succs, preds) == "join"

    def test_both(self):
        succs = {"G": ["X", "Y"]}
        preds = {"G": ["A", "B"]}
        assert classify_gateway("G", succs, preds) == "both"

    def test_none(self):
        succs = {"G": ["X"]}
        preds = {"G": ["A"]}
        assert classify_gateway("G", succs, preds) == "none"


class TestFindOrphans:
    def test_no_orphans(self):
        nodes = {"A": Node("A", "startEvent", "s"), "B": Node("B", "task", "b")}
        succs = {"A": ["B"]}
        assert find_orphans(nodes, "A", succs) == set()

    def test_with_orphan(self):
        nodes = {
            "A": Node("A", "startEvent", "s"),
            "B": Node("B", "task", "b"),
            "C": Node("C", "task", "orphan"),
        }
        succs = {"A": ["B"]}
        assert find_orphans(nodes, "A", succs) == {"C"}


# ═══════════════════════════════════════════════════════════════════════════════
# Category B — find_join
# ═══════════════════════════════════════════════════════════════════════════════


class TestFindJoin:
    def test_simple_xor(self):
        """Fork G → A,B → merge M → end."""
        g = _make_graph(
            [
                ("S", "startEvent", "s"),
                ("G", "exclusiveGateway", "G"),
                ("A", "task", "A"),
                ("B", "task", "B"),
                ("M", "exclusiveGateway", "M"),
                ("E", "endEvent", "e"),
            ],
            [
                ("S", "G"),
                ("G", "A", "cond_a"),
                ("G", "B", "cond_b"),
                ("A", "M"),
                ("B", "M"),
                ("M", "E"),
            ],
        )
        assert find_join(g, "G") == "M"

    def test_parallel_three_branches(self):
        """Fork P → A,B,C → join J."""
        g = _make_graph(
            [
                ("S", "startEvent", "s"),
                ("P", "parallelGateway", "P"),
                ("A", "task", "A"),
                ("B", "task", "B"),
                ("C", "task", "C"),
                ("J", "parallelGateway", "J"),
                ("E", "endEvent", "e"),
            ],
            [
                ("S", "P"),
                ("P", "A"),
                ("P", "B"),
                ("P", "C"),
                ("A", "J"),
                ("B", "J"),
                ("C", "J"),
                ("J", "E"),
            ],
        )
        assert find_join(g, "P") == "J"

    def test_no_convergence(self):
        """Branches end at different end events."""
        g = _make_graph(
            [
                ("S", "startEvent", "s"),
                ("G", "exclusiveGateway", "G"),
                ("A", "task", "A"),
                ("B", "task", "B"),
                ("E1", "endEvent", "e1"),
                ("E2", "endEvent", "e2"),
            ],
            [("S", "G"), ("G", "A", "a"), ("G", "B", "b"), ("A", "E1"), ("B", "E2")],
        )
        assert find_join(g, "G") is None

    def test_implicit_merge_at_task(self):
        """XOR branches converge at a regular task, not a gateway."""
        g = _make_graph(
            [
                ("S", "startEvent", "s"),
                ("G", "exclusiveGateway", "G"),
                ("A", "task", "A"),
                ("B", "task", "B"),
                ("C", "task", "Merge Here"),
                ("E", "endEvent", "e"),
            ],
            [("S", "G"), ("G", "A", "a"), ("G", "B", "b"), ("A", "C"), ("B", "C"), ("C", "E")],
        )
        assert find_join(g, "G") == "C"

    def test_nested_fork_join(self):
        """Outer AND → branch has inner XOR → all converge."""
        g = _make_graph(
            [
                ("S", "startEvent", "s"),
                ("P", "parallelGateway", "P"),
                ("X", "exclusiveGateway", "X"),
                ("A", "task", "A"),
                ("B", "task", "B"),
                ("M", "exclusiveGateway", "M"),
                ("C", "task", "C"),
                ("J", "parallelGateway", "J"),
                ("E", "endEvent", "e"),
            ],
            [
                ("S", "P"),
                ("P", "X"),
                ("P", "C"),
                ("X", "A", "a"),
                ("X", "B", "b"),
                ("A", "M"),
                ("B", "M"),
                ("M", "J"),
                ("C", "J"),
                ("J", "E"),
            ],
        )
        assert find_join(g, "P") == "J"
        assert find_join(g, "X") == "M"


# ═══════════════════════════════════════════════════════════════════════════════
# Category C — emit_node
# ═══════════════════════════════════════════════════════════════════════════════


class TestEmitNode:
    def test_plain_task(self):
        assert emit_node(Node("T1", "task", "Do Work")) == 'task "Do Work"'

    def test_manual_task(self):
        assert emit_node(Node("T1", "manualTask", "Build")) == 'manual "Build"'

    def test_service_task(self):
        assert emit_node(Node("T1", "serviceTask", "Calculate")) == 'service "Calculate"'

    def test_user_task(self):
        assert emit_node(Node("T1", "userTask", "Review")) == 'user "Review"'

    def test_send_task(self):
        assert emit_node(Node("T1", "sendTask", "Notify")) == 'send "Notify"'

    def test_receive_task(self):
        assert emit_node(Node("T1", "receiveTask", "Wait")) == 'receive "Wait"'

    def test_rule_task(self):
        assert emit_node(Node("T1", "businessRuleTask", "Check")) == 'rule "Check"'

    def test_task_with_doc(self):
        n = Node("T1", "task", "Pay", doc="See SLA")
        assert emit_node(n) == 'task "Pay" (doc="See SLA")'

    def test_start_event(self):
        assert emit_node(Node("E1", "startEvent", "s")) == "start"

    def test_end_event(self):
        assert emit_node(Node("E1", "endEvent", "e")) == "end"

    def test_start_message_event(self):
        n = Node("E1", "startMessageEvent", "order-received")
        assert emit_node(n) == 'start:message("order-received")'

    def test_end_error_event(self):
        n = Node("E1", "endErrorEvent", "payment-failed")
        assert emit_node(n) == 'end:error("payment-failed")'

    def test_catch_timer(self):
        n = Node("E1", "catchTimerEvent", "PT1H")
        assert emit_node(n) == 'catch:timer("PT1H")'

    def test_throw_signal(self):
        n = Node("E1", "throwSignalEvent", "fraud-alert")
        assert emit_node(n) == 'throw:signal("fraud-alert")'

    def test_name_with_quotes_escaped(self):
        n = Node("T1", "task", 'Say "hello"')
        assert emit_node(n) == 'task "Say \\"hello\\""'

    def test_unknown_type_fallback(self):
        n = Node("T1", "weirdType", "Stuff")
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = emit_node(n)
        assert result == 'task "Stuff"'


# ═══════════════════════════════════════════════════════════════════════════════
# Category D — linearize integration
# ═══════════════════════════════════════════════════════════════════════════════


class TestLinearize:
    def test_linear_sequence(self):
        g = _make_graph(
            [
                ("S", "startEvent", "s"),
                ("A", "task", "A"),
                ("B", "task", "B"),
                ("E", "endEvent", "e"),
            ],
            [("S", "A"), ("A", "B"), ("B", "E")],
        )
        parts = linearize(g, "S")
        assert parts == ["start", 'task "A"', 'task "B"', "end"]

    def test_xor_two_branches(self):
        g = _make_graph(
            [
                ("S", "startEvent", "s"),
                ("G", "exclusiveGateway", "G"),
                ("A", "task", "A"),
                ("B", "task", "B"),
                ("M", "exclusiveGateway", "M"),
                ("E", "endEvent", "e"),
            ],
            [("S", "G"), ("G", "A", "yes"), ("G", "B", "no"), ("A", "M"), ("B", "M"), ("M", "E")],
        )
        parts = linearize(g, "S")
        dsl = " -> ".join(parts)
        # Should start with 'start' and end with 'end'
        assert dsl.startswith("start")
        assert dsl.endswith("end")
        # Should contain xor block with conditions
        assert "xor" in dsl
        assert "[yes]" in dsl
        assert "[no]" in dsl

    def test_and_parallel(self):
        g = _make_graph(
            [
                ("S", "startEvent", "s"),
                ("P", "parallelGateway", "P"),
                ("A", "task", "A"),
                ("B", "task", "B"),
                ("J", "parallelGateway", "J"),
                ("E", "endEvent", "e"),
            ],
            [("S", "P"), ("P", "A"), ("P", "B"), ("A", "J"), ("B", "J"), ("J", "E")],
        )
        parts = linearize(g, "S")
        dsl = " -> ".join(parts)
        assert "and" in dsl
        assert 'task "A"' in dsl
        assert 'task "B"' in dsl

    def test_nested_xor_in_and(self):
        g = _make_graph(
            [
                ("S", "startEvent", "s"),
                ("P", "parallelGateway", "Fork"),
                ("X", "exclusiveGateway", "Decision"),
                ("A", "task", "A"),
                ("B", "task", "B"),
                ("XM", "exclusiveGateway", "XM"),
                ("C", "task", "C"),
                ("J", "parallelGateway", "Join"),
                ("E", "endEvent", "e"),
            ],
            [
                ("S", "P"),
                ("P", "X"),
                ("P", "C"),
                ("X", "A", "yes"),
                ("X", "B", "no"),
                ("A", "XM"),
                ("B", "XM"),
                ("XM", "J"),
                ("C", "J"),
                ("J", "E"),
            ],
        )
        parts = linearize(g, "S")
        dsl = " -> ".join(parts)
        assert "and" in dsl
        assert "xor" in dsl
        assert "[yes]" in dsl

    def test_skip_merge_only_gateway(self):
        """Pure merge gateway (in-degree > 1, out-degree 1) should not appear in output."""
        g = _make_graph(
            [
                ("S", "startEvent", "s"),
                ("G", "exclusiveGateway", "Fork"),
                ("A", "task", "A"),
                ("B", "task", "B"),
                ("M", "exclusiveGateway", "Merge"),
                ("E", "endEvent", "e"),
            ],
            [("S", "G"), ("G", "A", "a"), ("G", "B", "b"), ("A", "M"), ("B", "M"), ("M", "E")],
        )
        parts = linearize(g, "S")
        dsl = " -> ".join(parts)
        assert '"Merge"' not in dsl  # merge gateway name should NOT appear

    def test_branches_ending_at_different_ends(self):
        g = _make_graph(
            [
                ("S", "startEvent", "s"),
                ("G", "exclusiveGateway", "G"),
                ("A", "task", "A"),
                ("B", "task", "B"),
                ("E1", "endEvent", "e1"),
                ("E2", "endEvent", "e2"),
            ],
            [("S", "G"), ("G", "A", "a"), ("G", "B", "b"), ("A", "E1"), ("B", "E2")],
        )
        parts = linearize(g, "S")
        dsl = " -> ".join(parts)
        assert "xor" in dsl
        # Both branches should contain their end events
        assert dsl.count("end") == 2

    def test_cycle_produces_ref(self):
        """Back-edge to a previously visited task should emit #ref."""
        g = _make_graph(
            [
                ("S", "startEvent", "s"),
                ("A", "task", "Do Work"),
                ("G", "exclusiveGateway", "Retry?"),
                ("E", "endEvent", "e"),
            ],
            [("S", "A"), ("A", "G"), ("G", "A", "retry"), ("G", "E", "done")],
        )
        parts = linearize(g, "S")
        dsl = " -> ".join(parts)
        assert '#"Do Work"' in dsl


# ═══════════════════════════════════════════════════════════════════════════════
# Category E — full convert with round-trip validation
# ═══════════════════════════════════════════════════════════════════════════════


class TestConvert:
    """Full JSON → DSL conversion with Lark parser round-trip validation."""

    def test_simple_linear(self):
        data = {
            "pool": "Order Process",
            "lanes": [],
            "nodes": [
                {"id": "E01", "type": "startEvent", "name": "Start"},
                {"id": "T01", "type": "manualTask", "name": "Receive Order"},
                {"id": "T02", "type": "serviceTask", "name": "Process Payment"},
                {"id": "E02", "type": "endEvent", "name": "End"},
            ],
            "flows": [
                {"id": "f1", "from": "E01", "to": "T01"},
                {"id": "f2", "from": "T01", "to": "T02"},
                {"id": "f3", "from": "T02", "to": "E02"},
            ],
        }
        dsl = convert(data)
        tree = _roundtrip(dsl)
        tasks = list(tree.find_data("task"))
        assert len(tasks) == 2

    def test_xor_with_conditions(self):
        data = {
            "pool": "Approval",
            "lanes": [],
            "nodes": [
                {"id": "E01", "type": "startEvent", "name": "Start"},
                {"id": "T01", "type": "userTask", "name": "Review"},
                {"id": "G01", "type": "exclusiveGateway", "name": "Approved?"},
                {"id": "T02", "type": "task", "name": "Approve"},
                {"id": "T03", "type": "task", "name": "Reject"},
                {"id": "G02", "type": "exclusiveGateway", "name": "Merge"},
                {"id": "E02", "type": "endEvent", "name": "End"},
            ],
            "flows": [
                {"id": "f1", "from": "E01", "to": "T01"},
                {"id": "f2", "from": "T01", "to": "G01"},
                {"id": "f3", "from": "G01", "to": "T02", "cond": "yes"},
                {"id": "f4", "from": "G01", "to": "T03", "cond": "no"},
                {"id": "f5", "from": "T02", "to": "G02"},
                {"id": "f6", "from": "T03", "to": "G02"},
                {"id": "f7", "from": "G02", "to": "E02"},
            ],
        }
        dsl = convert(data)
        tree = _roundtrip(dsl)
        xors = list(tree.find_data("xor_gw"))
        assert len(xors) == 1
        branches = list(tree.find_data("branch"))
        assert len(branches) == 2

    def test_parallel_gateway(self):
        data = {
            "pool": "Parallel Process",
            "lanes": [],
            "nodes": [
                {"id": "E01", "type": "startEvent", "name": "Start"},
                {"id": "P01", "type": "parallelGateway", "name": "Split"},
                {"id": "T01", "type": "task", "name": "Branch A"},
                {"id": "T02", "type": "task", "name": "Branch B"},
                {"id": "P02", "type": "parallelGateway", "name": "Join"},
                {"id": "E02", "type": "endEvent", "name": "End"},
            ],
            "flows": [
                {"id": "f1", "from": "E01", "to": "P01"},
                {"id": "f2", "from": "P01", "to": "T01"},
                {"id": "f3", "from": "P01", "to": "T02"},
                {"id": "f4", "from": "T01", "to": "P02"},
                {"id": "f5", "from": "T02", "to": "P02"},
                {"id": "f6", "from": "P02", "to": "E02"},
            ],
        }
        dsl = convert(data)
        tree = _roundtrip(dsl)
        ands = list(tree.find_data("and_gw"))
        assert len(ands) == 1

    def test_with_lanes(self):
        data = {
            "pool": "Process with Lanes",
            "lanes": [
                {"id": "L1", "name": "Sales", "refs": ["E01", "T01"]},
                {"id": "L2", "name": "Finance", "refs": ["T02", "E02"]},
            ],
            "nodes": [
                {"id": "E01", "type": "startEvent", "name": "Start", "lane": "L1"},
                {"id": "T01", "type": "task", "name": "Take Order", "lane": "L1"},
                {"id": "T02", "type": "serviceTask", "name": "Invoice", "lane": "L2"},
                {"id": "E02", "type": "endEvent", "name": "End", "lane": "L2"},
            ],
            "flows": [
                {"id": "f1", "from": "E01", "to": "T01"},
                {"id": "f2", "from": "T01", "to": "T02"},
                {"id": "f3", "from": "T02", "to": "E02"},
            ],
        }
        dsl = convert(data)
        tree = _roundtrip(dsl)
        lanes = list(tree.find_data("lane"))
        assert len(lanes) == 2

    def test_nested_and_xor(self):
        """AND with nested XOR inside one branch — the example from the user's JSON."""
        data = {
            "pool": "Complex Process",
            "lanes": [],
            "nodes": [
                {"id": "E01", "type": "startEvent", "name": "Start"},
                {"id": "T01", "type": "manualTask", "name": "Prepare"},
                {"id": "P01", "type": "parallelGateway", "name": "Fork"},
                {"id": "T02", "type": "manualTask", "name": "Path A Step 1"},
                {"id": "G01", "type": "exclusiveGateway", "name": "Decision"},
                {"id": "T03", "type": "manualTask", "name": "Option 1"},
                {"id": "T04", "type": "manualTask", "name": "Option 2"},
                {"id": "G02", "type": "exclusiveGateway", "name": "XOR Merge"},
                {"id": "T05", "type": "manualTask", "name": "Path B"},
                {"id": "P02", "type": "parallelGateway", "name": "Join"},
                {"id": "T06", "type": "manualTask", "name": "Finalize"},
                {"id": "E02", "type": "endEvent", "name": "End"},
            ],
            "flows": [
                {"id": "f1", "from": "E01", "to": "T01"},
                {"id": "f2", "from": "T01", "to": "P01"},
                {"id": "f3", "from": "P01", "to": "T02"},
                {"id": "f4", "from": "T02", "to": "G01"},
                {"id": "f5", "from": "G01", "to": "T03", "cond": "option 1"},
                {"id": "f6", "from": "G01", "to": "T04", "cond": "option 2"},
                {"id": "f7", "from": "T03", "to": "G02"},
                {"id": "f8", "from": "T04", "to": "G02"},
                {"id": "f9", "from": "G02", "to": "P02"},
                {"id": "f10", "from": "P01", "to": "T05"},
                {"id": "f11", "from": "T05", "to": "P02"},
                {"id": "f12", "from": "P02", "to": "T06"},
                {"id": "f13", "from": "T06", "to": "E02"},
            ],
        }
        dsl = convert(data)
        tree = _roundtrip(dsl)
        assert len(list(tree.find_data("and_gw"))) == 1
        assert len(list(tree.find_data("xor_gw"))) == 1

    def test_user_example_logistics(self):
        """The actual JSON example from the user: logistics order processing."""
        data = {
            "pool": "Separação e Roteirização de Pedidos Logísticos",
            "lanes": [
                {"id": "L_Com", "name": "Comercial (Origem dos pedidos)", "refs": []},
                {
                    "id": "L_Coord",
                    "name": "Coordenador Logístico",
                    "refs": ["E01", "T01", "T02", "T03", "T04", "P01", "T09", "T10", "T11", "P02"],
                },
                {
                    "id": "L_Sep",
                    "name": "Separadores",
                    "refs": ["T05", "T06", "G01", "T07", "T08", "T12", "T13"],
                },
                {"id": "L_Mot", "name": "Motoristas", "refs": ["T14", "T15", "E02"]},
            ],
            "nodes": [
                {"id": "E01", "type": "startEvent", "name": "Início", "lane": "L_Coord"},
                {
                    "id": "T01",
                    "type": "receiveTask",
                    "name": "Receber duas vias impressas dos pedidos",
                    "lane": "L_Coord",
                    "doc": "Recebimento físico (papel) das duas vias do pedido.",
                },
                {
                    "id": "T02",
                    "type": "manualTask",
                    "name": "Assinar protocolo de recebimento",
                    "lane": "L_Coord",
                },
                {
                    "id": "T03",
                    "type": "manualTask",
                    "name": "Separar as vias (separação e roteirização)",
                    "lane": "L_Coord",
                },
                {
                    "id": "T04",
                    "type": "manualTask",
                    "name": "Entregar via de separação para Separadores",
                    "lane": "L_Coord",
                },
                {
                    "id": "P01",
                    "type": "parallelGateway",
                    "name": "Fork: Separação e Roteirização em paralelo",
                    "lane": "L_Coord",
                },
                {
                    "id": "T05",
                    "type": "manualTask",
                    "name": "Distribuir notas de pedidos entre Separadores",
                    "lane": "L_Sep",
                    "doc": "Separação cega: o separador não sabe qual motorista levará a carga.",
                },
                {
                    "id": "T06",
                    "type": "manualTask",
                    "name": "Coletar produtos no estoque com carrinho",
                    "lane": "L_Sep",
                },
                {
                    "id": "G01",
                    "type": "exclusiveGateway",
                    "name": "Quantidade excede um carrinho?",
                    "lane": "L_Sep",
                },
                {
                    "id": "T07",
                    "type": "manualTask",
                    "name": "Utilizar múltiplos carrinhos/equipamentos adequados",
                    "lane": "L_Sep",
                },
                {
                    "id": "T08",
                    "type": "manualTask",
                    "name": "Utilizar um carrinho único",
                    "lane": "L_Sep",
                },
                {
                    "id": "T09",
                    "type": "manualTask",
                    "name": "Agrupar vias de roteirização por bairro e destino",
                    "lane": "L_Coord",
                    "doc": "Ex.: Messejana, Maracanaú, Barra do Ceará, Vicente Pinzón, Bom Jardim.",
                },
                {
                    "id": "T10",
                    "type": "manualTask",
                    "name": "Definir rota e motorista responsável",
                    "lane": "L_Coord",
                },
                {
                    "id": "T11",
                    "type": "manualTask",
                    "name": "Entregar vias roteirizadas ao Motorista",
                    "lane": "L_Coord",
                },
                {
                    "id": "T12",
                    "type": "manualTask",
                    "name": "Depositar mercadorias separadas na bancada de conferência",
                    "lane": "L_Sep",
                },
                {
                    "id": "P02",
                    "type": "parallelGateway",
                    "name": "Join: Separação e Roteirização concluídas",
                    "lane": "L_Coord",
                },
                {
                    "id": "T13",
                    "type": "manualTask",
                    "name": "Informar numeração das notas ao Motorista na bancada",
                    "lane": "L_Sep",
                },
                {
                    "id": "T14",
                    "type": "manualTask",
                    "name": "Informar numeração das notas aos Separadores na bancada",
                    "lane": "L_Mot",
                },
                {
                    "id": "T15",
                    "type": "manualTask",
                    "name": "Realizar conferência dos produtos",
                    "lane": "L_Sep",
                },
                {
                    "id": "T16",
                    "type": "manualTask",
                    "name": "Carregar mercadorias no veículo",
                    "lane": "L_Mot",
                },
                {
                    "id": "E02",
                    "type": "endEvent",
                    "name": "Fim (mercadorias carregadas)",
                    "lane": "L_Mot",
                },
            ],
            "flows": [
                {"id": "f1", "from": "E01", "to": "T01"},
                {"id": "f2", "from": "T01", "to": "T02"},
                {"id": "f3", "from": "T02", "to": "T03"},
                {"id": "f4", "from": "T03", "to": "T04"},
                {"id": "f5", "from": "T04", "to": "P01"},
                {"id": "f6", "from": "P01", "to": "T05"},
                {"id": "f7", "from": "T05", "to": "T06"},
                {"id": "f8", "from": "T06", "to": "G01"},
                {
                    "id": "f9",
                    "from": "G01",
                    "to": "T07",
                    "label": "Sim",
                    "cond": "quantidade excede um carrinho",
                },
                {
                    "id": "f10",
                    "from": "G01",
                    "to": "T08",
                    "label": "Não",
                    "cond": "quantidade cabe em um carrinho",
                },
                {"id": "f11", "from": "T07", "to": "T12"},
                {"id": "f12", "from": "T08", "to": "T12"},
                {"id": "f13", "from": "T12", "to": "P02"},
                {"id": "f14", "from": "P01", "to": "T09"},
                {"id": "f15", "from": "T09", "to": "T10"},
                {"id": "f16", "from": "T10", "to": "T11"},
                {"id": "f17", "from": "T11", "to": "P02"},
                {"id": "f18", "from": "P02", "to": "T14"},
                {"id": "f19", "from": "T14", "to": "T15"},
                {"id": "f20", "from": "T15", "to": "T16"},
                {"id": "f21", "from": "T16", "to": "E02"},
            ],
        }
        dsl = convert(data)
        tree = _roundtrip(dsl)

        # Structural assertions
        assert len(list(tree.find_data("and_gw"))) == 1
        assert len(list(tree.find_data("xor_gw"))) == 1
        lanes = list(tree.find_data("lane"))
        # L_Coord has P01 and P02 (gateways) which are filtered → lanes still present
        assert len(lanes) >= 3  # at least 3 non-empty lanes

    def test_typed_events(self):
        data = {
            "pool": "Events Process",
            "lanes": [],
            "nodes": [
                {"id": "E01", "type": "StartMessageEvent", "name": "order-in"},
                {"id": "T01", "type": "task", "name": "Do Work"},
                {"id": "E02", "type": "endEvent", "name": "End"},
            ],
            "flows": [
                {"id": "f1", "from": "E01", "to": "T01"},
                {"id": "f2", "from": "T01", "to": "E02"},
            ],
        }
        dsl = convert(data)
        _roundtrip(dsl)
        assert 'start:message("order-in")' in dsl

    def test_task_doc_property(self):
        data = {
            "pool": "P",
            "lanes": [],
            "nodes": [
                {"id": "E01", "type": "startEvent", "name": "s"},
                {"id": "T01", "type": "task", "name": "Pay", "doc": "See SLA document"},
                {"id": "E02", "type": "endEvent", "name": "e"},
            ],
            "flows": [
                {"id": "f1", "from": "E01", "to": "T01"},
                {"id": "f2", "from": "T01", "to": "E02"},
            ],
        }
        dsl = convert(data)
        _roundtrip(dsl)
        assert '(doc="See SLA document")' in dsl


# ═══════════════════════════════════════════════════════════════════════════════
# Category F — Error handling / edge cases
# ═══════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_orphan_node_warning(self):
        data = {
            "pool": "P",
            "lanes": [],
            "nodes": [
                {"id": "E01", "type": "startEvent", "name": "Start"},
                {"id": "T01", "type": "task", "name": "Connected"},
                {"id": "T02", "type": "task", "name": "Orphan"},
                {"id": "E02", "type": "endEvent", "name": "End"},
            ],
            "flows": [
                {"id": "f1", "from": "E01", "to": "T01"},
                {"id": "f2", "from": "T01", "to": "E02"},
            ],
        }
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            dsl = convert(data)
            orphan_warnings = [x for x in w if "Orphan" in str(x.message)]
            assert len(orphan_warnings) >= 1
        _roundtrip(dsl)

    def test_empty_lanes_handled(self):
        data = {
            "pool": "P",
            "lanes": [{"id": "L1", "name": "Empty Lane", "refs": []}],
            "nodes": [
                {"id": "E01", "type": "startEvent", "name": "s"},
                {"id": "E02", "type": "endEvent", "name": "e"},
            ],
            "flows": [{"id": "f1", "from": "E01", "to": "E02"}],
        }
        dsl = convert(data)
        _roundtrip(dsl)
        assert 'lane "Empty Lane" {}' in dsl

    def test_gateway_refs_filtered_from_lanes(self):
        """Gateways in lane refs should be silently filtered out."""
        data = {
            "pool": "P",
            "lanes": [{"id": "L1", "name": "Sales", "refs": ["E01", "G01", "T01", "E02"]}],
            "nodes": [
                {"id": "E01", "type": "startEvent", "name": "s"},
                {"id": "G01", "type": "exclusiveGateway", "name": "Q"},
                {"id": "T01", "type": "task", "name": "A"},
                {"id": "T02", "type": "task", "name": "B"},
                {"id": "E02", "type": "endEvent", "name": "e"},
            ],
            "flows": [
                {"id": "f1", "from": "E01", "to": "G01"},
                {"id": "f2", "from": "G01", "to": "T01", "cond": "a"},
                {"id": "f3", "from": "G01", "to": "T02", "cond": "b"},
                {"id": "f4", "from": "T01", "to": "E02"},
                {"id": "f5", "from": "T02", "to": "E02"},
            ],
        }
        dsl = convert(data)
        _roundtrip(dsl)
        # Gateway should not be in lane members
        lane_text = dsl.split("lane")[1].split("}")[0] if "lane" in dsl else ""
        assert "xor" not in lane_text
        assert "and" not in lane_text

    def test_default_condition_when_no_cond(self):
        """Edges without condition get [default] in DSL."""
        data = {
            "pool": "P",
            "lanes": [],
            "nodes": [
                {"id": "S", "type": "startEvent", "name": "s"},
                {"id": "G", "type": "exclusiveGateway", "name": "Q"},
                {"id": "A", "type": "task", "name": "A"},
                {"id": "B", "type": "task", "name": "B"},
                {"id": "E", "type": "endEvent", "name": "e"},
            ],
            "flows": [
                {"id": "f1", "from": "S", "to": "G"},
                {"id": "f2", "from": "G", "to": "A", "cond": "condition"},
                {"id": "f3", "from": "G", "to": "B"},
                {"id": "f4", "from": "A", "to": "E"},
                {"id": "f5", "from": "B", "to": "E"},
            ],
        }
        dsl = convert(data)
        _roundtrip(dsl)
        assert "[default]" in dsl
        assert "[condition]" in dsl

    def test_start_end_only(self):
        data = {
            "pool": "Minimal",
            "lanes": [],
            "nodes": [
                {"id": "S", "type": "startEvent", "name": "s"},
                {"id": "E", "type": "endEvent", "name": "e"},
            ],
            "flows": [{"id": "f1", "from": "S", "to": "E"}],
        }
        dsl = convert(data)
        _roundtrip(dsl)
        assert "start" in dsl
        assert "end" in dsl

    def test_unknown_node_type_maps_to_task(self):
        data = {
            "pool": "P",
            "lanes": [],
            "nodes": [
                {"id": "S", "type": "startEvent", "name": "s"},
                {"id": "T", "type": "bizarroTask", "name": "Strange"},
                {"id": "E", "type": "endEvent", "name": "e"},
            ],
            "flows": [
                {"id": "f1", "from": "S", "to": "T"},
                {"id": "f2", "from": "T", "to": "E"},
            ],
        }
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            dsl = convert(data)
        _roundtrip(dsl)
        assert 'task "Strange"' in dsl

    def test_label_as_fallback_condition(self):
        """If no 'cond' field, use 'label' as condition text."""
        data = {
            "pool": "P",
            "lanes": [],
            "nodes": [
                {"id": "S", "type": "startEvent", "name": "s"},
                {"id": "G", "type": "exclusiveGateway", "name": "Q"},
                {"id": "A", "type": "task", "name": "A"},
                {"id": "B", "type": "task", "name": "B"},
                {"id": "E", "type": "endEvent", "name": "e"},
            ],
            "flows": [
                {"id": "f1", "from": "S", "to": "G"},
                {"id": "f2", "from": "G", "to": "A", "label": "Yes"},
                {"id": "f3", "from": "G", "to": "B", "label": "No"},
                {"id": "f4", "from": "A", "to": "E"},
                {"id": "f5", "from": "B", "to": "E"},
            ],
        }
        dsl = convert(data)
        _roundtrip(dsl)
        assert "[Yes]" in dsl
        assert "[No]" in dsl
