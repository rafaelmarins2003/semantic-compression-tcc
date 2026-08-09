"""Carrega as múltiplas referências do Zenodo em `gold_models` (spec 003 §4).

O Zenodo (Mangler et al., 2023) é a mesma fonte dos itens PMo 25–48, mas traz
**vários modelos por processo** com nota de especialista de 0 a 5. Eles entram
como referências alternativas dos itens do PMo, permitindo a regra congelada na
spec 003 §4: pontuar o candidato contra todas as referências com nota ≥ 4 e
ficar com o máximo.

O mapeamento Zenodo→PMo é derivado por similaridade de texto (determinística) e
**verificado como bijeção** antes de gravar: 24 amostras Zenodo para os 24 itens
do PMo com `origin='Mangler et al. (2023)'`. Falha alto se não for bijeção, em
vez de gravar um mapeamento parcial.

    uv run python -m src.data.ingestion.import_gold_zenodo --dry-run
    uv run python -m src.data.ingestion.import_gold_zenodo
"""

from __future__ import annotations

import argparse
import difflib
from pathlib import Path

from src.data.db import Database
from src.data.migrations.create_gold_models import ensure_schema
from src.evaluation.topology import xml_direct_follows

_ROOT_DIR = Path(__file__).resolve().parents[3]
ZENODO_DIR = _ROOT_DIR / "data" / "raw" / "zenodo" / "bpmn"
SOURCE = "zenodo"
FORMAT = "bpmn2"
MIN_SCORE = 4.0
MANGLER = "Mangler et al. (2023)"


def map_zenodo_to_pmo(db: Database) -> dict[str, str]:
    """Bijeção zenodo_id → pmo_id, por similaridade de texto. Falha se não for."""
    alvo = {
        r["id"]: r["raw_text"] or ""
        for r in db.query("SELECT id, raw_text, metadata FROM samples WHERE source='pmo'")
        if MANGLER in (r["metadata"] or "")
    }
    origem = {
        r["id"]: r["raw_text"] or ""
        for r in db.query("SELECT id, raw_text FROM samples WHERE source=?", (SOURCE,))
    }
    pares = {
        zid: max(alvo, key=lambda pid: difflib.SequenceMatcher(None, zt, alvo[pid]).ratio())
        for zid, zt in origem.items()
    }
    if len(set(pares.values())) != len(pares) or len(pares) != len(alvo):
        raise SystemExit(
            f"mapeamento não é bijeção: {len(pares)} zenodo → "
            f"{len(set(pares.values()))} pmo distintos (alvo tem {len(alvo)})"
        )
    return pares


def _score(path: Path) -> float | None:
    quality = path.with_name(path.name.replace(".bpmn2.xml", ".quality.txt"))
    if not quality.exists():
        return None
    try:
        return float(quality.read_text().strip())
    except ValueError:
        return None


def collect(db: Database) -> tuple[list[dict], list[str]]:
    """Referências com nota ≥ MIN_SCORE, já mapeadas para o item do PMo."""
    mapa = map_zenodo_to_pmo(db)
    rows: list[dict] = []
    problems: list[str] = []
    for zid, pid in sorted(mapa.items()):
        pasta = ZENODO_DIR / zid.replace("zenodo_", "")
        if not pasta.is_dir():
            problems.append(f"{zid}: pasta ausente em {pasta.name}")
            continue
        for modelo in sorted(pasta.glob("*.bpmn2.xml")):
            score = _score(modelo)
            if score is None:
                problems.append(f"{zid}/{modelo.name}: sem nota — descartado (spec 003 §4)")
                continue
            if score < MIN_SCORE:
                continue
            xml = modelo.read_text(encoding="utf-8")
            try:
                df, _ = xml_direct_follows(xml)
            except Exception as exc:
                problems.append(f"{zid}/{modelo.name}: não parseia ({type(exc).__name__})")
                continue
            if not df:
                problems.append(f"{zid}/{modelo.name}: sem arestas direct-follows")
                continue
            rows.append(
                {
                    "sample_id": pid,
                    "variant": f"zenodo:{zid.replace('zenodo_', '')}:{modelo.name.split('.')[0]}",
                    "gold_xml": xml,
                    "score": score,
                    "source_file": f"{pasta.name}/{modelo.name}",
                }
            )
    return rows, problems


def load(db: Database, rows: list[dict]) -> int:
    for row in rows:
        db.execute(
            "INSERT INTO gold_models (sample_id, source, variant, format, gold_xml, score,"
            " source_file) VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(sample_id, variant) DO UPDATE SET"
            "   gold_xml=excluded.gold_xml, score=excluded.score,"
            "   source_file=excluded.source_file",
            (
                row["sample_id"],
                SOURCE,
                row["variant"],
                FORMAT,
                row["gold_xml"],
                row["score"],
                row["source_file"],
            ),
        )
    return len(rows)


def run(args: argparse.Namespace) -> None:
    with Database() as db:
        if not args.dry_run:
            ensure_schema(db._conn)
        rows, problems = collect(db)
        for problem in problems:
            print(f"[aviso] {problem}")
        written = 0 if args.dry_run else load(db, rows)
        itens = len({r["sample_id"] for r in rows})
        print(
            {
                "referencias": len(rows),
                "itens_pmo_cobertos": itens,
                "carregadas": written,
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
