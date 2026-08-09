"""Carrega o gold do PMo Benchmark em `gold_models` (spec 004 §4.3).

Fonte: `data/raw/pmo/bpmn_process/NN.bpmn` — BPMN **lógico**, sem BPMNDI. As
outras representações do benchmark foram descartadas na spec 004 §3: `bpmn/`
traz layout que não usamos, `pme/` exigiria adaptador de schema e
`simplified_xml/` não é BPMN padrão.

Carrega apenas amostras já presentes em `samples` com `source='pmo'`, o que
naturalmente exclui os 2 processos degradados (22 e 24).

    uv run python -m src.data.ingestion.import_gold_pmo --dry-run
    uv run python -m src.data.ingestion.import_gold_pmo
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.data.db import Database
from src.data.migrations.create_gold_models import ensure_schema
from src.evaluation.topology import xml_direct_follows

_ROOT_DIR = Path(__file__).resolve().parents[3]
GOLD_DIR = _ROOT_DIR / "data" / "raw" / "pmo" / "bpmn_process"
SOURCE = "pmo"
FORMAT = "bpmn_process"


def gold_path_for(metadata: str | None) -> Path | None:
    """Caminho do gold a partir do `process_number` da amostra, ou None.

    Devolve None em vez de propagar quando o metadata não é JSON, não é objeto
    ou tem `process_number` não numérico — o chamador registra como problema e
    segue, igual às demais falhas do laço.
    """
    if not metadata:
        return None
    try:
        number = json.loads(metadata).get("process_number")
        if number is None:
            return None
        return GOLD_DIR / f"{int(number):02d}.bpmn"
    except (json.JSONDecodeError, AttributeError, TypeError, ValueError):
        return None


def collect(db: Database) -> tuple[list[dict], list[str]]:
    """Devolve (linhas prontas para inserir, problemas encontrados)."""
    rows: list[dict] = []
    problems: list[str] = []
    for sample in db.query(
        "SELECT id, metadata FROM samples WHERE source = ? ORDER BY id", (SOURCE,)
    ):
        path = gold_path_for(sample["metadata"])
        if path is None:
            problems.append(f"{sample['id']}: metadata sem process_number")
            continue
        if not path.exists():
            problems.append(f"{sample['id']}: gold ausente em {path.name}")
            continue
        xml = path.read_text(encoding="utf-8")
        # Falhar aqui é melhor que gravar um gold que a métrica não consegue ler.
        try:
            df, _ = xml_direct_follows(xml)
        except Exception as exc:
            problems.append(f"{sample['id']}: gold não parseia ({type(exc).__name__})")
            continue
        if not df:
            problems.append(f"{sample['id']}: gold sem arestas direct-follows")
            continue
        rows.append({"sample_id": sample["id"], "gold_xml": xml, "source_file": path.name})
    return rows, problems


def load(db: Database, rows: list[dict]) -> int:
    for row in rows:
        db.execute(
            "INSERT INTO gold_models (sample_id, source, variant, format, gold_xml, source_file)"
            " VALUES (?,?,'primary',?,?,?)"
            " ON CONFLICT(sample_id, variant) DO UPDATE SET"
            "   gold_xml=excluded.gold_xml, source_file=excluded.source_file",
            (row["sample_id"], SOURCE, FORMAT, row["gold_xml"], row["source_file"]),
        )
    return len(rows)


def run(args: argparse.Namespace) -> None:
    with Database() as db:
        if not args.dry_run:
            ensure_schema(db._conn)  # DDL só fora do dry-run: o flag promete não escrever
        rows, problems = collect(db)
        for problem in problems:
            print(f"[aviso] {problem}")
        written = 0 if args.dry_run else load(db, rows)
        print(
            {
                "candidatos": len(rows),
                "carregados": written,
                "problemas": len(problems),
                "dry_run": args.dry_run,
            }
        )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true", help="Valida sem escrever.")
    return p.parse_args()


if __name__ == "__main__":
    run(parse_args())
