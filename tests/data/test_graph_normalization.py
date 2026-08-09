"""Normalização de splits implícitos em `load_llm`.

O GLM 5.2 produz nós comuns com mais de uma saída (split não controlado). Sem
normalizar, `json_to_dsl` emitia um sucessor e descartava os demais — 20 amostras
perderam 77 arestas antes desta correção.
"""

from __future__ import annotations

from src.data.deterministic.graph import load_llm
from src.data.deterministic.json_to_dsl import convert


def _payload(flows):
    return {
        "pool": "P",
        "lanes": [],
        "nodes": [
            {"id": "E01", "type": "startEvent", "name": "Start"},
            {"id": "T01", "type": "userTask", "name": "Split Here"},
            {"id": "T02", "type": "userTask", "name": "Branch A"},
            {"id": "T03", "type": "userTask", "name": "Branch B"},
            {"id": "E02", "type": "endEvent", "name": "End"},
        ],
        "flows": flows,
    }


BASE_FLOWS = [
    {"id": "f1", "from": "E01", "to": "T01"},
    {"id": "f4", "from": "T02", "to": "E02"},
    {"id": "f5", "from": "T03", "to": "E02"},
]


def test_unconditional_implicit_split_becomes_parallel_gateway():
    graph = load_llm(
        _payload(
            BASE_FLOWS
            + [{"id": "f2", "from": "T01", "to": "T02"}, {"id": "f3", "from": "T01", "to": "T03"}]
        )
    )

    assert graph.succs["T01"] == ["T01_split"]
    assert graph.nodes["T01_split"].type == "parallelGateway"
    assert sorted(graph.succs["T01_split"]) == ["T02", "T03"]


def test_fully_conditional_implicit_split_becomes_exclusive_gateway():
    graph = load_llm(
        _payload(
            BASE_FLOWS
            + [
                {"id": "f2", "from": "T01", "to": "T02", "cond": "yes", "label": "Yes"},
                {"id": "f3", "from": "T01", "to": "T03", "cond": "no", "label": "No"},
            ]
        )
    )

    assert graph.nodes["T01_split"].type == "exclusiveGateway"


def test_single_successor_is_left_untouched():
    graph = load_llm(_payload(BASE_FLOWS + [{"id": "f2", "from": "T01", "to": "T02"}]))

    assert graph.succs["T01"] == ["T02"]
    assert not any(nid.endswith("_split") for nid in graph.nodes)


def test_explicit_gateway_is_not_double_wrapped():
    data = _payload(
        BASE_FLOWS
        + [{"id": "f2", "from": "G01", "to": "T02"}, {"id": "f3", "from": "G01", "to": "T03"}]
    )
    data["nodes"].append({"id": "G01", "type": "exclusiveGateway", "name": "Choice?"})
    data["flows"].append({"id": "f6", "from": "T01", "to": "G01"})

    graph = load_llm(data)

    assert not any(nid.endswith("_split") for nid in graph.nodes)
    assert sorted(graph.succs["G01"]) == ["T02", "T03"]


def test_both_branches_survive_conversion_to_dsl():
    """A regressão real: antes, um dos branches sumia da DSL."""
    dsl = convert(
        _payload(
            BASE_FLOWS
            + [{"id": "f2", "from": "T01", "to": "T02"}, {"id": "f3", "from": "T01", "to": "T03"}]
        )
    )

    assert "Branch A" in dsl
    assert "Branch B" in dsl


def test_synthetic_gateway_id_does_not_clobber_a_real_node():
    """Achado da revisão: `X_split` real era sobrescrito pelo gateway de `X`."""
    data = _payload(
        BASE_FLOWS
        + [{"id": "f2", "from": "T01", "to": "T02"}, {"id": "f3", "from": "T01", "to": "T03"}]
    )
    data["nodes"].append({"id": "T01_split", "type": "userTask", "name": "REAL NODE"})
    data["flows"].append({"id": "f6", "from": "T02", "to": "T01_split"})

    graph = load_llm(data)

    assert graph.nodes["T01_split"].name == "REAL NODE"
    assert graph.nodes["T01_split"].type == "userTask"
    gateway_id = graph.succs["T01"][0]
    assert gateway_id != "T01_split"
    assert graph.nodes[gateway_id].type == "parallelGateway"


def test_label_alone_does_not_imply_exclusive_choice():
    """Achado da revisão: `label` é legenda, não evidência de escolha."""
    graph = load_llm(
        _payload(
            BASE_FLOWS
            + [
                {"id": "f2", "from": "T01", "to": "T02", "label": "to warehouse"},
                {"id": "f3", "from": "T01", "to": "T03", "label": "to billing"},
            ]
        )
    )

    assert graph.nodes["T01_split"].type == "parallelGateway"
