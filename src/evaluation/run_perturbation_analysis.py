"""Validação do juiz por perturbação controlada: critérios e comparação com o DF-F1.

    uv run python -m src.evaluation.run_perturbation_analysis

Critérios fixados ANTES da execução (registro-tecnico, 2026-10-19). A nota do juiz
por caso é a mediana das 3 repetições; Δ é a nota do caso menos a do gold intacto
do mesmo item.

  C1 sensibilidade  concordância intacto × mutante de 1 defeito, no mesmo item:
                    P(intacto > mutante) + 0,5·P(empate) ≥ 0,80
  C2 gradação       Spearman entre nº de defeitos (0, 1, 3) e Δ ≤ −0,5
  C3 invariância    |Δ da paráfrase| ≤ 20% da escala (1 ponto no juiz) em ≥ 80% dos itens

O juiz passa se os três passarem. O DF-F1 recebe o mesmo cálculo como comparação.
C1 e C2 o favorecem por construção: a referência dele é o próprio gold mutado.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict

from scipy.stats import spearmanr

from src.data.db import Database
from src.evaluation.judge import prompt_sha
from src.evaluation.run_benchmark import references, score_candidate
from src.evaluation.topology import LABEL_MATCH_THRESHOLD, _jaccard, _tokens

C1_MIN, C2_MAX, C3_MIN, C3_TOL = 0.80, -0.5, 0.80, 0.20
SCALES = {"judge": 5.0, "df_f1": 1.0}


def load(db: Database, sha: str) -> list[dict]:
    notas: dict[str, list[float]] = defaultdict(list)
    for r in db.query(
        "SELECT target, score FROM judge_eval WHERE kind = 'perturbation' AND prompt_sha = ?",
        (sha,),
    ):
        notas[r["target"].removeprefix("pert:")].append(r["score"])
    refs: dict[str, list] = {}
    casos = []
    for r in db.query("SELECT case_id, sample_id, kind, n_defects, xml FROM perturbation_cases"):
        sid = r["sample_id"]
        refs.setdefault(sid, references(db, sid))
        casos.append(
            {
                **dict(r),
                "judge": statistics.median(notas[r["case_id"]]) if notas[r["case_id"]] else None,
                "df_f1": score_candidate(r["xml"], refs[sid])["df_f1"],
            }
        )
    return casos


def concordance(pares: list[tuple[float, float]]) -> float:
    """P(a > b) + 0,5·P(a = b)."""
    return sum((a > b) + 0.5 * (a == b) for a, b in pares) / len(pares)


def analyze(casos: list[dict], medida: str) -> dict:
    intacto = {c["sample_id"]: c[medida] for c in casos if c["kind"] == "intact"}
    validos = [
        c for c in casos if c[medida] is not None and intacto.get(c["sample_id"]) is not None
    ]
    delta = [(c, c[medida] - intacto[c["sample_id"]]) for c in validos]
    simples = [(intacto[c["sample_id"]], c[medida]) for c in validos if c["n_defects"] == 1]
    grad = [(c["n_defects"], d) for c, d in delta if c["kind"] != "paraphrase"]
    para = [d for c, d in delta if c["kind"] == "paraphrase"]
    tol = C3_TOL * SCALES[medida]

    c1 = concordance(simples) if simples else float("nan")
    # Nota constante: correlação indefinida, e o critério falha (NaN <= x é falso).
    variou = len({d for _, d in grad}) > 1
    c2 = float(spearmanr(*zip(*grad)).statistic) if variou else float("nan")
    c3 = sum(abs(d) <= tol for d in para) / len(para) if para else float("nan")
    por_operador = defaultdict(list)
    for c in validos:
        if c["n_defects"] == 1:
            por_operador[c["kind"]].append((intacto[c["sample_id"]], c[medida]))
    return {
        "itens": len(intacto),
        "casos": len(validos),
        "C1_concordancia": round(c1, 3),
        "C2_rho_defeitos": round(c2, 3),
        "C3_invariancia": round(c3, 3),
        "passa": c1 >= C1_MIN and c2 <= C2_MAX and c3 >= C3_MIN,
        "delta_medio_1_defeito": _media([d for c, d in delta if c["n_defects"] == 1]),
        "delta_medio_3_defeitos": _media([d for c, d in delta if c["n_defects"] == 3]),
        "delta_medio_parafrase": _media(para),
        "concordancia_por_operador": {
            op: round(concordance(ps), 3) for op, ps in sorted(por_operador.items())
        },
    }


def paraphrase_intensity(db: Database) -> dict:
    """Quanto as paráfrases mudam os rótulos, na tokenização do próprio DF-F1.

    C3 só tem sentido junto com isto: paráfrase leve é fácil de ignorar.
    """
    pares = [
        (orig, novo)
        for (detail,) in db.query("SELECT detail FROM perturbation_cases WHERE kind = 'paraphrase'")
        for orig, novo in json.loads(detail)["mapping"].items()
    ]
    if not pares:
        return {}
    sims = [_jaccard(_tokens(a), _tokens(b)) for a, b in pares]
    return {
        "rotulos": len(pares),
        "jaccard_medio": round(statistics.mean(sims), 3),
        "ainda_casam_no_df_f1": round(sum(s >= LABEL_MATCH_THRESHOLD for s in sims) / len(sims), 3),
    }


def _media(xs: list[float]) -> float | None:
    return round(statistics.mean(xs), 3) if xs else None


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prompt-sha", default=None, help="padrão: o prompt atual")
    sha = p.parse_args().prompt_sha or prompt_sha()
    with Database(read_only=True) as db:
        casos = load(db, sha)
        intensidade = paraphrase_intensity(db)
    sem_nota = sum(c["judge"] is None for c in casos)
    print(f"prompt_sha={sha[:12]}  casos={len(casos)}  sem nota do juiz={sem_nota}")
    print(f"critérios: C1 >= {C1_MIN}, C2 <= {C2_MAX}, C3 >= {C3_MIN} (tolerância {C3_TOL:.0%})")
    print(f"intensidade da paráfrase: {intensidade}")
    for medida in ("judge", "df_f1"):
        print(f"[{medida}]")
        for chave, valor in analyze(casos, medida).items():
            print(f"  {chave}: {valor}")


if __name__ == "__main__":
    main()
