"""Tests for local LLM client helpers."""

from __future__ import annotations

import os

from src.data.manipulation.llm.clients import load_dotenv


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
