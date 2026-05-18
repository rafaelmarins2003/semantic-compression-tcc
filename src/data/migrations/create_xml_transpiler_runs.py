"""Migration: create xml_transpiler_runs table.

Records deterministic DSL -> BPMN XML transpiler attempts. The table is an
audit trail parallel to dsl_transpiler_runs: every row stores the source DSL
snapshot, generated XML when available, validation status, and error details.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.data.manipulation.deterministic.dsl_to_xml import CREATE_XML_RUNS_TABLE

DB_PATH = Path(__file__).resolve().parents[3] / "data" / "dataset.db"


def run(path: Path = DB_PATH) -> None:
    con = sqlite3.connect(path)
    try:
        con.executescript(CREATE_XML_RUNS_TABLE)
        con.commit()
        count = con.execute("SELECT count(*) FROM xml_transpiler_runs").fetchone()[0]
        print({"table": "xml_transpiler_runs", "rows": count})
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


if __name__ == "__main__":
    run()
