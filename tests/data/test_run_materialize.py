"""Spec 005 AC-5: `samples` reflete o estado atual dos runs bem-sucedidos."""

from __future__ import annotations

from src.data.db import Database
from src.data.migrations.create_dsl_transpiler_runs import CREATE_TABLE as DSL_RUNS_TABLE
from src.data.migrations.create_xml_transpiler_runs import ensure_schema as ensure_xml
from src.data.run_materialize import materialize, pending

DSL_V = "json_to_dsl_v8"
XML_V = "dsl_to_xml_v3"


def _seed(tmp_path, *, xml_status="succeeded"):
    db = Database(tmp_path / "test.db")
    db._conn.executescript(DSL_RUNS_TABLE)
    ensure_xml(db._conn)
    db.insert("pet", "descriptions", [{"id": "s1", "raw_text": "Process one", "split": "sft"}])
    cur = db._conn.execute(
        "INSERT INTO dsl_transpiler_runs "
        "(sample_id, source_generation_id, transpiler_version, status, parse_ok, "
        " input_json, output_dsl) VALUES (?,0,?,'succeeded',1,?,?)",
        ("s1", DSL_V, '{"nodes": []}', 'process "P" { start -> end }'),
    )
    db._conn.execute(
        "INSERT INTO xml_transpiler_runs "
        "(sample_id, source_dsl_run_id, source_dsl_version, xml_transpiler_version, "
        " status, xml_ok, xsd_ok, output_xml) VALUES (?,?,?,?,?,1,1,?)",
        ("s1", cur.lastrowid, DSL_V, XML_V, xml_status, "<definitions/>"),
    )
    db._conn.commit()
    return db


def test_ac5_samples_materialized(tmp_path):
    db = _seed(tmp_path)
    rows = pending(db, dsl_version=DSL_V, xml_version=XML_V)

    assert materialize(db, rows) == 1

    sample = db.query("SELECT * FROM samples WHERE id='s1'")[0]
    assert sample["dsl"] == 'process "P" { start -> end }'
    assert sample["xml"] == "<definitions/>"
    assert sample["bpmn_json"] == '{"nodes": []}'
    assert sample["parse_ok"] == 1
    assert sample["xsd_ok"] == 1


def test_materialize_ignores_failed_xml_runs(tmp_path):
    db = _seed(tmp_path, xml_status="failed")

    assert pending(db, dsl_version=DSL_V, xml_version=XML_V) == []


def test_materialize_is_idempotent(tmp_path):
    db = _seed(tmp_path)
    rows = pending(db, dsl_version=DSL_V, xml_version=XML_V)
    materialize(db, rows)
    first = db.query("SELECT dsl, xml FROM samples WHERE id='s1'")[0]
    materialize(db, pending(db, dsl_version=DSL_V, xml_version=XML_V))
    second = db.query("SELECT dsl, xml FROM samples WHERE id='s1'")[0]

    assert dict(first) == dict(second)


def test_export_training_returns_pairs_after_materialize(tmp_path):
    db = _seed(tmp_path)
    assert db.export_training("sft") == []

    materialize(db, pending(db, dsl_version=DSL_V, xml_version=XML_V))

    exported = db.export_training("sft")
    assert [row["id"] for row in exported] == ["s1"]
