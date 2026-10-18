"""Tests for local LLM client helpers."""

from __future__ import annotations

import os

import pytest

from src.data.llm import clients
from src.data.llm.clients import LLMError, generate_meta, load_dotenv


def test_load_dotenv_explicit_path(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("GEMINI_API_KEY=test-key\n", encoding="utf-8")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    loaded = load_dotenv(env_path)

    assert loaded == env_path
    assert os.environ["GEMINI_API_KEY"] == "test-key"


def test_load_dotenv_finds_env_from_subdirectory(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    subdir = tmp_path / "src" / "data"
    subdir.mkdir(parents=True)
    env_path.write_text("OPENROUTER_API_KEY=test-openrouter-key\n", encoding="utf-8")
    monkeypatch.chdir(subdir)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    loaded = load_dotenv()

    assert loaded == env_path
    assert os.environ["OPENROUTER_API_KEY"] == "test-openrouter-key"


def test_generate_meta_sends_schema_and_returns_usage(monkeypatch):
    enviado = {}

    def falso(url, payload, *, headers, timeout):
        enviado.update(url=url, payload=payload, auth=headers["Authorization"])
        return {
            "model": "muse-spark-1.3-contributor",
            "choices": [{"finish_reason": "stop", "message": {"content": ' {"score": 4} '}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 50},
        }

    monkeypatch.setattr(clients, "_post_json", falso)
    esquema = {"type": "object", "properties": {"score": {"type": "integer"}}}

    texto, meta = generate_meta(
        "rate it", api_key="k", model="muse-spark-1.3-contributor", json_schema=esquema, seed=1
    )

    assert texto == '{"score": 4}'
    assert meta["usage"]["completion_tokens"] == 50
    assert enviado["auth"] == "Bearer k"
    assert enviado["payload"]["seed"] == 1
    assert enviado["payload"]["response_format"]["json_schema"]["schema"] == esquema


def test_generate_meta_empty_content_is_an_error(monkeypatch):
    monkeypatch.setattr(
        clients, "_post_json", lambda *a, **k: {"choices": [{"message": {"content": ""}}]}
    )
    with pytest.raises(LLMError):
        generate_meta("x", api_key="k", model="m")
