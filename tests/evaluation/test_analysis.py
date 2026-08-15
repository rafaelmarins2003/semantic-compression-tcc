"""Análise estatística (spec 003 §6.3).

Verificado contra valores calculados à mão, não contra a própria saída: um teste
que só congela o que o código já faz não detecta erro de estatística.
"""

from __future__ import annotations

import pytest

from src.evaluation.run_analysis import (
    CONTRASTES,
    bootstrap_ci,
    comparar,
    holm,
    pareado,
    rank_biserial,
)


def test_holm_confere_com_calculo_manual():
    """p = [0.01, 0.04, 0.03], m = 3, ordenados: 0.01, 0.03, 0.04.

    0.01×3 = 0.03 · 0.03×2 = 0.06 · 0.04×1 = 0.04 → monotonicidade eleva a 0.06.
    """
    assert holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])


def test_holm_impoe_monotonicidade():
    """Sem a imposição, um p maior poderia sair com ajustado menor — incoerente."""
    ajustados = holm([0.02, 0.021, 0.022])

    assert ajustados == sorted(ajustados)
    assert all(a <= 1.0 for a in ajustados)


def test_holm_nunca_passa_de_um():
    assert holm([0.9, 0.8, 0.7]) == pytest.approx([1.0, 1.0, 1.0])


def test_rank_biserial_extremos_e_empate():
    assert rank_biserial([1.0, 1.0, 1.0], [0.0, 0.0, 0.0]) == 1.0
    assert rank_biserial([0.0, 0.0, 0.0], [1.0, 1.0, 1.0]) == -1.0
    assert rank_biserial([1.0, 1.0], [1.0, 1.0]) == 0.0, "empate total não tem direção"
    assert rank_biserial([1.0, 0.0], [0.0, 1.0]) == 0.0, "um ganho e uma perda se anulam"


def test_pareado_usa_so_itens_comuns():
    """Comparação é pareada: item que só um braço tem não pode entrar."""
    x, y = pareado({"a": 1.0, "b": 2.0, "so_a": 9.0}, {"a": 0.5, "b": 1.0, "so_b": 9.0})

    assert (x, y) == ([1.0, 2.0], [0.5, 1.0])


def test_bootstrap_ci_e_reprodutivel_e_contem_a_mediana():
    diferencas = [0.1, 0.2, 0.15, 0.05, 0.3, 0.12, 0.18, 0.22, 0.08, 0.25]

    primeiro = bootstrap_ci(diferencas, n=2000)

    assert primeiro == bootstrap_ci(diferencas, n=2000), "semente fixa (§6.3)"
    assert primeiro[0] <= 0.15 <= primeiro[1]


def test_comparar_detecta_vantagem_consistente():
    a = {f"i{n}": 0.8 for n in range(20)}
    b = {f"i{n}": 0.5 for n in range(20)}

    r = comparar("A2", "A1", a, b)

    assert r["n"] == 20
    assert r["dif_mediana"] == pytest.approx(0.3)
    assert r["efeito_rb"] == 1.0
    assert r["p"] < 0.05
    assert r["ic95"][0] > 0, "IC inteiramente positivo indica superioridade"


def test_comparar_nao_quebra_com_empate_total():
    """Braços idênticos: scipy levanta se receber só diferenças nulas."""
    a = {f"i{n}": 0.7 for n in range(10)}

    r = comparar("A2", "A1", a, dict(a))

    assert r["p"] == 1.0
    assert r["dif_mediana"] == 0.0
    assert r["empates"] == 10


def test_comparar_devolve_none_sem_itens_comuns():
    assert comparar("A2", "A1", {"a": 1.0}, {"b": 1.0}) is None


def test_contrastes_planejados_sao_os_tres_da_spec():
    """Acrescentar contraste aqui depois de ver resultados é pesca (§6.3)."""
    assert CONTRASTES == [("A2", "A1"), ("A2g", "A1g"), ("A4", "A2")]
