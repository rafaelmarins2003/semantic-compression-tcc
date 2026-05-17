"""SQLite storage for the data pipeline.

Single database file at data/dataset.db. Each source+stage combination
is accessible as a view named {source}__{stage} (e.g. gitlab_handbook__seeds_sft).
All data lives in one normalized `samples` table for easy cross-source queries.

Usage:
    from src.data.db import Database

    db = Database()
    db.insert("gitlab_handbook", "seeds_sft", records)
    rows = db.query("SELECT * FROM gitlab_handbook__seeds_sft WHERE parse_ok=1")
    db.export_training(split="sft")  # → list of (raw_text, dsl) pairs
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

_DB_PATH = Path(__file__).parent.parent.parent / "data" / "dataset.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
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
);

CREATE INDEX IF NOT EXISTS idx_source_stage ON samples(source, stage);
CREATE INDEX IF NOT EXISTS idx_split ON samples(split);

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
    updated_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(sample_id) REFERENCES samples(id)
);

CREATE INDEX IF NOT EXISTS idx_preprocessing_generations_sample
ON preprocessing_generations(sample_id);
CREATE INDEX IF NOT EXISTS idx_preprocessing_generations_stage_status
ON preprocessing_generations(stage, status);

CREATE TABLE IF NOT EXISTS json_bpmn_generations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id           TEXT NOT NULL,
    stage               TEXT NOT NULL,
    model               TEXT,
    prompt_version      TEXT,
    status              TEXT NOT NULL DEFAULT 'pending',
    input_preprocess    TEXT,
    output_json         TEXT,
    error               TEXT,
    created_at          TEXT DEFAULT (datetime('now')),
    updated_at          TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(sample_id) REFERENCES samples(id)
);

CREATE INDEX IF NOT EXISTS idx_json_bpmn_generations_sample
ON json_bpmn_generations(sample_id);
CREATE INDEX IF NOT EXISTS idx_json_bpmn_generations_stage_status
ON json_bpmn_generations(stage, status);
"""


