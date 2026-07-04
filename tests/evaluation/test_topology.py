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
