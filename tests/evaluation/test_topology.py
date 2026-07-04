"""Tests for Eixo 2 — topological equivalence JSON ↔ XML."""

from src.data.manipulation.deterministic.json_to_dsl import convert
from src.evaluation.topology import compare
from src.transpiler import transpile


def _roundtrip(data: dict) -> dict:
    """JSON -> DSL -> XML -> compare(JSON, XML)."""
    return compare(data, transpile(convert(data)))


def test_linear_process_is_topologically_equivalent():
    res = _roundtrip(
        {
            "pool": "Linear",
            "nodes": [
                {"id": "S", "type": "startEvent", "name": "Start"},
                {"id": "A", "type": "task", "name": "Do A"},
                {"id": "B", "type": "task", "name": "Do B"},
                {"id": "E", "type": "endEvent", "name": "End"},
            ],
            "flows": [{"from": "S", "to": "A"}, {"from": "A", "to": "B"}, {"from": "B", "to": "E"}],
        }
    )
    assert res["nodes_match"]
    assert res["df_exact"]
    assert res["df_f1"] == 1.0


def test_fork_join_diamond_is_topologically_equivalent():
    res = _roundtrip(
        {
            "pool": "Diamond",
            "nodes": [
                {"id": "S", "type": "startEvent", "name": ""},
                {"id": "G", "type": "exclusiveGateway", "name": "Decide"},
                {"id": "A", "type": "task", "name": "Approve"},
                {"id": "R", "type": "task", "name": "Reject"},
                {"id": "M", "type": "task", "name": "Notify"},
                {"id": "E", "type": "endEvent", "name": ""},
            ],
            "flows": [
                {"from": "S", "to": "G"},
                {"from": "G", "to": "A", "cond": "yes"},
                {"from": "G", "to": "R", "cond": "no"},
                {"from": "A", "to": "M"},
                {"from": "R", "to": "M"},
                {"from": "M", "to": "E"},
            ],
        }
    )
    assert res["nodes_match"]
    assert res["df_exact"]
    # both branches must reach Notify (convergence preserved)
    assert res["df_f1"] == 1.0


def test_quoted_task_name_roundtrips_topology():
    # Regressão: nomes com aspas escapavam (\\") no XML e quebravam a igualdade
    # de rótulos. unquote agora desescapa, então a topologia bate.
    res = _roundtrip(
        {
            "pool": "Quotes",
            "nodes": [
                {"id": "S", "type": "startEvent", "name": ""},
                {"id": "A", "type": "task", "name": 'Clicar em "Payments"'},
                {"id": "B", "type": "task", "name": "Exportar relatório"},
                {"id": "E", "type": "endEvent", "name": ""},
            ],
            "flows": [{"from": "S", "to": "A"}, {"from": "A", "to": "B"}, {"from": "B", "to": "E"}],
        }
    )
    assert res["df_exact"]
    assert res["df_f1"] == 1.0


def test_skip_branch_to_join_emitted_inside_sibling_branch():
    # Regressão (bug das arestas de convergência, 130 df_exact=0): o branch de
    # skip aponta para um join que acaba emitido DENTRO do branch irmão (bloco
    # aninhado sem join próprio). Sem #ref explícito, a aresta G1->C evaporava
    # porque o bloco não tem continuação `-> join`.
    res = _roundtrip(
        {
            "pool": "NonSESE skip",
            "nodes": [
                {"id": "S", "type": "startEvent", "name": ""},
                {"id": "P", "type": "task", "name": "Prepare"},
                {"id": "G1", "type": "exclusiveGateway", "name": "Validate?"},
                {"id": "V", "type": "task", "name": "Do validation"},
                {"id": "G2", "type": "exclusiveGateway", "name": "Stop?"},
                {"id": "E1", "type": "endEvent", "name": "Stopped"},
                {"id": "C", "type": "task", "name": "Confirm budget"},
                {"id": "D", "type": "task", "name": "Proceed"},
                {"id": "E2", "type": "endEvent", "name": "Done"},
            ],
            "flows": [
                {"from": "S", "to": "P"},
                {"from": "P", "to": "G1"},
                {"from": "G1", "to": "V", "cond": "yes"},
                {"from": "G1", "to": "C", "cond": "skip"},
                {"from": "V", "to": "G2"},
                {"from": "G2", "to": "E1", "cond": "stop"},
                {"from": "G2", "to": "C", "cond": "continue"},
                {"from": "C", "to": "D"},
                {"from": "D", "to": "E2"},
            ],
        }
    )
    assert res["nodes_match"]
    assert res["df_missing"] == {}
    assert res["df_exact"]


def test_branch_tail_to_join_emitted_inside_sibling_branch():
    # Mesma regressão, variante sem skip: o branch [a] emite uma cauda (X) e
    # para na fronteira; a aresta X->C precisa de #ref quando o join não vira
    # continuação do bloco. Valida a decisão pós-loop (branch [a] roda ANTES
    # de C ser emitido pelo branch [b]).
    res = _roundtrip(
        {
            "pool": "NonSESE tail",
            "nodes": [
                {"id": "S", "type": "startEvent", "name": ""},
                {"id": "G1", "type": "exclusiveGateway", "name": "Route"},
                {"id": "X", "type": "task", "name": "Fast path"},
                {"id": "Y", "type": "task", "name": "Slow path"},
                {"id": "G2", "type": "exclusiveGateway", "name": "Continue?"},
                {"id": "E1", "type": "endEvent", "name": "Aborted"},
                {"id": "C", "type": "task", "name": "Converge"},
                {"id": "D", "type": "task", "name": "Wrap up"},
                {"id": "E2", "type": "endEvent", "name": "Done"},
            ],
            "flows": [
                {"from": "S", "to": "G1"},
                {"from": "G1", "to": "X", "cond": "a"},
                {"from": "G1", "to": "Y", "cond": "b"},
                {"from": "X", "to": "C"},
                {"from": "Y", "to": "G2"},
                {"from": "G2", "to": "C", "cond": "p"},
                {"from": "G2", "to": "E1", "cond": "q"},
                {"from": "C", "to": "D"},
                {"from": "D", "to": "E2"},
            ],
        }
    )
    assert res["nodes_match"]
    assert res["df_missing"] == {}
    assert res["df_exact"]
