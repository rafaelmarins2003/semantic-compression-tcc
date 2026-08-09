"""Tests for SQLite dataset storage."""

from __future__ import annotations

import json
import sqlite3

import pytest

from src.data.db import Database


@pytest.fixture
def db(tmp_path):
    """Fresh in-memory-like database per test."""
    return Database(tmp_path / "test.db")


@pytest.fixture
def sample_records():
    return [
        {"id": "s1", "title": "Process A", "raw_text": "Step 1. Do X.", "split": "sft"},
        {"id": "s2", "title": "Process B", "raw_text": "Step 1. Do Y.", "split": "sft"},
        {"id": "s3", "title": "Process C", "raw_text": "Step 1. Do Z.", "split": "grpo"},
    ]


class TestInsertAndQuery:
    def test_insert_creates_view(self, db, sample_records):
        db.insert("handbook", "seeds_sft", sample_records[:2])
        views = db.list_views()
        assert "handbook__seeds_sft" in views

    def test_insert_and_count(self, db, sample_records):
        db.insert("handbook", "seeds_sft", sample_records)
        assert db.count() == 3
        assert db.count(source="handbook") == 3
        assert db.count(source="handbook", stage="seeds_sft") == 3
        assert db.count(source="other") == 0

    def test_query_via_view(self, db, sample_records):
        db.insert("handbook", "seeds_sft", sample_records[:2])
        rows = db.query("SELECT * FROM [handbook__seeds_sft]")
        assert len(rows) == 2
        assert rows[0]["title"] == "Process A"

    def test_multiple_sources(self, db):
        db.insert("handbook", "seeds_sft", [{"id": "h1", "raw_text": "X"}])
        db.insert("pmo", "raw", [{"id": "p1", "raw_text": "Y"}])
        assert db.count(source="handbook") == 1
        assert db.count(source="pmo") == 1
        assert db.count() == 2

    def test_metadata_dict_serialized(self, db):
        db.insert("handbook", "raw", [{"id": "m1", "metadata": {"score": 89, "words": 500}}])
        rows = db.query("SELECT metadata FROM samples WHERE id='m1'")
        meta = json.loads(rows[0]["metadata"])
        assert meta["score"] == 89

    def test_insert_ignore_duplicates(self, db):
        db.insert("h", "s", [{"id": "dup", "raw_text": "first"}])
        db.insert("h", "s", [{"id": "dup", "raw_text": "second"}])
        rows = db.query("SELECT raw_text FROM samples WHERE id='dup'")
        assert rows[0]["raw_text"] == "first"  # ignored duplicate

    def test_insert_replace(self, db):
        db.insert("h", "s", [{"id": "r1", "raw_text": "first"}])
        db.insert("h", "s", [{"id": "r1", "raw_text": "updated"}], replace=True)
        rows = db.query("SELECT raw_text FROM samples WHERE id='r1'")
        assert rows[0]["raw_text"] == "updated"


class TestUpdate:
    def test_update_single_field(self, db):
        db.insert("h", "s", [{"id": "u1", "raw_text": "text"}])
        db.update("u1", dsl='process "X" { task "A" }')
        rows = db.query("SELECT dsl FROM samples WHERE id='u1'")
        assert rows[0]["dsl"] == 'process "X" { task "A" }'

    def test_update_multiple_fields(self, db):
        db.insert("h", "s", [{"id": "u2"}])
        db.update("u2", parse_ok=1, xsd_ok=0)
        rows = db.query("SELECT parse_ok, xsd_ok FROM samples WHERE id='u2'")
        assert rows[0]["parse_ok"] == 1
        assert rows[0]["xsd_ok"] == 0

    def test_bulk_update(self, db):
        db.insert("h", "s", [{"id": "b1"}, {"id": "b2"}])
        db.bulk_update(
            [
                {"id": "b1", "parse_ok": 1},
                {"id": "b2", "parse_ok": 0},
            ]
        )
        r1 = db.query("SELECT parse_ok FROM samples WHERE id='b1'")[0]
        r2 = db.query("SELECT parse_ok FROM samples WHERE id='b2'")[0]
        assert r1["parse_ok"] == 1
        assert r2["parse_ok"] == 0


