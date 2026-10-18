"""Análise da validação: mediana das repetições, critério e concordância."""

import math

from src.evaluation.run_judge_validation import analyze, cluster_bootstrap_ci


def _modelos(pares):
    return {
        f"zenodo:{proc}/{i}": {"process": proc, "expert": e, "reps": dict(enumerate(reps))}
        for i, (proc, e, reps) in enumerate(pares)
    }


def test_judge_that_tracks_expert_is_adopted():
    pares = [(f"E{p}", e, [e, e, e]) for p in range(4) for e in (1.0, 2.5, 4.0, 5.0)]
    r = analyze(_modelos(pares))
    assert r["rho"] == 1.0 and r["adotado"] and r["erro_absoluto_medio"] == 0
    assert r["rho_entre_repeticoes"] == [1.0, 1.0, 1.0]


def test_score_is_median_of_reps_and_noise_fails_criterion():
    pares = [(f"E{p}", e, [5.0 - e, 0.0, 5.0]) for p in range(4) for e in (1.0, 2.5, 4.0, 5.0)]
    r = analyze(_modelos(pares))
    assert not r["adotado"]
    assert r["modelos_com_amplitude_ate_0_5"] == 0


def test_bootstrap_ci_contains_point_estimate():
    por_processo = {
        f"E{p}": [(e + (p % 2) * 0.5, e) for e in (1.0, 2.0, 3.0, 4.0, 5.0)] for p in range(6)
    }
    baixo, alto = cluster_bootstrap_ci(por_processo, n_boot=500)
    assert not math.isnan(baixo) and baixo <= alto <= 1.0
