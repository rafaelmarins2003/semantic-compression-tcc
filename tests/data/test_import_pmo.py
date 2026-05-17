"""Tests for PMo description importer."""

from __future__ import annotations

from src.data.ingestion.dataset.import_pmo import load_description


class TestLoadDescription:
    def test_plain_text(self, tmp_path):
        f = tmp_path / "01.txt"
        f.write_text("The process starts.\nThen it ends.")
        title, text = load_description(f)
        assert title == ""
        assert "The process starts." in text
        assert "Then it ends." in text

    def test_title_extracted(self, tmp_path):
        f = tmp_path / "25.txt"
        f.write_text("Title: Find a Job\n\nYou must report applications.\nOffers are sent.")
        title, text = load_description(f)
        assert title == "Find a Job"
        assert "Title:" not in text
        assert "You must report" in text

    def test_title_case_insensitive(self, tmp_path):
        f = tmp_path / "x.txt"
        f.write_text("TITLE: My Process\nStep one happens.\nStep two follows.")
        title, text = load_description(f)
        assert title == "My Process"

    def test_sentences_joined(self, tmp_path):
        f = tmp_path / "x.txt"
        f.write_text("First step.\nSecond step.\nThird step.")
        _, text = load_description(f)
        assert text == "First step. Second step. Third step."

    def test_empty_lines_skipped(self, tmp_path):
        f = tmp_path / "x.txt"
        f.write_text("Title: T\n\n\nFirst sentence.\n\nSecond sentence.")
        _, text = load_description(f)
        assert text == "First sentence. Second sentence."

    def test_empty_file(self, tmp_path):
        f = tmp_path / "x.txt"
        f.write_text("")
        title, text = load_description(f)
        assert title == ""
        assert text == ""

    def test_title_only(self, tmp_path):
        f = tmp_path / "x.txt"
        f.write_text("Title: Only a title\n")
        title, text = load_description(f)
        assert title == "Only a title"
        assert text == ""
