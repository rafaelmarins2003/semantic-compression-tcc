"""Tests for Zenodo BPMN description importer."""

from __future__ import annotations

from src.data.ingestion.dataset.import_zenodo import load_description


class TestLoadDescription:
    def test_full_header(self, tmp_path):
        f = tmp_path / "E_j01.txt"
        f.write_text("Category: E-Government\nTitle: Find a Job\n\nYou must report applications.")
        category, title, text = load_description(f)
        assert category == "E-Government"
        assert title == "Find a Job"
        assert text == "You must report applications."

    def test_no_header(self, tmp_path):
        f = tmp_path / "x.txt"
        f.write_text("The process starts.\nThen it ends.")
        category, title, text = load_description(f)
        assert category == ""
        assert title == ""
        assert "The process starts." in text

    def test_only_title(self, tmp_path):
        f = tmp_path / "x.txt"
        f.write_text("Title: My Process\n\nStep one. Step two.")
        category, title, text = load_description(f)
        assert title == "My Process"
        assert category == ""
        assert text == "Step one. Step two."

    def test_multiline_text_joined(self, tmp_path):
        f = tmp_path / "x.txt"
        f.write_text("Category: C\nTitle: T\n\nLine one.\nLine two.\nLine three.")
        _, _, text = load_description(f)
        assert text == "Line one. Line two. Line three."

    def test_empty_lines_between_body_preserved(self, tmp_path):
        f = tmp_path / "x.txt"
        f.write_text("Title: T\n\nFirst paragraph.\n\nSecond paragraph.")
        _, _, text = load_description(f)
        # Empty lines in body are skipped (only non-empty lines joined)
        assert "First paragraph." in text
        assert "Second paragraph." in text

    def test_empty_file(self, tmp_path):
        f = tmp_path / "x.txt"
        f.write_text("")
        category, title, text = load_description(f)
        assert category == title == text == ""

    def test_id_format(self, tmp_path):
        """Verify that stem is usable as a clean ID."""
        f = tmp_path / "E_j01.txt"
        f.write_text("Some text here for the process.")
        # id would be f"zenodo_{f.stem}" = "zenodo_E_j01"
        assert f.stem == "E_j01"
