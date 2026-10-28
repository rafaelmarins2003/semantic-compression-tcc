"""Validade XSD com IC pareado e teste de equivalência (T3 + T10).

    uv run python -m src.evaluation.run_validity

Margem e método registrados em docs/registro-tecnico.md ("T10 — margens de
equivalência", commit 1f4805a) antes desta conta existir.

Validade de um item num braço = fração das repetições válidas no XSD (saída que
não gerou, não transpilou ou não validou conta como inválida). A diferença é
pareada por item. Equivalência: o IC95 inteiro dentro de ±MARGIN.
"""

from __future__ import annotations

import argparse
import random
import statistics
from collections import defaultdict

from src.data.db import Database, not_leaked

CONTRASTS = [("A4", "X-a2r"), ("X-a2r", "A1")]
MARGIN = 0.10
N_BOOT = 10_000
SEED = 20261020


def item_validity(db: Database, arm: str) -> dict[str, float]:
    reps: dict[str, list[int]] = defaultdict(list)
    for r in db.query(
        f"SELECT sample_id, xsd_valid FROM benchmark_eval WHERE arm = ?{not_leaked()}", (arm,)
    ):
        reps[r["sample_id"]].append(1 if r["xsd_valid"] == 1 else 0)
    return {sid: statistics.mean(v) for sid, v in reps.items()}


def bootstrap_ci(valores: list[float], n_boot: int = N_BOOT) -> tuple[float, float]:
    rng = random.Random(SEED)
    medias = sorted(statistics.mean(rng.choices(valores, k=len(valores))) for _ in range(n_boot))
    return medias[int(0.025 * n_boot)], medias[int(0.975 * n_boot) - 1]


def verdict(ic: tuple[float, float], margin: float = MARGIN) -> str:
    if -margin < ic[0] and ic[1] < margin:
        return "equivalente"
    if ic[1] < -margin or ic[0] > margin:
        return "diferente além da margem"
    return "inconclusivo"


def contrast(a: dict[str, float], b: dict[str, float]) -> dict:
    comuns = sorted(set(a) & set(b))
    difs = [a[s] - b[s] for s in comuns]
    ic = bootstrap_ci(difs)
    return {
        "itens": len(difs),
        "dif_pp": round(100 * statistics.mean(difs), 1),
        "ic95_pp": [round(100 * ic[0], 1), round(100 * ic[1], 1)],
        "veredito": verdict(ic),
    }


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    with Database(read_only=True) as db:
        arms = {arm for par in CONTRASTS for arm in par}
        val = {arm: item_validity(db, arm) for arm in sorted(arms)}
    print(f"Validade XSD por item, margem ±{MARGIN:.0%} (registrada em 1f4805a)")
    for arm, v in val.items():
        print(f"  {arm}: {len(v)} itens, {100 * statistics.mean(v.values()):.1f}%")
    for a, b in CONTRASTS:
        print(f"  {a} − {b}: {contrast(val[a], val[b])}")


if __name__ == "__main__":
    main()
