"""Tests for JSON to BPMN-DSL v2 conversion."""

import warnings

from src.data.manipulation.deterministic.graph import (
    Edge,
    Lane,
    Node,
    ProcessGraph,
    build_adjacency,
    classify_gateway,
    find_orphans,
    find_start,
    load_llm,
)
from src.data.manipulation.deterministic.json_to_dsl import convert, find_join
from src.dsl.parser import parse


def _make_graph(nodes_list, edges_list, lanes=None, name="Test Process") -> ProcessGraph:
    nodes = {}
    for raw_node in nodes_list:
        if len(raw_node) == 3:
            node_id, node_type, node_name = raw_node
            nodes[node_id] = Node(node_id, node_type, node_name)
        else:
            node_id, node_type, node_name, doc = raw_node
            nodes[node_id] = Node(node_id, node_type, node_name, doc)

    edges = []
    for idx, raw_edge in enumerate(edges_list):
        if len(raw_edge) == 2:
            source, target = raw_edge
            edges.append(Edge(f"f{idx}", source, target))
        else:
            source, target, condition = raw_edge
            edges.append(Edge(f"f{idx}", source, target, condition=condition))

    succs, preds, edge_map = build_adjacency(nodes, edges)
    return ProcessGraph(
        name=name,
        nodes=nodes,
        edges=edges,
        succs=succs,
        preds=preds,
        edge_map=edge_map,
        lanes=lanes or [],
        start_id=find_start(nodes, preds),
    )


def _assert_parseable(dsl_text: str) -> None:
    parse(dsl_text)


def test_build_adjacency_skips_unknown_source_with_warning():
    nodes = {"B": Node("B", "task", "B")}
    edges = [Edge("f1", "MISSING", "B")]

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        succs, preds, edge_map = build_adjacency(nodes, edges)

    assert "unknown source" in str(caught[0].message)
    assert succs == {}
    assert preds == {}
    assert edge_map == {}


def test_find_start_prefers_start_event_then_falls_back_to_in_degree_zero():
    nodes = {
        "S": Node("S", "startEvent", "Start"),
        "T": Node("T", "task", "Task"),
    }
    assert find_start(nodes, {"T": ["S"]}) == "S"

    fallback_nodes = {
        "A": Node("A", "task", "First"),
        "B": Node("B", "task", "Second"),
    }
    assert find_start(fallback_nodes, {"B": ["A"]}) == "A"


def test_classify_gateway_by_degrees():
    assert classify_gateway("G", {"G": ["A", "B"]}, {"G": ["S"]}) == "fork"
    assert classify_gateway("G", {"G": ["E"]}, {"G": ["A", "B"]}) == "join"
    assert classify_gateway("G", {"G": ["A", "B"]}, {"G": ["X", "Y"]}) == "both"
    assert classify_gateway("G", {"G": ["E"]}, {"G": ["S"]}) == "none"


def test_find_orphans_returns_unreachable_nodes():
    nodes = {
        "S": Node("S", "startEvent", "Start"),
        "T": Node("T", "task", "Task"),
        "O": Node("O", "task", "Orphan"),
    }

    assert find_orphans(nodes, "S", {"S": ["T"]}) == {"O"}


def test_find_join_detects_nearest_common_node():
    graph = _make_graph(
        [
            ("S", "startEvent", "Start"),
            ("G", "exclusiveGateway", "Decision"),
            ("A", "task", "A"),
            ("B", "task", "B"),
            ("M", "task", "Merge"),
            ("E", "endEvent", "End"),
        ],
        [
            ("S", "G"),
            ("G", "A", "yes"),
            ("G", "B", "no"),
            ("A", "M"),
            ("B", "M"),
            ("M", "E"),
        ],
    )

    assert find_join(graph, "G") == "M"


def test_load_llm_preserves_event_based_gateway_type():
    graph = load_llm(
        {
            "pool": "P",
            "nodes": [
                {"id": "S", "type": "startEvent", "name": ""},
                {"id": "G", "type": "eventBasedGateway", "name": "Wait"},
            ],
            "flows": [{"from": "S", "to": "G"}],
        }
    )

    assert graph.nodes["G"].type == "eventBasedGateway"


