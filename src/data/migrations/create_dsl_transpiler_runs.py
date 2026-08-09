"""Migration: create dsl_transpiler_runs table.

Records every attempt of the deterministic JSON → DSL transpiler
(src/data/manipulation/deterministic/json_to_dsl.py) against each
input row from json_bpmn_generations. Captures the DSL output, parser
acceptance, and any error/warning so debugging can iterate against
real data without rerunning the LLM stages.

Status values:
    succeeded        — convert() returned text AND parser accepted it
    convert_failed   — convert() raised an exception
    parse_failed     — convert() returned text but parser rejected it
    convert_timeout  — convert() or parse() exceeded the per-sample budget
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[3] / "data" / "dataset.db"

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS dsl_transpiler_runs (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id             TEXT NOT NULL,
    source_generation_id  INTEGER,            -- FK json_bpmn_generations.id
    transpiler_version    TEXT NOT NULL,      -- e.g. json_to_dsl_v1
    status                TEXT NOT NULL,      -- succeeded | convert_failed | parse_failed
    parse_ok              INTEGER,            -- 1 / 0 / NULL (NULL if convert failed)
    input_json            TEXT,               -- snapshot of input for reproducibility
    output_dsl            TEXT,               -- NULL if convert failed
    warnings              TEXT,               -- pipe-separated captured warning messages
    error_stage           TEXT,               -- convert | parse | NULL
    error_type            TEXT,               -- exception class name
    error_message         TEXT,               -- truncated message
    error_traceback       TEXT,               -- full traceback for debugging
    created_at            TEXT DEFAULT (datetime('now'))
)
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_transpiler_sample ON dsl_transpiler_runs(sample_id)",
    "CREATE INDEX IF NOT EXISTS idx_transpiler_version_status "
    "ON dsl_transpiler_runs(transpiler_version, status)",
    "CREATE INDEX IF NOT EXISTS idx_transpiler_source_gen "
    "ON dsl_transpiler_runs(source_generation_id)",
]


def run(path: Path = DB_PATH) -> None:
    con = sqlite3.connect(path)
    try:
        con.execute("BEGIN")
        con.execute(CREATE_TABLE)
        for idx in CREATE_INDEXES:
            con.execute(idx)
        con.execute("COMMIT")
        count = con.execute("SELECT count(*) FROM dsl_transpiler_runs").fetchone()[0]
        print({"table": "dsl_transpiler_runs", "rows": count})
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()


if __name__ == "__main__":
    run()
