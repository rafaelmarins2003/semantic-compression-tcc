"""Materializa em `samples` o estado atual do pipeline (spec 005, E3).

Autoridade dos dados: as tabelas `*_runs` são o **histórico** de execução;
`samples` é o **estado atual** materializado. Antes desta rotina as colunas
`dsl`, `xml`, `bpmn_json`, `parse_ok` e `xsd_ok` ficavam NULL, o que fazia
`Database.export_training()` retornar zero linhas.

Idempotente: reexecutar sobre o mesmo par de versões reescreve os mesmos valores.

    uv run python -m src.data.run_materialize
    uv run python -m src.data.run_materialize --dry-run
"""

from __future__ import annotations

import argparse

from src.data.db import Database

DEFAULT_DSL_VERSION = "json_to_dsl_v8"
DEFAULT_XML_VERSION = "dsl_to_xml_v3"

MATERIALIZE_SQL = """
    SELECT d.sample_id, d.input_json, d.output_dsl, d.parse_ok,
           x.output_xml, x.xsd_ok
    FROM dsl_transpiler_runs d
    JOIN xml_transpiler_runs x ON x.source_dsl_run_id = d.id
    WHERE d.transpiler_version = ? AND d.status = 'succeeded'
      AND x.xml_transpiler_version = ? AND x.status = 'succeeded'
    ORDER BY d.id
"""


def pending(db: Database, *, dsl_version: str, xml_version: str) -> list[dict]:
    return [dict(r) for r in db.query(MATERIALIZE_SQL, (dsl_version, xml_version))]


def materialize(db: Database, rows: list[dict]) -> int:
    for row in rows:
        db.update(
            row["sample_id"],
            bpmn_json=row["input_json"],
            dsl=row["output_dsl"],
            xml=row["output_xml"],
            parse_ok=row["parse_ok"],
            xsd_ok=row["xsd_ok"],
        )
    return len(rows)


def run(args: argparse.Namespace) -> None:
    with Database() as db:
        rows = pending(db, dsl_version=args.dsl_version, xml_version=args.xml_version)
        written = 0 if args.dry_run else materialize(db, rows)
        print(
            {
                "dsl_version": args.dsl_version,
                "xml_version": args.xml_version,
                "candidatos": len(rows),
                "materializados": written,
                "dry_run": args.dry_run,
            }
        )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dsl-version", default=DEFAULT_DSL_VERSION)
    p.add_argument("--xml-version", default=DEFAULT_XML_VERSION)
    p.add_argument("--dry-run", action="store_true", help="Conta sem escrever.")
    return p.parse_args()


if __name__ == "__main__":
    run(parse_args())
