"""Fidelidade dos braços pelo juiz (T6). EXPLORATÓRIO.

    uv run python -m src.evaluation.run_fidelity

O juiz não passou em nenhuma validação pré-registrada (registro técnico,
2026-10-18 a 2026-10-20). Por isso nada aqui é confirmatório: sem correção de
multiplicidade, e todo número sai rotulado como exploratório.

Unidade de análise: o item. A nota de uma saída é a mediana das 3 repetições do
juiz; a nota de um braço num item é a média das suas saídas válidas nesse item.
Só saídas válidas no XSD são julgadas, então a fidelidade é condicional à validade
e a cobertura (itens com ao menos uma saída válida) é reportada junto.

Os resultados saem também por tipo de texto: os itens do PMo vindos de Mangler et
al. (2023) têm enunciados vagos e golds de modeladores iniciantes, e o juiz se
comporta diferente neles (validação por perturbação, 2026-10-20).
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
from collections import defaultdict

from scipy.stats import wilcoxon

from src.data.db import LEAKED_HOLDOUT, Database
from src.evaluation.judge import prompt_sha
from src.evaluation.run_judge import MAIN_ARMS
from src.evaluation.run_validity import verdict

CONTRASTS = [("X-a2r", "A1"), ("A4", "X-a2r"), ("A4", "A1"), ("A2", "A1")]
MANGLER = "Mangler et al. (2023)"
MARGIN = 0.5  # T10, fixada depois de ver a T6 (registro técnico, commit 1f4805a)
N_BOOT = 10_000
SEED = 20261020


def load(db: Database, sha: str) -> dict[str, dict[str, float]]:
    """arm -> sample_id -> nota média das saídas válidas."""
    reps: dict[tuple, list[float]] = defaultdict(list)
    for r in db.query(
        "SELECT target, arm, sample_id, score FROM judge_eval"
        " WHERE kind = 'benchmark' AND prompt_sha = ?",
        (sha,),
    ):
        reps[(r["arm"], r["sample_id"], r["target"])].append(r["score"])
    por_item: dict[tuple, list[float]] = defaultdict(list)
    for (arm, sid, _), notas in reps.items():
        if sid not in LEAKED_HOLDOUT:
            por_item[(arm, sid)].append(statistics.median(notas))
    notas_arm: dict[str, dict[str, float]] = defaultdict(dict)
    for (arm, sid), notas in por_item.items():
        notas_arm[arm][sid] = statistics.mean(notas)
    return notas_arm


def text_type(db: Database) -> dict[str, str]:
    tipos = {}
    for r in db.query("SELECT id, metadata FROM samples WHERE source = 'pmo'"):
        origem = (json.loads(r["metadata"] or "{}") or {}).get("origin", "")
        tipos[r["id"]] = "mangler" if origem == MANGLER else "outros"
    return tipos


def bootstrap_ci(valores: list[float], n_boot: int = N_BOOT) -> list[float]:
    rng = random.Random(SEED)
    medias = sorted(statistics.mean(rng.choices(valores, k=len(valores))) for _ in range(n_boot))
    return [round(medias[int(0.025 * n_boot)], 3), round(medias[int(0.975 * n_boot) - 1], 3)]


def describe(notas: dict[str, float], itens: set[str]) -> dict:
    valores = [notas[s] for s in itens if s in notas]
    if not valores:
        return {"itens_cobertos": 0}
    return {
        "itens_cobertos": f"{len(valores)}/{len(itens)}",
        "media": round(statistics.mean(valores), 3),
        "ic95": bootstrap_ci(valores),
    }


def contrast(a: dict[str, float], b: dict[str, float], itens: set[str]) -> dict:
    """Pareado nos itens em que os dois braços têm ao menos uma saída válida."""
    comuns = sorted(s for s in itens if s in a and s in b)
    difs = [a[s] - b[s] for s in comuns]
    if len(difs) < 2:
        return {"itens_pareados": len(difs)}
    p = wilcoxon(difs).pvalue if any(difs) else 1.0
    ic = bootstrap_ci(difs)
    return {
        "itens_pareados": len(difs),
        "dif_media": round(statistics.mean(difs), 3),
        "ic95": ic,
        "p_wilcoxon": round(float(p), 4),
        "veredito": verdict(tuple(ic), MARGIN),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prompt-sha", default=None, help="padrão: o prompt atual")
    sha = p.parse_args().prompt_sha or prompt_sha()
    with Database(read_only=True) as db:
        notas = load(db, sha)
        tipos = text_type(db)
    itens_por_tipo = {"todos": {s for s in tipos if s not in LEAKED_HOLDOUT}}
    for t in ("mangler", "outros"):
        itens_por_tipo[t] = {s for s in itens_por_tipo["todos"] if tipos[s] == t}

    print(f"EXPLORATÓRIO — juiz não validado pelos critérios registrados. prompt_sha={sha[:12]}")
    for tipo, itens in itens_por_tipo.items():
        print(f"\n[{tipo}: {len(itens)} itens]")
        for arm in MAIN_ARMS.split(","):
            print(f"  {arm}: {describe(notas.get(arm, {}), itens)}")
        for a, b in CONTRASTS:
            print(f"  {a} − {b}: {contrast(notas.get(a, {}), notas.get(b, {}), itens)}")


if __name__ == "__main__":
    main()
