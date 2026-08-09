"""Critérios de aceitação do gold do PMo (spec 004 §5, AC-1 a AC-3).

Estes testes leem `data/raw/pmo/` e o banco real: são de integração, não de
unidade. Se o gold não estiver carregado, pulam em vez de falhar, para não
quebrar a suíte em um clone sem o dataset.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.data.db import _DB_PATH, Database
from src.data.ingestion.import_gold_pmo import GOLD_DIR, collect, gold_path_for
from src.evaluation.topology import compare_xml, xml_direct_follows

EXCLUDED = {22, 24}
ACTIVE = [n for n in range(1, 56) if n not in EXCLUDED]


@pytest.fixture(scope="module")
def gold_rows():
    if not GOLD_DIR.exists():
        pytest.skip("dataset bruto do PMo não disponível")
    if not _DB_PATH.exists():
        pytest.skip("banco de pesquisa não disponível")
    with Database(read_only=True) as db:
        if not db.query("SELECT 1 FROM samples WHERE source='pmo' LIMIT 1"):
            pytest.skip("amostras do PMo não estão no banco")
        rows, problems = collect(db)
    assert problems == [], f"problemas ao coletar o gold: {problems}"
    return rows


def test_ac1_gold_loaded_for_active_pmo(gold_rows):
    """53 ativos entram; os 2 degradados (22 e 24) não."""
    assert len(gold_rows) == len(ACTIVE) == 53

    arquivos = {row["source_file"] for row in gold_rows}
    for excluded in EXCLUDED:
        assert f"{excluded:02d}.bpmn" not in arquivos


def test_ac2_gold_parses_with_topology(gold_rows):
    """Todo gold parseia sem exceção e tem ao menos uma aresta direct-follows."""
    for row in gold_rows:
        df, nodes = xml_direct_follows(row["gold_xml"])
        assert sum(df.values()) >= 1, f"{row['sample_id']} sem arestas"
        assert sum(nodes.values()) >= 1, f"{row['sample_id']} sem nós emitíveis"


def test_ac3_gold_self_comparison_is_perfect(gold_rows):
    """`compare_xml(gold, gold)` tem de ser identidade — se não for, a métrica
    está errada antes mesmo de olhar para qualquer candidato."""
    for row in gold_rows:
        result = compare_xml(row["gold_xml"], row["gold_xml"])
        assert result["df_exact"] is True, row["sample_id"]
        assert result["df_f1"] == 1.0, row["sample_id"]
        assert result["nodes_match"] is True, row["sample_id"]
        assert result["df_missing"] == {}
        assert result["df_extra"] == {}


def test_gold_path_ignores_sample_without_process_number():
    assert gold_path_for(None) is None
    assert gold_path_for('{"file": "x.txt"}') is None
    assert gold_path_for('{"process_number": 7}') == Path(GOLD_DIR) / "07.bpmn"


def test_compare_xml_detects_a_missing_edge():
    """Contraprova: remover uma aresta do candidato tem de aparecer em df_missing."""
    gold = """<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL" id="d">
      <process id="p">
        <startEvent id="s" name="Start"/><task id="a" name="A"/><task id="b" name="B"/>
        <endEvent id="e" name="End"/>
        <sequenceFlow id="f1" sourceRef="s" targetRef="a"/>
        <sequenceFlow id="f2" sourceRef="a" targetRef="b"/>
        <sequenceFlow id="f3" sourceRef="b" targetRef="e"/>
      </process></definitions>"""
    candidate = gold.replace('<sequenceFlow id="f2" sourceRef="a" targetRef="b"/>', "")

    result = compare_xml(gold, candidate)

    assert result["df_exact"] is False
    assert ("A", "B") in result["df_missing"]
    assert result["df_f1"] < 1.0


def test_load_is_idempotent(tmp_path):
    """TODO.md afirma '53/53, idempotente'; o caminho de upsert não tinha teste."""
    from src.data.db import Database
    from src.data.ingestion.import_gold_pmo import load
    from src.data.migrations.create_gold_models import ensure_schema

    linhas = [
        {"sample_id": "pmo_01", "gold_xml": "<a/>", "source_file": "01.bpmn"},
        {"sample_id": "pmo_02", "gold_xml": "<b/>", "source_file": "02.bpmn"},
    ]
    with Database(tmp_path / "t.db") as db:
        ensure_schema(db._conn)
        assert load(db, linhas) == 2
        assert load(db, linhas) == 2  # upsert, não duplicação
        assert db.query("SELECT count(*) n FROM gold_models")[0]["n"] == 2

        atualizado = [{**linhas[0], "gold_xml": "<novo/>"}]
        load(db, atualizado)
        guardado = db.query("SELECT gold_xml FROM gold_models WHERE sample_id='pmo_01'")[0]
        assert guardado["gold_xml"] == "<novo/>"


def test_dry_run_does_not_create_the_table(tmp_path):
    """Achado da revisão: `--dry-run` criava gold_models apesar do help."""
    import argparse
    import sqlite3
    from unittest.mock import patch

    import src.data.ingestion.import_gold_pmo as loader
    from src.data.db import Database

    caminho = tmp_path / "seco.db"
    with patch.object(loader, "Database", lambda: Database(caminho)):
        loader.run(argparse.Namespace(dry_run=True))

    existe = (
        sqlite3.connect(caminho)
        .execute("SELECT name FROM sqlite_master WHERE name='gold_models'")
        .fetchone()
    )
    assert existe is None


def test_message_flow_f1_is_reported_separately(gold_rows):
    """`messageFlow` é comunicação, não ordem: entra como métrica própria."""
    from src.evaluation.topology import message_flows

    com_mensagens = [r for r in gold_rows if message_flows(r["gold_xml"])]
    assert com_mensagens, "o holdout precisa de ao menos um gold com messageFlow"

    for row in com_mensagens:
        identidade = compare_xml(row["gold_xml"], row["gold_xml"])
        assert identidade["mf_f1"] == 1.0
        assert identidade["mf_missing"] == {}


def test_omitting_messages_does_not_touch_df_f1():
    """A separação é o objetivo: omitir mensagens zera MF-F1 e preserva DF-F1.

    Se um dia alguém fundir as duas relações, este teste falha."""
    from src.evaluation.topology import compare_xml

    gold = """<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL" id="d">
      <collaboration id="c">
        <participant id="p1" name="Cliente" processRef="pr1"/>
        <participant id="p2" name="Banco" processRef="pr2"/>
        <messageFlow id="m1" sourceRef="a" targetRef="b"/>
      </collaboration>
      <process id="pr1"><task id="a" name="Pedir"/></process>
      <process id="pr2"><task id="b" name="Responder"/></process>
    </definitions>"""
    sem_mensagem = gold.replace('<messageFlow id="m1" sourceRef="a" targetRef="b"/>', "")

    resultado = compare_xml(gold, sem_mensagem)

    assert resultado["df_f1"] == compare_xml(gold, gold)["df_f1"]
    assert resultado["mf_f1"] == 0.0
    assert ("Pedir", "Responder") in resultado["mf_missing"]


def test_malformed_candidate_still_reports_message_keys():
    """AC-2: linha completa mesmo com XML quebrado — inclusive as chaves mf_."""
    from src.evaluation.topology import compare_xml

    gold = (
        '<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL">'
        '<process id="p"/></definitions>'
    )
    resultado = compare_xml(gold, "<definitions><process id=")

    assert resultado["parse_error"] is not None
    assert resultado["mf_f1"] == 0.0
    assert "mf_ref_size" in resultado