def test_load_llm_maps_raw_node_lane_id_to_lane_name():
    graph = load_llm(
        {
            "pool": "P",
            "lanes": [{"id": "L_MAIN", "name": "Main", "refs": ["S"]}],
            "nodes": [
                {"id": "S", "type": "startEvent", "name": "", "lane": "L_MAIN"},
                {"id": "G", "type": "exclusiveGateway", "name": "Decision", "lane": "L_MAIN"},
            ],
            "flows": [{"from": "S", "to": "G"}],
        }
    )

    assert graph.nodes["G"].lane == "Main"


def test_convert_generic_intermediate_catch_event_preserves_event_semantics():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        dsl_text = convert(
            {
                "pool": "Wait",
                "nodes": [
                    {"id": "S", "type": "startEvent", "name": ""},
                    {
                        "id": "IT01",
                        "type": "intermediateCatchEvent",
                        "name": "Aguardar conclusão",
                    },
                    {"id": "E", "type": "endEvent", "name": ""},
                ],
                "flows": [{"from": "S", "to": "IT01"}, {"from": "IT01", "to": "E"}],
            }
        )

    _assert_parseable(dsl_text)
    assert 'catch:none "Aguardar conclusão"' in dsl_text
    assert 'task "Aguardar conclusão"' not in dsl_text
    assert not any("Unknown node type" in str(item.message) for item in caught)


def test_convert_simple_process_preserves_event_names():
    dsl_text = convert(
        {
            "pool": "Order",
            "nodes": [
                {"id": "S", "type": "startEvent", "name": "Created"},
                {"id": "T", "type": "userTask", "name": "Review"},
                {"id": "E", "type": "endEvent", "name": "Closed"},
            ],
            "flows": [{"from": "S", "to": "T"}, {"from": "T", "to": "E"}],
        }
    )

    _assert_parseable(dsl_text)
    assert 'start "Created"' in dsl_text
    assert 'user "Review"' in dsl_text
    assert 'end "Closed"' in dsl_text


def test_convert_typed_events_and_task_doc_props():
    dsl_text = convert(
        {
            "pool": "Typed",
            "nodes": [
                {"id": "S", "type": "StartMessageEvent", "name": "Request"},
                {"id": "T", "type": "serviceTask", "name": "Process", "doc": "SLA 1h"},
                {"id": "M", "type": "IntermediateMessageEventThrowing", "name": "Done"},
                {"id": "E", "type": "EndErrorEvent", "name": "Failed"},
            ],
            "flows": [
                {"from": "S", "to": "T"},
                {"from": "T", "to": "M"},
                {"from": "M", "to": "E"},
            ],
        }
    )

    _assert_parseable(dsl_text)
    assert 'start:message "Request"' in dsl_text
    assert 'service "Process" (doc="SLA 1h")' in dsl_text
    assert 'throw:message "Done"' in dsl_text
    assert 'end:error "Failed"' in dsl_text


def test_convert_empty_branch_uses_v2_empty_branch_syntax():
    dsl_text = convert(
        {
            "pool": "Decision",
            "nodes": [
                {"id": "S", "type": "startEvent", "name": ""},
                {"id": "G", "type": "exclusiveGateway", "name": "Approved?"},
                {"id": "A", "type": "task", "name": "Approve"},
                {"id": "M", "type": "task", "name": "Notify"},
                {"id": "E", "type": "endEvent", "name": ""},
            ],
            "flows": [
                {"from": "S", "to": "G"},
                {"from": "G", "to": "A", "condition": "yes"},
                {"from": "G", "to": "M", "condition": "skip"},
                {"from": "A", "to": "M"},
                {"from": "M", "to": "E"},
            ],
        }
    )

    _assert_parseable(dsl_text)
    assert "[skip] -> ()" in dsl_text
    assert 'task "empty"' not in dsl_text


def test_convert_loop_uses_stable_cname_ref_not_name_ref():
    dsl_text = convert(
        {
            "pool": "Loop",
            "nodes": [
                {"id": "S", "type": "startEvent", "name": ""},
                {"id": "T", "type": "task", "name": "Work"},
                {"id": "G", "type": "exclusiveGateway", "name": "Again?"},
                {"id": "E", "type": "endEvent", "name": ""},
            ],
            "flows": [
                {"from": "S", "to": "T"},
                {"from": "T", "to": "G"},
                {"from": "G", "to": "T", "condition": "retry"},
                {"from": "G", "to": "E", "condition": "done"},
            ],
        }
    )

    _assert_parseable(dsl_text)
    assert 'task "Work" #t' in dsl_text
    assert "[retry] -> #t" in dsl_text
    assert '#"Work"' not in dsl_text


