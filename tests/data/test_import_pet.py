"""Tests for PET dataset importer."""

from __future__ import annotations

from src.data.ingestion.dataset.import_pet import join_tokens


class TestJoinTokens:
    def test_basic_words(self):
        assert join_tokens(["Hello", "world"]) == "Hello world"

    def test_period_no_space(self):
        assert join_tokens(["The", "process", "ends", "."]) == "The process ends."

    def test_comma_no_space(self):
        assert join_tokens(["step", "one", ",", "step", "two"]) == "step one, step two"

    def test_multiple_sentences(self):
        tokens = ["First", "step", ".", "Second", "step", "."]
        assert join_tokens(tokens) == "First step. Second step."

    def test_open_paren_no_space_after(self):
        assert join_tokens(["see", "(", "note", ")"]) == "see (note)"

    def test_hyphen(self):
        assert join_tokens(["self", "-", "service"]) == "self-service"

    def test_empty(self):
        assert join_tokens([]) == ""

    def test_single_token(self):
        assert join_tokens(["word"]) == "word"

    def test_colon_no_space(self):
        assert join_tokens(["status", ":", "active"]) == "status: active"

    def test_realistic_sentence(self):
        tokens = [
            "A",
            "company",
            "receives",
            "an",
            "order",
            ".",
            "If",
            "approved",
            ",",
            "the",
            "process",
            "continues",
            ".",
        ]
        result = join_tokens(tokens)
        assert result == "A company receives an order. If approved, the process continues."