class Database:
    """Thin wrapper around SQLite for the dataset pipeline."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else _DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._migrate_preprocessing_generations()
        self._conn.executescript(_SCHEMA)
        self._migrate_json_bpmn_generations()
        self._conn.executescript(_SCHEMA)

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _table_exists(self, name: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
        return row is not None

    def _migrate_preprocessing_generations(self) -> None:
        """Rename/simplify the old generations table when opening existing DBs."""
        has_old = self._table_exists("generations")
        has_new = self._table_exists("preprocessing_generations")
        if not has_old or has_new:
            return

        self._conn.executescript(
            """
            CREATE TABLE preprocessing_generations (
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
                updated_at      TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(sample_id) REFERENCES samples(id)
            );

            INSERT INTO preprocessing_generations (
                id, sample_id, stage, model, prompt_version, status,
                input_text, output_text, error, created_at, updated_at
            )
            SELECT
                id, sample_id, stage, model, prompt_version, status,
                input_text, output_text, error, created_at, updated_at
            FROM generations;

            DROP TABLE generations;
            """
        )
        self._conn.commit()

    def _migrate_json_bpmn_generations(self) -> None:
        """Recreate json_bpmn_generations when an older column layout exists."""
        if not self._table_exists("json_bpmn_generations"):
            return

        expected = [
            "id",
            "sample_id",
            "stage",
            "model",
            "prompt_version",
            "status",
            "input_preprocess",
            "output_json",
            "error",
            "created_at",
            "updated_at",
        ]
        columns = [
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(json_bpmn_generations)")
        ]
        if columns == expected:
            return

        output_expr = "output_json" if "output_json" in columns else "NULL"
        if "output_preprocess" in columns:
            output_expr = "output_preprocess"

        self._conn.executescript(
            f"""
            PRAGMA foreign_keys=OFF;
            BEGIN;

            ALTER TABLE json_bpmn_generations RENAME TO json_bpmn_generations_old;

            CREATE TABLE json_bpmn_generations (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                sample_id           TEXT NOT NULL,
                stage               TEXT NOT NULL,
                model               TEXT,
                prompt_version      TEXT,
                status              TEXT NOT NULL DEFAULT 'pending',
                input_preprocess    TEXT,
                output_json         TEXT,
                error               TEXT,
                created_at          TEXT DEFAULT (datetime('now')),
                updated_at          TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(sample_id) REFERENCES samples(id)
            );

            INSERT INTO json_bpmn_generations (
                id, sample_id, stage, model, prompt_version, status,
                input_preprocess, output_json, error, created_at, updated_at
            )
            SELECT
                id, sample_id, stage, model, prompt_version, status,
                input_preprocess, {output_expr}, error, created_at, updated_at
            FROM json_bpmn_generations_old;

            DROP TABLE json_bpmn_generations_old;

            COMMIT;
            PRAGMA foreign_keys=ON;
            """
        )
        self._conn.commit()

    # ── Views ──────────────────────────────────────────────────────────────

    def _ensure_view(self, source: str, stage: str) -> str:
        """Create view {source}__{stage} if it doesn't exist.

        Source and stage are validated to prevent SQL injection —
        only alphanumeric + underscore allowed.
        """
        if not all(c.isalnum() or c == "_" for c in source + stage):
            raise ValueError(f"Invalid source/stage name: {source}/{stage}")
        view_name = f"{source}__{stage}"
        # SQLite views don't support parameters, so we interpolate safely
        self._conn.execute(
            f"CREATE VIEW IF NOT EXISTS [{view_name}] AS "
            f"SELECT * FROM samples WHERE source='{source}' AND stage='{stage}'"
        )
        return view_name

    def list_views(self) -> list[str]:
        """List all source__stage views."""
        rows = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='view' ORDER BY name"
        ).fetchall()
        return [r["name"] for r in rows]

    # ── Insert ─────────────────────────────────────────────────────────────

    def insert(
        self,
        source: str,
        stage: str,
        records: list[dict],
        *,
        replace: bool = False,
    ) -> int:
        """Insert records into the samples table and create a view.

        Each record dict can have any subset of columns:
        id, split, title, raw_text, preprocessing, bpmn_json, dsl, xml,
        parse_ok, xsd_ok, metadata.

        If 'metadata' value is a dict, it's auto-serialized to JSON.
        Returns number of rows inserted.
        """
        self._ensure_view(source, stage)
        verb = "INSERT OR REPLACE" if replace else "INSERT OR IGNORE"

        count = 0
        for r in records:
            meta = r.get("metadata")
            if isinstance(meta, dict):
                meta = json.dumps(meta, ensure_ascii=False)

            self._conn.execute(
                f"{verb} INTO samples "
                "(id, source, stage, split, title, raw_text, preprocessing, bpmn_json, dsl, "
                "xml, parse_ok, xsd_ok, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    r.get("id"),
                    source,
                    stage,
                    r.get("split"),
                    r.get("title"),
                    r.get("raw_text"),
                    r.get("preprocessing"),
                    r.get("bpmn_json"),
                    r.get("dsl"),
                    r.get("xml"),
                    r.get("parse_ok"),
                    r.get("xsd_ok"),
                    meta,
                ),
            )
            count += 1

        self._conn.commit()
        return count

    # ── Query ──────────────────────────────────────────────────────────────

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        """Execute a SELECT and return rows."""
        return self._conn.execute(sql, params).fetchall()

    def execute(self, sql: str, params: tuple = ()) -> int:
        """Execute a write statement and return affected row count."""
        cur = self._conn.execute(sql, params)
        self._conn.commit()
        return cur.rowcount

    def count(self, source: str | None = None, stage: str | None = None) -> int:
        """Count samples, optionally filtered by source and/or stage."""
        sql = "SELECT count(*) FROM samples WHERE 1=1"
        params: list = []
        if source:
            sql += " AND source=?"
            params.append(source)
        if stage:
            sql += " AND stage=?"
            params.append(stage)
        return self._conn.execute(sql, params).fetchone()[0]

    def sources(self) -> list[dict]:
        """Summary of all source+stage combinations with counts."""
        rows = self._conn.execute(
            "SELECT source, stage, count(*) as n, "
            "sum(CASE WHEN parse_ok=1 THEN 1 ELSE 0 END) as n_parse_ok, "
            "sum(CASE WHEN xsd_ok=1 THEN 1 ELSE 0 END) as n_xsd_ok "
            "FROM samples GROUP BY source, stage ORDER BY source, stage"
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Export ─────────────────────────────────────────────────────────────

    def export_training(self, split: str = "sft") -> list[dict]:
        """Export training-ready pairs: records with both raw_text and dsl."""
        rows = self.query(
            "SELECT id, source, title, raw_text, dsl FROM samples "
            "WHERE split=? AND dsl IS NOT NULL AND parse_ok=1",
            (split,),
        )
        return [dict(r) for r in rows]

    # ── Update ─────────────────────────────────────────────────────────────

    def update(self, sample_id: str, **fields) -> None:
        """Update specific fields for a sample by id."""
        if not fields:
            return
        sets = ", ".join(f"{k}=?" for k in fields)
        vals = list(fields.values())
        vals.append(sample_id)
        self._conn.execute(f"UPDATE samples SET {sets} WHERE id=?", vals)
        self._conn.commit()

    def bulk_update(self, updates: list[dict]) -> None:
        """Update multiple samples. Each dict must have 'id' + fields to set."""
        for u in updates:
            uid = u.pop("id")
            self.update(uid, **u)
            u["id"] = uid  # restore

    # ── Generation artifacts ───────────────────────────────────────────────

    def create_generation(
        self,
        sample_id: str,
        stage: str,
        *,
        model: str | None = None,
        prompt_version: str | None = None,
        status: str = "pending",
        input_text: str | None = None,
        output_text: str | None = None,
        error: str | None = None,
    ) -> int:
        """Store one versioned LLM/pipeline artifact for a sample."""
        cur = self._conn.execute(
            "INSERT INTO preprocessing_generations "
            "(sample_id, stage, model, prompt_version, status, input_text, output_text, error) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                sample_id,
                stage,
                model,
                prompt_version,
                status,
                input_text,
                output_text,
                error,
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def update_generation(self, generation_id: int, **fields) -> None:
        """Update a generation row without overwriting other versions."""
        if not fields:
            return

        serialized = {}
        for key, value in fields.items():
            serialized[key] = value

        sets = ", ".join(f"{key}=?" for key in serialized)
        vals = list(serialized.values())
        vals.append(generation_id)
        self._conn.execute(
            f"UPDATE preprocessing_generations SET {sets}, updated_at=datetime('now') "
            "WHERE id=?",
            vals,
        )
        self._conn.commit()

    def generations(self, sample_id: str | None = None, stage: str | None = None) -> list[dict]:
        """List generation artifacts, optionally filtered by sample and stage."""
        sql = "SELECT * FROM preprocessing_generations WHERE 1=1"
        params = []
        if sample_id:
            sql += " AND sample_id=?"
            params.append(sample_id)
        if stage:
            sql += " AND stage=?"
            params.append(stage)
        sql += " ORDER BY created_at, id"
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def create_json_bpmn_generation(
        self,
        sample_id: str,
        stage: str,
        *,
        model: str | None = None,
        prompt_version: str | None = None,
        status: str = "pending",
        input_preprocess: str | None = None,
        output_json: str | dict | None = None,
        error: str | None = None,
    ) -> int:
        """Store one versioned JSON BPMN generation artifact for a sample."""
        if isinstance(output_json, dict):
            output_json = json.dumps(output_json, ensure_ascii=False)

        cur = self._conn.execute(
            "INSERT INTO json_bpmn_generations "
            "(sample_id, stage, model, prompt_version, status, input_preprocess, "
            "output_json, error) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                sample_id,
                stage,
                model,
                prompt_version,
                status,
                input_preprocess,
                output_json,
                error,
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def json_bpmn_generations(
        self,
        sample_id: str | None = None,
        stage: str | None = None,
    ) -> list[dict]:
        """List JSON BPMN generation artifacts, optionally filtered."""
        sql = "SELECT * FROM json_bpmn_generations WHERE 1=1"
        params = []
        if sample_id:
            sql += " AND sample_id=?"
            params.append(sample_id)
        if stage:
            sql += " AND stage=?"
            params.append(stage)
        sql += " ORDER BY created_at, id"
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    # ── Migrate from JSONL ─────────────────────────────────────────────────

    def import_jsonl(
        self,
        path: Path | str,
        source: str,
        stage: str,
        *,
        split: str | None = None,
        text_field: str = "text",
        replace: bool = False,
    ) -> int:
        """Import a JSONL file into the database.

        Maps JSONL fields to sample columns:
        - 'id' → id
        - 'title' → title
        - text_field → raw_text
        - 'split' → split (or override with split param)
        - remaining fields → metadata JSON blob
        """
        path = Path(path)
        lines = path.read_text(encoding="utf-8").strip().split("\n")

        records = []
        known_keys = {"id", "title", text_field, "split"}
        for line in lines:
            obj = json.loads(line)
            meta = {k: v for k, v in obj.items() if k not in known_keys}
            records.append(
                {
                    "id": obj.get("id"),
                    "split": split or obj.get("split"),
                    "title": obj.get("title"),
                    "raw_text": obj.get(text_field),
                    "metadata": meta if meta else None,
                }
            )

        return self.insert(source, stage, records, replace=replace)