class TestGenerations:
    def test_old_generations_table_is_migrated(self, tmp_path):
        path = tmp_path / "old.db"
        con = sqlite3.connect(path)
        con.executescript(
            """
            CREATE TABLE samples (
                id             TEXT PRIMARY KEY,
                source         TEXT NOT NULL,
                stage          TEXT NOT NULL,
                split          TEXT,
                title          TEXT,
                raw_text       TEXT,
                preprocessing  TEXT,
                bpmn_json      TEXT,
                dsl            TEXT,
                xml            TEXT,
                parse_ok       INTEGER,
                xsd_ok         INTEGER,
                metadata       TEXT,
                created_at     TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE generations (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                sample_id       TEXT NOT NULL,
                stage           TEXT NOT NULL,
                model           TEXT,
                prompt_version  TEXT,
                status          TEXT NOT NULL DEFAULT 'pending',
                input_text      TEXT,
                output_text     TEXT,
                output_json     TEXT,
                output_dsl      TEXT,
                output_bpmn     TEXT,
                error           TEXT,
                metadata        TEXT,
                created_at      TEXT DEFAULT (datetime('now')),
                updated_at      TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(sample_id) REFERENCES samples(id)
            );

            INSERT INTO samples (id, source, stage, raw_text)
            VALUES ('s1', 'handbook', 'curated', 'raw');

            INSERT INTO generations (
                sample_id, stage, model, prompt_version, status, input_text,
                output_text, output_json, output_dsl, output_bpmn, error, metadata
            )
            VALUES (
                's1', 'preprocess', 'model-a', 'v1', 'succeeded', 'input',
                'output', '{"old": true}', 'dsl', 'bpmn', NULL, '{"cost": 1}'
            );
            """
        )
        con.commit()
        con.close()

        migrated = Database(path)

        tables = {
            row["name"]
            for row in migrated.query("SELECT name FROM sqlite_master WHERE type='table'")
        }
        rows = migrated.generations("s1", "preprocess")

        assert "generations" not in tables
        assert "preprocessing_generations" in tables
        assert len(rows) == 1
        assert rows[0]["model"] == "model-a"
        assert rows[0]["output_text"] == "output"

    def test_preprocessing_generations_schema(self, db):
        columns = {row["name"] for row in db.query("PRAGMA table_info(preprocessing_generations)")}

        assert "output_json" not in columns
        assert "output_dsl" not in columns
        assert "output_bpmn" not in columns
        assert "metadata" not in columns

    def test_create_generation(self, db):
        db.insert("handbook", "curated", [{"id": "s1", "raw_text": "raw"}])

        gid = db.create_generation(
            "s1",
            "preprocess",
            model="gpt-test",
            prompt_version="v1",
            status="succeeded",
            output_text="structured",
        )

        rows = db.generations("s1")
        assert rows[0]["id"] == gid
        assert rows[0]["stage"] == "preprocess"
        assert rows[0]["model"] == "gpt-test"
        assert rows[0]["output_text"] == "structured"

    def test_multiple_generations_preserved(self, db):
        db.insert("handbook", "curated", [{"id": "s1", "raw_text": "raw"}])

        db.create_generation("s1", "preprocess", prompt_version="v1", output_text="old")
        db.create_generation("s1", "preprocess", prompt_version="v2", output_text="new")

        rows = db.generations("s1", "preprocess")
        assert [r["output_text"] for r in rows] == ["old", "new"]

    def test_update_generation(self, db):
        db.insert("handbook", "curated", [{"id": "s1", "raw_text": "raw"}])
        gid = db.create_generation("s1", "json_bpmn")

        db.update_generation(
            gid,
            status="failed",
            error="invalid json",
        )

        row = db.generations("s1")[0]
        assert row["status"] == "failed"
        assert row["error"] == "invalid json"

    def test_create_json_bpmn_generation(self, db):
        db.insert("handbook", "curated", [{"id": "s1", "raw_text": "raw"}])

        gid = db.create_json_bpmn_generation(
            "s1",
            "json_bpmn",
            model="gpt-test",
            prompt_version="json_v1",
            status="succeeded",
            input_preprocess="PROCESSO: Teste",
            output_json={"pool": "Teste"},
        )

        rows = db.json_bpmn_generations("s1", "json_bpmn")
        assert rows[0]["id"] == gid
        assert rows[0]["model"] == "gpt-test"
        assert rows[0]["input_preprocess"] == "PROCESSO: Teste"
        assert rows[0]["output_json"] == '{"pool": "Teste"}'

    def test_old_json_bpmn_table_is_migrated(self, tmp_path):
        path = tmp_path / "old_json.db"
        con = sqlite3.connect(path)
        con.executescript(
            """
            CREATE TABLE samples (
                id             TEXT PRIMARY KEY,
                source         TEXT NOT NULL,
                stage          TEXT NOT NULL,
                split          TEXT,
                title          TEXT,
                raw_text       TEXT,
                preprocessing  TEXT,
                bpmn_json      TEXT,
                dsl            TEXT,
                xml            TEXT,
                parse_ok       INTEGER,
                xsd_ok         INTEGER,
                metadata       TEXT,
                created_at     TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE json_bpmn_generations (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                sample_id           TEXT NOT NULL,
                stage               TEXT NOT NULL,
                model               TEXT,
                prompt_version      TEXT,
                status              TEXT NOT NULL DEFAULT 'pending',
                input_preprocess    TEXT,
                output_preprocess   TEXT,
                error               TEXT,
                created_at          TEXT DEFAULT (datetime('now')),
                updated_at          TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(sample_id) REFERENCES samples(id)
            );

            INSERT INTO samples (id, source, stage, raw_text)
            VALUES ('s1', 'handbook', 'curated', 'raw');

            INSERT INTO json_bpmn_generations (
                sample_id, stage, model, prompt_version, status,
                input_preprocess, output_preprocess
            )
            VALUES (
                's1', 'json_bpmn', 'model-a', 'v1', 'succeeded',
                'PROCESSO: Teste', '{"pool": "Teste"}'
            );
            """
        )
        con.commit()
        con.close()

        migrated = Database(path)

        columns = [
            row["name"] for row in migrated.query("PRAGMA table_info(json_bpmn_generations)")
        ]
        rows = migrated.json_bpmn_generations("s1", "json_bpmn")

        assert "output_preprocess" not in columns
        assert "output_json" in columns
        assert rows[0]["output_json"] == '{"pool": "Teste"}'


