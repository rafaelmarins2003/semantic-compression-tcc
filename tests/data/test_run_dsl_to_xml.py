"""Tests for the DSL -> XML batch runner."""

from __future__ import annotations

from lxml import etree

from src.data.db import Database
from src.data.deterministic.run_dsl_to_xml import (
    ensure_xml_transpiler_runs_table,
    insert_run,
    pending_rows,
    run_one,
)


def _create_dsl_runs_table(db: Database) -> None:
    db._conn.executescript(
        """
        CREATE TABLE dsl_transpiler_runs (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            sample_id             TEXT NOT NULL,
            source_generation_id  INTEGER,
            transpiler_version    TEXT NOT NULL,
            status                TEXT NOT NULL,
            parse_ok              INTEGER,
            input_json            TEXT,
            output_dsl            TEXT,
            warnings              TEXT,
            error_stage           TEXT,
            error_type            TEXT,
            error_message         TEXT,
            error_traceback       TEXT,
            created_at            TEXT DEFAULT (datetime('now'))
        );
        """
    )
    db._conn.commit()


def test_run_one_transpiles_valid_dsl_to_well_formed_xml():
    result = run_one(
        'process "P" { start "Begin" -> user "Review" -> end "Done" }',
        timeout_seconds=5,
    )

    assert result["status"] == "succeeded"
    assert result["xml_ok"] == 1
    root = etree.fromstring(result["output_xml"].encode("utf-8"))
    assert root.find(".//{http://www.omg.org/spec/BPMN/20100524/MODEL}userTask") is not None


def test_run_one_reports_transpile_failure():
    result = run_one(
        'process "P" { start -> #missing }',
        timeout_seconds=5,
    )

    assert result["status"] == "transpile_failed"
    assert result["xml_ok"] is None
    assert result["error_stage"] == "transpile"
    assert result["error_type"] == "ValueError"
    assert "Unresolved DSL ref #missing" in result["error_message"]


def test_run_one_allows_multiple_processes_with_unique_xml_ids():
    result = run_one(
        """
        process "A" { start -> end }
        process "B" { start -> end }
        """,
        timeout_seconds=5,
    )

    assert result["status"] == "succeeded"
    assert result["xml_ok"] == 1
    root = etree.fromstring(result["output_xml"].encode("utf-8"))
    ids = [el.get("id") for el in root.xpath("//*[@id]")]
    assert len(ids) == len(set(ids))


def test_pending_rows_skips_existing_runs(tmp_path):
    db = Database(tmp_path / "dataset.db")
    try:
        _create_dsl_runs_table(db)
        ensure_xml_transpiler_runs_table(db)
        db._conn.execute(
            """
            INSERT INTO dsl_transpiler_runs (
                sample_id, source_generation_id, transpiler_version,
                status, parse_ok, input_json, output_dsl
            )
            VALUES ('s1', 10, 'json_to_dsl_v4', 'succeeded', 1, '{}',
                    'process "P" { start -> end }')
            """
        )
        db._conn.commit()

        rows = pending_rows(
            db,
            source_dsl_version="json_to_dsl_v4",
            xml_transpiler_version="dsl_to_xml_v1",
            limit=10,
            retry_failed=False,
        )
        assert len(rows) == 1

        result = run_one(rows[0]["output_dsl"], timeout_seconds=5)
        insert_run(
            db,
            sample_id=rows[0]["sample_id"],
            source_generation_id=rows[0]["source_generation_id"],
            source_dsl_run_id=rows[0]["source_dsl_run_id"],
            source_dsl_version=rows[0]["source_dsl_version"],
            xml_transpiler_version="dsl_to_xml_v1",
            input_dsl=rows[0]["output_dsl"],
            result=result,
        )

        rows = pending_rows(
            db,
            source_dsl_version="json_to_dsl_v4",
            xml_transpiler_version="dsl_to_xml_v1",
            limit=10,
            retry_failed=False,
        )
        assert rows == []
    finally:
        db.close()
