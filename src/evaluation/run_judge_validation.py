"""Validação do juiz contra as notas de especialista do Zenodo (T5).

    uv run python -m src.evaluation.run_judge_validation

Critério fixado ANTES da execução (auditoria de 2026-10-14, P1): o juiz é adotado
como medida de fidelidade se o Spearman entre a nota dele e a do especialista for
ρ ≥ 0,5 nos 222 modelos. A nota do juiz por modelo é a mediana das 3 repetições.

O IC é por bootstrap **agrupado por processo**: os ~9 modelos de um mesmo texto não
são independentes entre si, e reamostrar modelos soltos daria um IC estreito demais.
Também reporta o ρ dentro de cada processo (o juiz ordena bem as alternativas do
mesmo texto?) e a concordância do juiz consigo mesmo entre repetições.
"""

from __future__ import annotations

import argparse
import random
import statistics
from collections import defaultdict
from itertools import combinations

from scipy.stats import spearmanr

from src.data.db import Database
from src.evaluation.judge import prompt_sha

THRESHOLD = 0.5
N_BOOT = 10_000
SEED = 20261018


def load(db: Database, sha: str) -> dict[str, dict]:
    """target -> {processo, nota do especialista, notas do juiz por repetição}."""
    modelos: dict[str, dict] = {}
    for r in db.query(
        "SELECT target, sample_id, expert_score, rep, score FROM judge_eval"
        " WHERE kind = 'zenodo' AND prompt_sha = ?",
        (sha,),
    ):
        m = modelos.setdefault(
            r["target"], {"process": r["sample_id"], "expert": r["expert_score"], "reps": {}}
        )
        m["reps"][r["rep"]] = r["score"]
    return modelos


def _rho(pares: list[tuple[float, float]]) -> float:
    x, y = zip(*pares)
    if len(set(x)) < 2 or len(set(y)) < 2:
        return float("nan")
    return float(spearmanr(x, y).statistic)


def cluster_bootstrap_ci(pares_por_processo: dict[str, list], n_boot: int = N_BOOT) -> list:
    rng = random.Random(SEED)
    processos = list(pares_por_processo)
    rhos = []
    for _ in range(n_boot):
        amostra = [p for _ in processos for p in pares_por_processo[rng.choice(processos)]]
        rho = _rho(amostra)
        if rho == rho:  # descarta NaN
            rhos.append(rho)
    rhos.sort()
    return [round(rhos[int(0.025 * len(rhos))], 3), round(rhos[int(0.975 * len(rhos)) - 1], 3)]


def analyze(modelos: dict[str, dict]) -> dict:
    completos = {t: m for t, m in modelos.items() if m["reps"]}
    por_processo: dict[str, list] = defaultdict(list)
    for m in completos.values():
        por_processo[m["process"]].append((statistics.median(m["reps"].values()), m["expert"]))
    pares = [p for ps in por_processo.values() for p in ps]

    dentro = [r for ps in por_processo.values() if (r := _rho(ps)) == r]

    reps = [m["reps"] for m in completos.values() if len(m["reps"]) >= 2]
    rho_reps = [
        _rho([(r[a], r[b]) for r in reps if a in r and b in r])
        for a, b in combinations(range(3), 2)
    ]
    rho = _rho(pares)
    return {
        "modelos": len(pares),
        "processos": len(por_processo),
        "rho": round(rho, 3),
        "ic95": cluster_bootstrap_ci(por_processo),
        "criterio": f"rho >= {THRESHOLD}",
        "adotado": rho >= THRESHOLD,
        "rho_dentro_do_processo_medio": round(statistics.mean(dentro), 3) if dentro else None,
        "processos_com_rho_dentro": len(dentro),
        "erro_absoluto_medio": round(statistics.mean(abs(j - e) for j, e in pares), 3),
        "rho_entre_repeticoes": [round(r, 3) for r in rho_reps if r == r],
        "modelos_com_amplitude_ate_0_5": round(
            sum(max(r.values()) - min(r.values()) <= 0.5 for r in reps) / len(reps), 3
        )
        if reps
        else None,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prompt-sha", default=None, help="padrão: o prompt atual")
    sha = p.parse_args().prompt_sha or prompt_sha()
    with Database(read_only=True) as db:
        modelos = load(db, sha)
    if not modelos:
        raise SystemExit(f"sem notas para prompt_sha={sha[:12]}; rode run_judge --zenodo antes")
    incompletos = sum(len(m["reps"]) < 3 for m in modelos.values())
    print(f"prompt_sha={sha[:12]}  modelos={len(modelos)}  com <3 repetições={incompletos}")
    for chave, valor in analyze(modelos).items():
        print(f"  {chave}: {valor}")


if __name__ == "__main__":
    main()