def test_convert_nested_gateway_stops_at_outer_branch_boundary():
    dsl_text = convert(
        {
            "pool": "Nested Join",
            "nodes": [
                {"id": "S", "type": "startEvent", "name": ""},
                {"id": "G1", "type": "exclusiveGateway", "name": "Outer"},
                {"id": "A", "type": "task", "name": "A"},
                {"id": "G2", "type": "exclusiveGateway", "name": "Inner"},
                {"id": "B", "type": "task", "name": "B"},
                {"id": "C", "type": "task", "name": "C"},
                {"id": "J", "type": "exclusiveGateway", "name": "Join"},
                {"id": "D", "type": "task", "name": "After"},
                {"id": "E", "type": "endEvent", "name": ""},
            ],
            "flows": [
                {"from": "S", "to": "G1"},
                {"from": "G1", "to": "A", "cond": "left"},
                {"from": "G1", "to": "G2", "cond": "right"},
                {"from": "A", "to": "J"},
                {"from": "G2", "to": "B", "cond": "b"},
                {"from": "G2", "to": "C", "cond": "c"},
                {"from": "B", "to": "J"},
                {"from": "C", "to": "J"},
                {"from": "J", "to": "D"},
                {"from": "D", "to": "E"},
            ],
        }
    )

    _assert_parseable(dsl_text)
    assert '} ->\n  task "After"' in dsl_text
    assert "#after" not in dsl_text


def test_convert_skips_degenerate_gateway_markers():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        dsl_text = convert(
            {
                "pool": "Degenerate Gateways",
                "nodes": [
                    {"id": "S", "type": "startEvent", "name": ""},
                    {"id": "P1", "type": "parallelGateway", "name": "Fork marker"},
                    {"id": "T", "type": "userTask", "name": "Work"},
                    {"id": "P2", "type": "parallelGateway", "name": "Join marker"},
                    {"id": "E", "type": "endEvent", "name": ""},
                ],
                "flows": [
                    {"from": "S", "to": "P1"},
                    {"from": "P1", "to": "T"},
                    {"from": "T", "to": "P2"},
                    {"from": "P2", "to": "E"},
                ],
            }
        )

    _assert_parseable(dsl_text)
    assert 'task "Fork marker"' not in dsl_text
    assert 'task "Join marker"' not in dsl_text
    assert 'user "Work"' in dsl_text
    assert not any("_emit_element: unhandled type" in str(item.message) for item in caught)


def test_convert_wrapped_process_collection_preserves_all_processes():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        dsl_text = convert(
            {
                "processes": [
                    {
                        "pool": "First",
                        "nodes": [
                            {"id": "S1", "type": "startEvent", "name": ""},
                            {"id": "E1", "type": "endEvent", "name": ""},
                        ],
                        "flows": [{"from": "S1", "to": "E1"}],
                    },
                    {
                        "pool": "Second",
                        "nodes": [
                            {"id": "S2", "type": "startEvent", "name": ""},
                            {"id": "T2", "type": "task", "name": "Do second"},
                            {"id": "E2", "type": "endEvent", "name": ""},
                        ],
                        "flows": [{"from": "S2", "to": "T2"}, {"from": "T2", "to": "E2"}],
                    },
                ]
            }
        )

    _assert_parseable(dsl_text)
    assert dsl_text.count('process "') == 2
    assert 'process "First"' in dsl_text
    assert 'process "Second"' in dsl_text
    assert 'task "Do second"' in dsl_text
    assert not any("Unwrapped" in str(item.message) for item in caught)


def test_convert_disconnected_components_emit_separate_processes():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        dsl_text = convert(
            {
                "pool": "Disconnected",
                "nodes": [
                    {"id": "S", "type": "startEvent", "name": "Main start"},
                    {"id": "T", "type": "task", "name": "Main work"},
                    {"id": "E", "type": "endEvent", "name": "Main end"},
                    {"id": "IT", "type": "intermediateCatchEvent", "name": "Wait"},
                    {"id": "T2", "type": "task", "name": "Secondary work"},
                    {"id": "E2", "type": "endEvent", "name": "Secondary end"},
                ],
                "flows": [
                    {"from": "S", "to": "T"},
                    {"from": "T", "to": "E"},
                    {"from": "IT", "to": "T2"},
                    {"from": "T2", "to": "E2"},
                ],
            }
        )

    _assert_parseable(dsl_text)
    assert 'process "Disconnected"' in dsl_text
    assert 'process "Disconnected - componente 2"' in dsl_text
    assert 'catch:none "Wait"' in dsl_text
    assert 'task "Secondary work"' in dsl_text
    assert not any("Orphan node" in str(item.message) for item in caught)


