"""Execução do juiz: alvos do Zenodo, retomada e falhas que ficam pendentes."""

import pytest

from src.data.db import Database
from src.data.migrations.create_judge_eval import ensure_schema
from src.evaluation import run_judge as rj

XML = (
    '<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL" id="d"><process id="p">'
    '<startEvent id="s"/><task id="t" name="A"/><endEvent id="e"/>'
    '<sequenceFlow id="1" sourceRef="s" targetRef="t"/>'
    '<sequenceFlow id="2" sourceRef="t" targetRef="e"/></process></definitions>'
)


@pytest.fixture
def zenodo(tmp_path):
    (tmp_path / "E_j01.txt").write_text("Do A.")
    pasta = tmp_path / "E_j01"
    pasta.mkdir()
    for nome, nota in [("0", "5"), ("1", "2.5"), ("2", None)]:
        (pasta / f"{nome}.bpmn2.xml").write_text(XML)
        if nota is not None:
            (pasta / f"{nome}.quality.txt").write_text(nota)
    return tmp_path


@pytest.fixture
def banco(tmp_path):
    db = Database(tmp_path / "t.db")
    ensure_schema(db._conn)
    yield db
    db.close()


def test_only_models_with_expert_score_are_targets(zenodo):
    alvos = rj.zenodo_targets(zenodo)
    assert [(a["target"], a["expert_score"]) for a in alvos] == [
        ("zenodo:E_j01/0", 5.0),
        ("zenodo:E_j01/1", 2.5),
    ]


def test_execute_is_resumable_and_failures_stay_pending(zenodo, banco, monkeypatch):
    chamadas = []

    def falso(descricao, xml, *, api_key, seed):
        chamadas.append(seed)
        if seed == 2:
            raise RuntimeError("timeout")
        problemas = {c: [] for c in ("tasks", "decisions")}
        return {"score": 4.0, "problems": problemas, "prompt_sha": "sha", "usage": {}}

    monkeypatch.setattr(rj, "judge", falso)
    alvos = rj.zenodo_targets(zenodo)

    resumo = rj.execute(banco, rj.pending(banco, alvos, "sha"), "k", workers=2)
    assert resumo == {"ok": 4, "falhas": 2}

    restantes = rj.pending(banco, alvos, "sha")
    assert sorted((a["target"], rep) for a, rep in restantes) == [
        ("zenodo:E_j01/0", 2),
        ("zenodo:E_j01/1", 2),
    ]
    assert rj.pending(banco, alvos, "outro-prompt") and len(chamadas) == 6
