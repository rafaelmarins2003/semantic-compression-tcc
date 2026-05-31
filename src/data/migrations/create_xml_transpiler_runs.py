"""Migration: create xml_transpiler_runs table.

Records deterministic DSL -> BPMN XML transpiler attempts. The table is an
audit trail parallel to dsl_transpiler_runs: every row stores the source DSL
snapshot, generated XML when available, validation status, and error details.

`xsd_ok`/`xsd_error` are an independent quality gate (BPMN 2.0 XSD validity),
orthogonal to `status`/`xml_ok` (well-formed + globally unique ids): a row can
be well-formed but schema-invalid, and we keep the XML either way to debug it.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[3] / "data" / "dataset.db"
CREATE_XML_RUNS_TABLE = """
CREATE TABLE IF NOT EXISTS xml_transpiler_runs (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id                TEXT NOT NULL,
    source_generation_id     INTEGER,
    source_dsl_run_id        INTEGER NOT NULL,
    source_dsl_version       TEXT NOT NULL,
    xml_transpiler_version   TEXT NOT NULL,
    status                   TEXT NOT NULL,
    xml_ok                   INTEGER,
    xsd_ok                   INTEGER,
    input_dsl                TEXT,
    output_xml               TEXT,
    warnings                 TEXT,
    error_stage              TEXT,
    error_type               TEXT,
    error_message            TEXT,
    error_traceback          TEXT,
    xsd_error                TEXT,
    created_at               TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(source_dsl_run_id) REFERENCES dsl_transpiler_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_xml_transpiler_sample
ON xml_transpiler_runs(sample_id);
CREATE INDEX IF NOT EXISTS idx_xml_transpiler_version_status
ON xml_transpiler_runs(xml_transpiler_version, status);
CREATE INDEX IF NOT EXISTS idx_xml_transpiler_source_dsl
ON xml_transpiler_runs(source_dsl_run_id);
"""

# Columns added after the table's first version; applied idempotently so an
# existing DB picks them up without dropping data.
ADDED_COLUMNS = {"xsd_ok": "INTEGER", "xsd_error": "TEXT"}


def ensure_schema(con: sqlite3.Connection) -> None:
    """Create the table (if absent) and add any columns missing on old DBs."""
    con.executescript(CREATE_XML_RUNS_TABLE)
    existing = {r[1] for r in con.execute("PRAGMA table_info(xml_transpiler_runs)")}
    for col, decl in ADDED_COLUMNS.items():
        if col not in existing:
            con.execute(f"ALTER TABLE xml_transpiler_runs ADD COLUMN {col} {decl}")


def run(path: Path = DB_PATH, *, recreate: bool = False) -> None:
    con = sqlite3.connect(path)
    try:
        if recreate:
            con.execute("DROP TABLE IF EXISTS xml_transpiler_runs")
        ensure_schema(con)
        con.commit()
        count = con.execute("SELECT count(*) FROM xml_transpiler_runs").fetchone()[0]
        print({"table": "xml_transpiler_runs", "rows": count, "recreated": recreate})
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--recreate",
        action="store_true",
        help="Drop and recreate the table (destructive; rows are deterministic).",
    )
    return p.parse_args()


if __name__ == "__main__":
    run(recreate=parse_args().recreate)
