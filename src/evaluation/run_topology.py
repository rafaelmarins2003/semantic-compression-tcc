"""Eixo 2 runner — score topological equivalence JSON ↔ XML over the dataset.

Joins each succeeded XML run to its source DSL run (and the original input JSON),
computes the direct-follows projection metric, and records it in `topology_eval`.
Deterministic and cheap: re-runnable, rows for the version pair are replaced.

Examples:
    uv run python -m src.evaluation.run_topology
    uv run python -m src.evaluation.run_topology --limit 50
"""

from __future__ import annotations

import argparse
import json
import warnings

from src.data.db import Database
from src.data.migrations.create_topology_eval import ensure_schema
from src.evaluation.topology import compare

DEFAULT_SOURCE_DSL_VERSION = "json_to_dsl_v8"
DEFAULT_XML_TRANSPILER_VERSION = "dsl_to_xml_v3"
PREVIEW_MAX = 2000


def _truncate(text: str, limit: int = PREVIEW_MAX) -> str:
    return text if len(text) <= limit else text[:limit] + " …[truncated]"


def _edges_json(edges: dict) -> str:
    """Serialize a tuple-keyed direct-follows multiset as [[src, tgt, count], ...]."""
    return _truncate(json.dumps([[a, b, c] for (a, b), c in edges.items()], ensure_ascii=False))


def pairs(db: Database, *, source_dsl_version: str, xml_version: str, limit: int) -> list[dict]:
    sql = """
        SELECT d.id AS source_dsl_run_id, x.id AS xml_run_id, d.sample_id,
               d.input_json, x.output_xml
        FROM dsl_transpiler_runs d
        JOIN xml_transpiler_runs x ON x.source_dsl_run_id = d.id
        WHERE d.transpiler_version = ? AND d.status = 'succeeded'
          AND x.xml_transpiler_version = ? AND x.status = 'succeeded'
        ORDER BY d.id
        LIMIT ?
    """
    return [dict(r) for r in db.query(sql, (source_dsl_version, xml_version, limit))]


def run_batch(*, source_dsl_version: str, xml_version: str, limit: int) -> dict:
    summary = {"n": 0, "nodes_match": 0, "df_exact": 0, "f1_sum": 0.0, "min_f1": 1.0}
    with Database() as db:
        ensure_schema(db._conn)
        db._conn.execute(
            "DELETE FROM topology_eval WHERE source_dsl_version = ? AND xml_transpiler_version = ?",
            (source_dsl_version, xml_version),
        )
        rows = pairs(
            db, source_dsl_version=source_dsl_version, xml_version=xml_version, limit=limit
        )
        for r in rows:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                res = compare(json.loads(r["input_json"]), r["output_xml"])
            db._conn.execute(
                """
                INSERT INTO topology_eval
                    (sample_id, source_dsl_run_id, xml_run_id, source_dsl_version,
                     xml_transpiler_version, nodes_match, df_exact, df_precision,
                     df_recall, df_f1, df_json_size, df_xml_size, df_missing,
                     df_extra, node_delta)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    r["sample_id"], r["source_dsl_run_id"], r["xml_run_id"],
                    source_dsl_version, xml_version,
                    int(res["nodes_match"]), int(res["df_exact"]),
                    res["df_precision"], res["df_recall"], res["df_f1"],
                    res["df_json_size"], res["df_xml_size"],
                    _edges_json(res["df_missing"]),
                    _edges_json(res["df_extra"]),
                    json.dumps(res["node_delta"], ensure_ascii=False),
                ),
            )
            summary["n"] += 1
            summary["nodes_match"] += res["nodes_match"]
            summary["df_exact"] += res["df_exact"]
            summary["f1_sum"] += res["df_f1"]
            summary["min_f1"] = min(summary["min_f1"], res["df_f1"])
        db._conn.commit()
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-dsl-version", default=DEFAULT_SOURCE_DSL_VERSION)
    p.add_argument("--xml-transpiler-version", default=DEFAULT_XML_TRANSPILER_VERSION)
    p.add_argument("--limit", type=int, default=100_000)
    args = p.parse_args()

    s = run_batch(
        source_dsl_version=args.source_dsl_version,
        xml_version=args.xml_transpiler_version,
        limit=args.limit,
    )
    n = s["n"] or 1
    print("=" * 60)
    print(f"Eixo 2 topology eval ({args.source_dsl_version} -> {args.xml_transpiler_version})")
    print("=" * 60)
    print(f"  samples            {s['n']}")
    print(f"  nodes_match        {s['nodes_match']}/{s['n']} ({s['nodes_match']/n:.1%})")
    print(f"  direct-follows ==  {s['df_exact']}/{s['n']} ({s['df_exact']/n:.1%})")
    print(f"  mean DF F1         {s['f1_sum']/n:.4f}")
    print(f"  min DF F1          {s['min_f1']:.3f}")


if __name__ == "__main__":
    main()
