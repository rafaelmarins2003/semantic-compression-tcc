"""Migration: create gold_models table (spec 004 §4.3).

Guarda o modelo de referência de cada amostra de holdout. Fica em tabela própria,
e não numa coluna de `samples`, por dois motivos: o gold é entrada de avaliação e
não resultado de pipeline, e uma amostra pode ter mais de uma referência (Zenodo
traz múltiplos modelos com score de especialista para o mesmo processo).

`score` guarda a nota do especialista (Zenodo, 0–5); fica NULL para o PMo, que
tem referência única. `variant` distingue as múltiplas referências do mesmo item.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[3] / "data" / "dataset.db"
CREATE_GOLD_MODELS_TABLE = """
CREATE TABLE IF NOT EXISTS gold_models (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id   TEXT NOT NULL,
    source      TEXT NOT NULL,
    variant     TEXT NOT NULL DEFAULT 'primary',
    format      TEXT NOT NULL,
    gold_xml    TEXT NOT NULL,
    score       REAL,
    source_file TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(sample_id, variant),
    FOREIGN KEY(sample_id) REFERENCES samples(id)
);

CREATE INDEX IF NOT EXISTS idx_gold_models_sample ON gold_models(sample_id);
"""


def ensure_schema(con: sqlite3.Connection) -> None:
    con.executescript(CREATE_GOLD_MODELS_TABLE)


def run(path: Path = DB_PATH, *, recreate: bool = False) -> None:
    con = sqlite3.connect(path)
    try:
        if recreate:
            con.execute("DROP TABLE IF EXISTS gold_models")
        ensure_schema(con)
        con.commit()
        count = con.execute("SELECT count(*) FROM gold_models").fetchone()[0]
        print({"table": "gold_models", "rows": count, "recreated": recreate})
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--recreate", action="store_true")
    return p.parse_args()


if __name__ == "__main__":
    run(recreate=parse_args().recreate)
