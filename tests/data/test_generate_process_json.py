"""Tests for JSON BPMN generation selection and prompt handling."""

from __future__ import annotations

import json

import pytest

from src.data.db import Database
from src.data.manipulation.llm.generate_process_json import (
    DEFAULT_ERROR_PREVIEW_CHARS,
    DEFAULT_JSON_BPMN_TIMEOUT,
    DEFAULT_THINK,
    _extract_json_object,
    _format_output_error,
    _json_extraction_note,
    _prune_duplicate_json_generations,
    build_prompt,
    parse_args,
    pending_preprocess_outputs,
)


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


def test_build_prompt_uses_preprocess_output():
    system_prompt, user_prompt = build_prompt("PROCESSO: Aprovação\nATORES:\n- Gestor")

    assert system_prompt == ""
    assert "Retorne um JSON valido" in user_prompt
    assert "<input_preprocess>" in user_prompt
    assert "PROCESSO: Aprovação" in user_prompt


def test_pending_preprocess_outputs_uses_latest_successful_preprocess(db):
    db.insert(
        "handbook",
        "curated",
        [
            {"id": "s1", "raw_text": "raw one", "split": "sft"},
            {"id": "s2", "raw_text": "raw two", "split": "sft"},
            {"id": "s3", "raw_text": "raw three", "split": "sft"},
            {"id": "s4", "raw_text": "raw four", "split": "sft"},
            {"id": "s5", "raw_text": "raw five", "split": "sft"},
        ],
    )
    db.create_generation("s1", "preprocess", status="succeeded", output_text="old")
    db.create_generation("s1", "preprocess", status="succeeded", output_text="new")
    db.create_generation("s3", "preprocess", status="succeeded", output_text="done")
    db.create_json_bpmn_generation(
        "s3",
        "json_bpmn",
        prompt_version="json_v1",
        status="succeeded",
        output_json={"pool": "done"},
    )
    db.create_generation("s4", "preprocess", status="succeeded", output_text="retry")
    db.create_json_bpmn_generation(
        "s4",
        "json_bpmn",
        prompt_version="json_v1",
        status="failed",
        output_json=None,
        error="retry",
    )
    db.create_generation("s5", "preprocess", status="failed", error="no output")

    rows = pending_preprocess_outputs(
        db,
        stage="json_bpmn",
        preprocess_stage="preprocess",
        prompt_version="json_v1",
        limit=10,
        source="handbook",
        split="sft",
    )

    assert [(row["id"], row["input_preprocess"]) for row in rows] == [
        ("s1", "new"),
        ("s4", "retry"),
    ]


def test_extract_json_object_ignores_reasoning_before_json():
    output = """
RACIOCINIO:
- 1 ator

{"pool": "Teste", "lanes": [], "nodes": [], "flows": []}
"""

    normalized = _extract_json_object(output)

    assert json.loads(normalized) == {
        "pool": "Teste",
        "lanes": [],
        "nodes": [],
        "flows": [],
    }


def test_extract_json_object_ignores_text_after_json():
    normalized = _extract_json_object('{"pool": "Teste"}\ntexto extra')

    assert json.loads(normalized) == {"pool": "Teste"}


def test_json_extraction_note_identifies_wrapped_json():
    output = 'RACIOCINIO\n{"pool": "Teste"}\ntexto extra'

    assert _json_extraction_note(output) == "stripped_before_after"


def test_format_output_error_includes_output_preview():
    error = _format_output_error(
        "invalid json",
        "abc" * 20,
        max_chars=12,
    )

    assert "invalid json" in error
    assert "output_chars=60" in error
    assert "output_preview_chars=12" in error
    assert "[truncated 48 chars]" in error
    assert error.endswith("abcabc")


def test_parse_args_enables_thinking_by_default(monkeypatch):
    monkeypatch.setattr("sys.argv", ["generate_process_json"])

    args = parse_args()

    assert DEFAULT_THINK is True
    assert DEFAULT_ERROR_PREVIEW_CHARS == 4000
    assert DEFAULT_JSON_BPMN_TIMEOUT == 900
    assert args.think is True
    assert args.timeout == DEFAULT_JSON_BPMN_TIMEOUT
    assert args.error_preview_chars == DEFAULT_ERROR_PREVIEW_CHARS


def test_parse_args_supports_no_think(monkeypatch):
    monkeypatch.setattr("sys.argv", ["generate_process_json", "--no-think"])

    args = parse_args()

    assert args.think is False


def test_prune_duplicate_json_generations_keeps_latest_per_prompt_version(db):
    db.insert(
        "handbook",
        "curated",
        [
            {"id": "s1", "raw_text": "raw one"},
            {"id": "s2", "raw_text": "raw two"},
        ],
    )
    db.create_json_bpmn_generation(
        "s1",
        "json_bpmn",
        prompt_version="v1",
        status="failed",
        error="old",
    )
    db.create_json_bpmn_generation(
        "s1",
        "json_bpmn",
        prompt_version="v1",
        status="succeeded",
        output_json={"pool": "old"},
    )
    keep_id = db.create_json_bpmn_generation(
        "s1",
        "json_bpmn",
        prompt_version="v1",
        status="succeeded",
        output_json={"pool": "new"},
    )
    db.create_json_bpmn_generation(
        "s2",
        "json_bpmn",
        prompt_version="v1",
        status="succeeded",
        output_json={"pool": "v1"},
    )
    db.create_json_bpmn_generation(
        "s2",
        "json_bpmn",
        prompt_version="v2",
        status="succeeded",
        output_json={"pool": "v2"},
    )

    deleted = _prune_duplicate_json_generations(db, stage="json_bpmn")

    s1_rows = db.json_bpmn_generations("s1", "json_bpmn")
    s2_rows = db.json_bpmn_generations("s2", "json_bpmn")
    assert deleted == 2
    assert len(s1_rows) == 1
    assert s1_rows[0]["id"] == keep_id
    assert json.loads(s1_rows[0]["output_json"]) == {"pool": "new"}
    assert [row["prompt_version"] for row in s2_rows] == ["v1", "v2"]
