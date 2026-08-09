"""Critérios de aceitação da persistência (spec 004 §5, AC-4 a AC-7).

AC-4, AC-5 e AC-7 leem o banco real: são de integração. Pulam quando a base não
está materializada, para não quebrar a suíte em um clone sem o dataset.
AC-6 é puro — lê os prompts do repositório.
"""

from __future__ import annotations

import pytest

from src.data.db import _DB_PATH, HOLDOUT_SPLIT, Database
from src.data.llm.run_generate_json import DEFAULT_PROMPT_VERSION as JSON_PROMPT_VERSION
from src.data.llm.run_generate_json import build_prompt as build_json_prompt
from src.data.llm.run_preprocess import DEFAULT_PROMPT_VERSION as PP_PROMPT_VERSION
from src.data.llm.run_preprocess import build_prompt as build_preprocess_prompt
from src.transpiler.xsd import validate_bpmn_xsd


@pytest.fixture(scope="module")
def db():
    """Somente-leitura: `pytest` não pode reescrever o dataset da pesquisa."""
    if not _DB_PATH.exists():
        pytest.skip("banco de pesquisa não disponível")
    with Database(read_only=True) as conn:
        if not conn.query("SELECT 1 FROM samples WHERE dsl IS NOT NULL LIMIT 1"):
            pytest.skip("base não materializada")
        yield conn


def test_ac4_export_training_not_empty(db):
    """Antes do materializador, `export_training` devolvia zero linhas."""
    pares = db.export_training("sft")

    assert len(pares) > 0
    assert all(p["dsl"] for p in pares)
    assert all(p["raw_text"] for p in pares)


def test_ac5_export_never_leaks_holdout(db):
    """Pedir holdout tem de falhar alto, não devolver os dados de avaliação."""
    with pytest.raises(ValueError, match=HOLDOUT_SPLIT):
        db.export_training(HOLDOUT_SPLIT)

    holdout_ids = {
        r["id"] for r in db.query("SELECT id FROM samples WHERE split = ?", (HOLDOUT_SPLIT,))
    }
    assert holdout_ids, "o teste precisa de amostras em holdout para ter sentido"

    for split in ("sft", "grpo"):
        exportados = {p["id"] for p in db.export_training(split)}
        assert not (exportados & holdout_ids), f"holdout vazou em split={split}"


def test_ac5_holdout_refusal_does_not_depend_on_the_database(tmp_path):
    """A recusa é da função, não um efeito de o banco estar vazio."""
    with Database(tmp_path / "vazio.db") as conn:
        with pytest.raises(ValueError):
            conn.export_training(HOLDOUT_SPLIT)


def test_ac6_prompts_declare_language():
    """ADR 0001: o idioma da saída é fixado no prompt, não herdado da entrada."""
    system_prompt, _ = build_preprocess_prompt("Cliente envia pedido.")
    _, json_prompt = build_json_prompt("PROCESS: Approval")

    for texto in (system_prompt, json_prompt):
        assert "<language>" in texto
        assert "in English" in texto
        assert "Never mirror the input language" in texto

    assert PP_PROMPT_VERSION.endswith("_en")
    assert JSON_PROMPT_VERSION.endswith("_en")


def test_ac7_xsd_flag_is_truthful(db):
    """`samples.xsd_ok=1` tem de significar XSD realmente válido — a flag é o que
    o harness vai consultar em vez de revalidar."""
    marcados = db.query("SELECT id, xml FROM samples WHERE xsd_ok = 1 AND xml IS NOT NULL")
    assert marcados, "o teste precisa de amostras marcadas como válidas"

    mentirosos = [r["id"] for r in marcados if validate_bpmn_xsd(r["xml"]) != []]

    assert mentirosos == [], f"marcados xsd_ok=1 mas inválidos: {mentirosos[:5]}"


def test_ac7_no_sample_has_dsl_without_parse_ok(db):
    """Contraparte: se a DSL foi gravada, ela parseou — senão o materializador
    estaria propagando resultado de run que falhou."""
    inconsistentes = db.query(
        "SELECT id FROM samples WHERE dsl IS NOT NULL AND (parse_ok IS NULL OR parse_ok != 1)"
    )

    assert [r["id"] for r in inconsistentes] == []
