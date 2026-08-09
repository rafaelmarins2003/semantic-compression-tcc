"""Migration: create model_pilot table (spec 004 §4.1b).

Guarda o resultado por amostra do piloto de seleção do modelo gerador. Existe
para que a escolha do modelo seja rastreável até dados, não até reputação.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[3] / "data" / "dataset.db"
CREATE_MODEL_PILOT_TABLE = """
CREATE TABLE IF NOT EXISTS model_pilot (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_label       TEXT NOT NULL,
    sample_id       TEXT NOT NULL,
    source          TEXT NOT NULL,
    preprocess_model TEXT NOT NULL,
    json_model      TEXT NOT NULL,
    prompt_version  TEXT NOT NULL,
    stage_failed    TEXT,
    json_ok         INTEGER NOT NULL DEFAULT 0,
    dsl_ok          INTEGER NOT NULL DEFAULT 0,
    xml_ok          INTEGER NOT NULL DEFAULT 0,
    xsd_ok          INTEGER NOT NULL DEFAULT 0,
    n_nodes         INTEGER,
    n_gateways      INTEGER,
    n_lanes         INTEGER,
    n_flows         INTEGER,
    rule_violations INTEGER,
    pt_markers      INTEGER,
    error_message   TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_model_pilot_run ON model_pilot(run_label);
"""


def ensure_schema(con: sqlite3.Connection) -> None:
    con.executescript(CREATE_MODEL_PILOT_TABLE)


def run(path: Path = DB_PATH, *, recreate: bool = False) -> None:
    con = sqlite3.connect(path)
    try:
        if recreate:
            con.execute("DROP TABLE IF EXISTS model_pilot")
        ensure_schema(con)
        con.commit()
        count = con.execute("SELECT count(*) FROM model_pilot").fetchone()[0]
        print({"table": "model_pilot", "rows": count, "recreated": recreate})
    finally:
        con.close()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--recreate", action="store_true")
    return p.parse_args()


if __name__ == "__main__":
    run(recreate=parse_args().recreate)
