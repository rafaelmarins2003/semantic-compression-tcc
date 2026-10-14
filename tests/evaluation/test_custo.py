"""Custo por requisição (Metodologia §Custo por Requisição)."""

import pytest

from src.data.llm.utils import load_prompt
from src.evaluation.run_benchmark import ARMS
from src.evaluation.run_custo import (
    CENARIO_FIGURA,
    CENARIOS,
    PRECOS,
    custo,
    linhas_de_custo,
    prefixo_fixo,
)


def test_custo_soma_entrada_e_saida_por_milhao():
    assert custo(1_000_000, 0, {"in": 0.66, "out": 1.98}) == pytest.approx(0.66)
    assert custo(1000, 500, {"in": 1.0, "out": 2.0}) == pytest.approx((1000 + 1000) / 1e6)


def test_tokens_de_cache_saem_a_preco_de_cache():
    preco = {"in": 1.0, "out": 0.0, "cache": 0.1}
    assert custo(1000, 0, preco, t_cache=600) == pytest.approx((400 * 1.0 + 600 * 0.1) / 1e6)


def test_cache_sem_preco_falha_em_vez_de_cobrar_zero():
    with pytest.raises(ValueError):
        custo(1000, 0, {"in": 1.0, "out": 1.0, "cache": None}, t_cache=10)


def test_cache_do_7b_tem_a_mesma_proporcao_do_deepseek():
    """Tratamento simétrico: comparar o grande com cache contra o pequeno sem
    cache favoreceria o grande por construção."""
    ds = PRECOS["deepseek_fora_pico"]
    for nome in ("7b", "7b_lora"):
        assert PRECOS[nome]["cache"] / PRECOS[nome]["in"] == pytest.approx(ds["cache"] / ds["in"])


def test_figura_usa_o_cenario_mais_caro_do_a4():
    assert CENARIO_FIGURA["A4"] == max(CENARIOS["A4"], key=lambda n: PRECOS[n]["in"])
    assert set(CENARIO_FIGURA) == set(CENARIOS)


def test_custo_por_saida_valida_divide_pela_validade():
    m = {"t_in": 1000, "t_out": 100, "t_prefixo": 0, "validade": 0.5}
    (linha,) = linhas_de_custo("A4", m)[:1]
    assert linha["por_1M_validas"] == pytest.approx(2 * linha["por_1M"])


@pytest.mark.parametrize("arm", CENARIOS)
def test_prefixo_cacheavel_e_o_trecho_antes_da_descricao(arm):
    prompt = load_prompt(ARMS[arm].prompt)
    prefixo = prefixo_fixo(prompt)
    assert "{description}" in prompt
    assert prompt.startswith(prefixo) and "{description}" not in prefixo


def test_sem_saida_valida_o_custo_por_valida_nao_e_definido():
    m = {"t_in": 1000, "t_out": 100, "t_prefixo": 0, "validade": 0.0}
    assert all(li["por_1M_validas"] is None for li in linhas_de_custo("A3m", m))
