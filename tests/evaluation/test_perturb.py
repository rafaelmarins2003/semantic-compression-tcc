"""Cada operador produz o defeito que diz produzir, e só ele."""

import copy
import random

import pytest

from src.evaluation import perturb as pt
from src.evaluation.render import render
from src.evaluation.run_perturbation import mutant_cases
from src.transpiler.xml import transpile
from src.transpiler.xsd import validate_bpmn_xsd

DSL = """process "P" { @lane "Clerk" {
  start -> task "Receive order" -> task "Check stock" -> xor "In stock?" {
    [yes] -> task "Pack goods"
    [no] -> task "Reorder goods"
  } -> and { task "Send invoice"; task "Ship goods" } -> end "Done"
} }"""
TEXT = "Receive the order, check stock, pack or reorder, then invoice and ship."


@pytest.fixture
def g():
    return pt.graph(transpile(DSL))


def _nomes(g):
    return sorted(n["name"] for n in g["nodes"].values() if n["kind"] == "activity")


def test_roundtrip_keeps_process_and_is_valid(g):
    xml = pt.to_xml(g)
    assert render(xml) == render(transpile(DSL))
    assert validate_bpmn_xsd(xml) == []


def test_drop_task_removes_one_and_reconnects(g):
    antes = _nomes(g)
    assert pt.mutate(g, "drop_task", random.Random(0), TEXT)
    assert len(_nomes(g)) == len(antes) - 1
    assert validate_bpmn_xsd(pt.to_xml(g)) == []


def test_add_task_uses_label_absent_from_text(g):
    assert pt.mutate(g, "add_task", random.Random(0), TEXT)
    novo = set(_nomes(g)) - set(_nomes(pt.graph(transpile(DSL))))
    assert len(novo) == 1 and novo <= set(pt.INVENTED)


def test_parallel_to_exclusive_and_swap_branches(g):
    h = copy.deepcopy(g)
    assert pt.mutate(h, "parallel_to_exclusive", random.Random(0), TEXT)
    assert "parallel" not in render(pt.to_xml(h))
    assert pt.mutate(g, "swap_branches", random.Random(0), TEXT)
    sim = next(b for a, b, cond in g["flows"] if cond == "yes")
    assert g["nodes"][sim]["name"] == "Reorder goods"


def test_paraphrase_changes_only_labels(g):
    mapa = {r: r.upper() for r in pt.labels(g)}
    p = pt.paraphrased(g, mapa)
    assert p["flows"] == g["flows"]
    assert _nomes(p) == sorted(n.upper() for n in _nomes(g))


def test_mutant_cases_never_include_a_no_op():
    casos = mutant_cases("x", transpile(DSL), TEXT)
    intacto = render(casos[0]["xml"])
    assert casos[0]["kind"] == "intact"
    assert all(render(c["xml"]) != intacto for c in casos[1:])
    assert {c["kind"] for c in casos} >= {"drop_task", "add_task", "triple"}