class TestSources:
    def test_sources_summary(self, db):
        db.insert(
            "handbook",
            "seeds_sft",
            [
                {"id": "a", "parse_ok": 1, "xsd_ok": 1},
                {"id": "b", "parse_ok": 1, "xsd_ok": 0},
                {"id": "c", "parse_ok": 0},
            ],
        )
        db.insert("pmo", "test", [{"id": "d", "parse_ok": 1, "xsd_ok": 1}])

        summary = db.sources()
        assert len(summary) == 2
        hb = next(s for s in summary if s["source"] == "handbook")
        assert hb["n"] == 3
        assert hb["n_parse_ok"] == 2
        assert hb["n_xsd_ok"] == 1


class TestExport:
    def test_export_training(self, db):
        db.insert(
            "handbook",
            "seeds_sft",
            [
                {"id": "e1", "split": "sft", "raw_text": "desc A", "dsl": "dsl A", "parse_ok": 1},
                {"id": "e2", "split": "sft", "raw_text": "desc B", "dsl": "dsl B", "parse_ok": 1},
                {
                    "id": "e3",
                    "split": "sft",
                    "raw_text": "desc C",
                    "dsl": None,
                    "parse_ok": 1,
                },  # no dsl
                {
                    "id": "e4",
                    "split": "sft",
                    "raw_text": "desc D",
                    "dsl": "dsl D",
                    "parse_ok": 0,
                },  # failed parse
                {
                    "id": "e5",
                    "split": "grpo",
                    "raw_text": "desc E",
                    "dsl": "dsl E",
                    "parse_ok": 1,
                },  # wrong split
            ],
        )
        pairs = db.export_training(split="sft")
        assert len(pairs) == 2
        assert pairs[0]["raw_text"] == "desc A"
        assert pairs[0]["dsl"] == "dsl A"


class TestImportJsonl:
    def test_import_basic(self, db, tmp_path):
        jsonl_path = tmp_path / "data.jsonl"
        lines = [
            json.dumps({"id": "j1", "title": "T1", "text": "Content 1", "score": 89}),
            json.dumps({"id": "j2", "title": "T2", "text": "Content 2", "score": 45}),
        ]
        jsonl_path.write_text("\n".join(lines))

        count = db.import_jsonl(jsonl_path, "handbook", "seeds_sft", split="sft")
        assert count == 2
        assert db.count(source="handbook", stage="seeds_sft") == 2

        rows = db.query("SELECT * FROM [handbook__seeds_sft]")
        assert rows[0]["raw_text"] == "Content 1"
        assert rows[0]["split"] == "sft"
        # score should be in metadata
        meta = json.loads(rows[0]["metadata"])
        assert meta["score"] == 89

    def test_import_custom_text_field(self, db, tmp_path):
        jsonl_path = tmp_path / "custom.jsonl"
        jsonl_path.write_text(json.dumps({"id": "c1", "description": "Desc", "title": "T"}))

        db.import_jsonl(jsonl_path, "src", "raw", text_field="description")
        rows = db.query("SELECT raw_text FROM samples WHERE id='c1'")
        assert rows[0]["raw_text"] == "Desc"


class TestContextManager:
    def test_context_manager(self, tmp_path):
        with Database(tmp_path / "ctx.db") as db:
            db.insert("h", "s", [{"id": "ctx1"}])
            assert db.count() == 1
