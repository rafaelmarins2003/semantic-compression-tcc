"""Migration: create preprocessing_generations table.

Retroactive migration documenting the schema of the table used by
src/data/manipulation/llm/preprocess.py. Safe to re-run (idempotent).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[3] / "data" / "dataset.db"

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS preprocessing_generations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id       TEXT NOT NULL,
    stage           TEXT NOT NULL,
    model           TEXT,
    prompt_version  TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    input_text      TEXT,
    output_text     TEXT,
    error           TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
)
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_preproc_gen_sample ON preprocessing_generations(sample_id)",
    "CREATE INDEX IF NOT EXISTS idx_preproc_gen_stage_status "
    "ON preprocessing_generations(stage, status)",
]


def run(path: Path = DB_PATH) -> None:
    con = sqlite3.connect(path)
    try:
        con.execute("BEGIN")
        con.execute(CREATE_TABLE)
        for idx in CREATE_INDEXES:
            con.execute(idx)
        con.execute("COMMIT")
        count = con.execute("SELECT count(*) FROM preprocessing_generations").fetchone()[0]
        print({"table": "preprocessing_generations", "rows": count})
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()


if __name__ == "__main__":
    run()