def test_convert_lanes_emit_scoped_lane_blocks():
    graph = _make_graph(
        [
            ("S", "startEvent", ""),
            ("A", "task", "Receive"),
            ("B", "serviceTask", "Process"),
            ("E", "endEvent", ""),
        ],
        [("S", "A"), ("A", "B"), ("B", "E")],
        lanes=[
            Lane("Sales", ["S", "A"]),
            Lane("Operations", ["B", "E"]),
        ],
        name="Lane Process",
    )

    dsl_text = convert(
        {
            "pool": graph.name,
            "lanes": [
                {"name": lane.name, "refs": lane.node_ids}
                for lane in graph.lanes
            ],
            "nodes": [
                {"id": node.id, "type": node.type, "name": node.name}
                for node in graph.nodes.values()
            ],
            "flows": [
                {"from": edge.source, "to": edge.target}
                for edge in graph.edges
            ],
        }
    )

    _assert_parseable(dsl_text)
    assert '@lane "Sales"' in dsl_text
    assert '@lane "Operations"' in dsl_text
    assert "\n  lane " not in dsl_text


def test_convert_gateway_lane_prevents_redundant_lane_props():
    dsl_text = convert(
        {
            "pool": "Lanes",
            "lanes": [
                {"id": "L1", "name": "Main", "refs": ["S", "T1", "T2", "E"]},
                {"id": "L2", "name": "Other", "refs": ["O"]},
            ],
            "nodes": [
                {"id": "S", "type": "startEvent", "name": "", "lane": "L1"},
                {"id": "G", "type": "exclusiveGateway", "name": "Decision", "lane": "L1"},
                {"id": "T1", "type": "task", "name": "Same", "lane": "L1"},
                {"id": "O", "type": "task", "name": "Other", "lane": "L2"},
                {"id": "T2", "type": "task", "name": "After", "lane": "L1"},
                {"id": "E", "type": "endEvent", "name": "", "lane": "L1"},
            ],
            "flows": [
                {"from": "S", "to": "G"},
                {"from": "G", "to": "T1", "cond": "same"},
                {"from": "G", "to": "O", "cond": "other"},
                {"from": "T1", "to": "T2"},
                {"from": "O", "to": "T2"},
                {"from": "T2", "to": "E"},
            ],
        }
    )

    _assert_parseable(dsl_text)
    assert 'task "Same" (lane="Main")' not in dsl_text
    assert 'task "Other" (lane="Other")' in dsl_text


def test_convert_event_gateway_uses_event_branch_specs_parseable_by_v2():
    dsl_text = convert(
        {
            "pool": "Wait",
            "nodes": [
                {"id": "S", "type": "startEvent", "name": ""},
                {"id": "G", "type": "eventBasedGateway", "name": "Wait for result"},
                {"id": "M", "type": "IntermediateMessageEventCatching", "name": "Approved"},
                {"id": "T", "type": "IntermediateTimerEvent", "name": "PT30M"},
                {"id": "E1", "type": "endEvent", "name": "Approved"},
                {"id": "E2", "type": "endEvent", "name": "Timeout"},
            ],
            "flows": [
                {"from": "S", "to": "G"},
                {"from": "G", "to": "M"},
                {"from": "G", "to": "T"},
                {"from": "M", "to": "E1"},
                {"from": "T", "to": "E2"},
            ],
        }
    )

    _assert_parseable(dsl_text)
    assert 'event "Wait for result"' in dsl_text
    assert '[:message("Approved")]' in dsl_text
    assert '[:timer("PT30M")]' in dsl_text


def test_unknown_node_type_falls_back_to_task_with_warning():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        dsl_text = convert(
            {
                "pool": "Unknown",
                "nodes": [
                    {"id": "S", "type": "startEvent", "name": ""},
                    {"id": "X", "type": "customTask", "name": "Custom"},
                    {"id": "E", "type": "endEvent", "name": ""},
                ],
                "flows": [{"from": "S", "to": "X"}, {"from": "X", "to": "E"}],
            }
        )

    _assert_parseable(dsl_text)
    assert 'task "Custom"' in dsl_text
    assert any("Unknown node type" in str(item.message) for item in caught)
