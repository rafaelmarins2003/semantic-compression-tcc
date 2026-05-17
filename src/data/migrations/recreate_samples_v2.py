"""Recreate samples with the current column order.

This migration preserves existing rows and leaves new columns as NULL:
preprocessing, xml.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[3] / "data" / "dataset.db"

CREATE_SAMPLES_V2 = """
CREATE TABLE samples_v2 (
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
)
"""


def run(path: Path = DB_PATH) -> None:
    """Recreate samples and validate the migrated database."""
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row

    sample_count = con.execute("SELECT count(*) FROM samples").fetchone()[0]
    generation_table = (
        "preprocessing_generations"
        if con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='preprocessing_generations'"
        ).fetchone()
        else "generations"
    )
    generation_count = con.execute(f"SELECT count(*) FROM {generation_table}").fetchone()[0]
    views = [
        dict(row)
        for row in con.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='view' AND sql LIKE '%FROM samples%' "
            "ORDER BY name"
        )
    ]

    try:
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute("BEGIN")

        for view in views:
            con.execute(f"DROP VIEW IF EXISTS [{view['name']}]")

        con.execute("DROP TABLE IF EXISTS samples_v2")
        con.execute(CREATE_SAMPLES_V2)
        con.execute(
            """
            INSERT INTO samples_v2 (
                id, source, stage, split, title, raw_text, preprocessing,
                bpmn_json, dsl, xml, parse_ok, xsd_ok, metadata, created_at
            )
            SELECT
                id, source, stage, split, title, raw_text, NULL,
                bpmn_json, dsl, NULL, parse_ok, xsd_ok, metadata, created_at
            FROM samples
            """
        )
        con.execute("DROP TABLE samples")
        con.execute("ALTER TABLE samples_v2 RENAME TO samples")
        con.execute("CREATE INDEX idx_source_stage ON samples(source, stage)")
        con.execute("CREATE INDEX idx_split ON samples(split)")

        for view in views:
            con.execute(view["sql"])

        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.execute("PRAGMA foreign_keys=ON")

    new_sample_count = con.execute("SELECT count(*) FROM samples").fetchone()[0]
    new_generation_count = con.execute(
        f"SELECT count(*) FROM {generation_table}"
    ).fetchone()[0]
    fk_errors = con.execute("PRAGMA foreign_key_check").fetchall()

    if new_sample_count != sample_count:
        raise RuntimeError(f"samples count changed: {sample_count} -> {new_sample_count}")
    if new_generation_count != generation_count:
        raise RuntimeError(
            f"{generation_table} count changed: {generation_count} -> {new_generation_count}"
        )
    if fk_errors:
        raise RuntimeError(f"foreign key errors after migration: {fk_errors}")

    columns = [row["name"] for row in con.execute("PRAGMA table_info(samples)")]
    print(
        {
            "samples": new_sample_count,
            generation_table: new_generation_count,
            "columns": columns,
        }
    )


if __name__ == "__main__":
    run()
