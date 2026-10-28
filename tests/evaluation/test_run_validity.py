from src.evaluation.run_validity import contrast, verdict


def test_verdict_equivalent_only_when_whole_ci_inside_margin():
    assert verdict((-0.05, 0.08)) == "equivalente"
    assert verdict((-0.12, 0.02)) == "inconclusivo"
    assert verdict((-0.30, -0.15)) == "diferente além da margem"


def test_contrast_is_paired_on_common_items():
    a = {"x": 1.0, "y": 1.0, "z": 0.0}
    b = {"x": 1.0, "y": 1.0}
    r = contrast(a, b)
    assert r["itens"] == 2 and r["dif_pp"] == 0.0 and r["veredito"] == "equivalente"
