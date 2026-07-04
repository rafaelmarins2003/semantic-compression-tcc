"""Migration: create topology_eval table (Eixo 2).

Stores per-sample topological equivalence between the original BPMN JSON and the
generated BPMN XML: node-type parity + direct-follows projection P/R/F1. This is
the empirical "no logic loss" evidence and a filter for training-set selection.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[3] / "data" / "dataset.db"
CREATE_TOPOLOGY_EVAL_TABLE = """
CREATE TABLE IF NOT EXISTS topology_eval (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id                TEXT NOT NULL,
    source_dsl_run_id        INTEGER NOT NULL,
    xml_run_id               INTEGER NOT NULL,
    source_dsl_version       TEXT NOT NULL,
    xml_transpiler_version   TEXT NOT NULL,
    nodes_match              INTEGER NOT NULL,
    df_exact                 INTEGER NOT NULL,
    df_precision             REAL NOT NULL,
    df_recall                REAL NOT NULL,
    df_f1                    REAL NOT NULL,
    df_json_size             INTEGER NOT NULL,
    df_xml_size              INTEGER NOT NULL,
    df_missing               TEXT,
    df_extra                 TEXT,
    node_delta               TEXT,
    created_at               TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(xml_run_id) REFERENCES xml_transpiler_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_topology_eval_sample ON topology_eval(sample_id);
CREATE INDEX IF NOT EXISTS idx_topology_eval_version
ON topology_eval(source_dsl_version, xml_transpiler_version);
"""


def ensure_schema(con: sqlite3.Connection) -> None:
    con.executescript(CREATE_TOPOLOGY_EVAL_TABLE)


def run(path: Path = DB_PATH, *, recreate: bool = False) -> None:
    con = sqlite3.connect(path)
    try:
        if recreate:
            con.execute("DROP TABLE IF EXISTS topology_eval")
        ensure_schema(con)
        con.commit()
        count = con.execute("SELECT count(*) FROM topology_eval").fetchone()[0]
        print({"table": "topology_eval", "rows": count, "recreated": recreate})
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--recreate", action="store_true", help="Drop and recreate the table.")
    return p.parse_args()


if __name__ == "__main__":
    run(recreate=parse_args().recreate)
