"""Tests for LLM preprocessing selection and prompt generation."""

from __future__ import annotations

from src.data.db import Database
from src.data.llm.run_preprocess import (
    DEFAULT_MODELS,
    _parse_models,
    _prune_duplicate_generations,
    build_prompt,
    pending_samples,
)


def test_build_prompt_splits_system_and_user():
    system_prompt, user_prompt = build_prompt("Customer sends order. Finance approves payment.")

    assert "<input>" in user_prompt
    assert "Customer sends order. Finance approves payment." in user_prompt
    assert "<input>" not in system_prompt
    assert "---PROCESS---" in system_prompt
    assert "---END_PROCESS---" in system_prompt
    assert "Do NOT invent information" in system_prompt


def test_ac6_prompt_declares_output_language():
    """ADR 0001 / spec 004 AC-6: o idioma da saída é fixado, não herdado da entrada."""
    system_prompt, _ = build_prompt("Cliente envia pedido.")

    assert "<language>" in system_prompt
    assert "Write ALL output in English" in system_prompt
    assert "Never mirror the input language" in system_prompt


def test_pending_samples_skips_successful_generation(tmp_path):
    db = Database(tmp_path / "test.db")
    db.insert(
        "handbook",
        "curated",
        [
            {"id": "s1", "raw_text": "Process one", "split": "sft"},
            {"id": "s2", "raw_text": "Process two", "split": "sft"},
            {"id": "s3", "raw_text": "Process three", "split": "grpo"},
        ],
    )
    db.create_generation(
        "s1", "preprocess", status="succeeded", output_text="done", prompt_version="v1"
    )
    db.create_generation(
        "s2", "preprocess", status="failed", error="retry later", prompt_version="v1"
    )

    rows = pending_samples(
        db, stage="preprocess", prompt_version="v1", limit=10, source="handbook", split="sft"
    )

    assert [row["id"] for row in rows] == ["s2"]


def test_ac6_preprocess_regenerates_on_new_prompt(tmp_path):
    """Spec 005 AC-6: trocar prompt_version reprocessa em vez de pular."""
    db = Database(tmp_path / "test.db")
    db.insert("handbook", "curated", [{"id": "s1", "raw_text": "Process one"}])
    db.create_generation(
        "s1", "preprocess", status="succeeded", output_text="done", prompt_version="v1"
    )

    same = pending_samples(db, stage="preprocess", prompt_version="v1", limit=10)
    renewed = pending_samples(db, stage="preprocess", prompt_version="v2", limit=10)

    assert [row["id"] for row in same] == []
    assert [row["id"] for row in renewed] == ["s1"]


def test_pending_samples_respects_limit(tmp_path):
    db = Database(tmp_path / "test.db")
    db.insert(
        "handbook",
        "curated",
        [
            {"id": "s1", "raw_text": "Process one"},
            {"id": "s2", "raw_text": "Process two"},
        ],
    )

    rows = pending_samples(db, stage="preprocess", prompt_version="v1", limit=1)

    assert len(rows) == 1


def test_prune_duplicate_generations_keeps_latest_non_failed(tmp_path):
    db = Database(tmp_path / "test.db")
    db.insert(
        "handbook",
        "curated",
        [
            {"id": "s1", "raw_text": "Process one"},
            {"id": "s2", "raw_text": "Process two"},
            {"id": "s3", "raw_text": "Process three"},
            {"id": "s4", "raw_text": "Process four"},
        ],
    )
    db.create_generation(
        "s1",
        "preprocess",
        prompt_version="v1",
        status="failed",
        error="old",
    )
    db.create_generation(
        "s1",
        "preprocess",
        prompt_version="v1",
        status="succeeded",
        output_text="old ok",
    )
    keep_id = db.create_generation(
        "s1",
        "preprocess",
        prompt_version="v1",
        status="succeeded",
        output_text="new ok",
    )
    db.create_generation("s2", "preprocess", status="failed", error="old")
    db.create_generation("s2", "preprocess", status="failed", error="new")
    db.create_generation("s3", "json_bpmn", status="succeeded", output_text="other stage")
    db.create_generation(
        "s4",
        "preprocess",
        prompt_version="v1",
        status="succeeded",
        output_text="v1",
    )
    db.create_generation(
        "s4",
        "preprocess",
        prompt_version="v2",
        status="succeeded",
        output_text="v2",
    )

    deleted = _prune_duplicate_generations(db, stage="preprocess")

    assert deleted == 2
    s1_rows = db.generations("s1", "preprocess")
    assert len(s1_rows) == 1
    assert s1_rows[0]["id"] == keep_id
    assert s1_rows[0]["status"] == "succeeded"
    assert s1_rows[0]["output_text"] == "new ok"
    assert len(db.generations("s2", "preprocess")) == 2
    assert len(db.generations("s3", "json_bpmn")) == 1
    assert [row["prompt_version"] for row in db.generations("s4", "preprocess")] == [
        "v1",
        "v2",
    ]


def test_default_model_fallback_order():
    """ADR 0002: GLM 5.2 é o gerador escolhido; os anteriores viram fallback."""
    assert DEFAULT_MODELS[0] == "glm-5.2:cloud"
    assert "kimi-k2.6:cloud" in DEFAULT_MODELS
    assert "deepseek-v4-pro:cloud" in DEFAULT_MODELS


def test_parse_models_supports_repeated_and_comma_separated_values():
    models = _parse_models(["a,b", "c"])

    assert models == ["a", "b", "c"]
