"""Critérios da validação por perturbação, sobre casos sintéticos."""

from src.evaluation.run_perturbation_analysis import analyze, concordance


def _casos(intacto, um, tres, parafrase, itens=6):
    casos = []
    for i in range(itens):
        sid = f"pmo_{i}"
        for kind, n, nota in [
            ("intact", 0, intacto), ("drop_task", 1, um), ("add_task", 1, um),
            ("triple", 3, tres), ("paraphrase", 0, parafrase),
        ]:  # fmt: skip
            casos.append({"sample_id": sid, "kind": kind, "n_defects": n, "judge": nota})
    return casos


def test_concordance_counts_ties_as_half():
    assert concordance([(5, 4), (4, 4), (3, 4)]) == 0.5


def test_valid_measure_passes():
    r = analyze(_casos(5, 4, 2, 5), "judge")
    assert r["C1_concordancia"] == 1.0 and r["C3_invariancia"] == 1.0
    assert r["C2_rho_defeitos"] < -0.5 and r["passa"]


def test_measure_that_ignores_defects_fails():
    assert not analyze(_casos(4, 4, 4, 4), "judge")["passa"]


def test_measure_that_punishes_paraphrase_fails():
    r = analyze(_casos(5, 4, 2, 2), "judge")
    assert r["C3_invariancia"] == 0.0 and not r["passa"]


def test_paraphrase_intensity_uses_df_f1_tokens(tmp_path):
    import json

    from src.data.db import Database
    from src.data.migrations.create_perturbation_cases import ensure_schema
    from src.evaluation.run_perturbation_analysis import paraphrase_intensity

    db = Database(tmp_path / "t.db")
    ensure_schema(db._conn)
    mapa = {"Collect resumes": "Gather CVs", "Begin onboarding process": "Start onboarding process"}
    db._conn.execute(
        "INSERT INTO perturbation_cases"
        " (case_id, sample_id, kind, n_defects, operators, detail, xml)"
        " VALUES ('x:paraphrase', 'x', 'paraphrase', 0, '[]', ?, '<x/>')",
        (json.dumps({"mapping": mapa}),),
    )
    r = paraphrase_intensity(db)
    db.close()
    assert r == {"rotulos": 2, "jaccard_medio": 0.25, "ainda_casam_no_df_f1": 0.5}
