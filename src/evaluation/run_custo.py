"""Custo por requisição dos braços, a preço público de API (Metodologia §Custo).

C = t_in · p_in + t_out · p_out, com os tokens médios de cada geração gravada em
`benchmark_eval` (instrução + descrição na entrada) e o preço por token do
provedor. Reporta também o custo por saída válida, C / taxa de validade.

Métrica posterior ao pré-registro: reexpressão monetária de grandezas já
medidas, não medição nova. Tempo de inferência fica de fora de propósito
(nuvem do provedor contra estação local mediria hardware, não método).

Todos os preços vêm de um único provedor (Together AI, 2026-10-24), que serve
os três modelos: sem horário de pico nem descontos temporários.

Hipóteses que acompanham qualquer número daqui:
- Preço do 7B é o do Qwen2.5-7B-Instruct (mesma arquitetura e porte do
  Qwen2.5-Coder-7B, que nenhum provedor serve por token). O "+50%" do A4 é
  margem arbitrada: Together e Fireworks descontinuaram LoRA por token.
- Tokenizador único (Qwen2.5-Coder) para todos os braços: aproxima o DeepSeek.
- Cenário com cache: o trecho do prompt anterior à descrição é prefixo fixo e
  é cobrado a preço de cache hit. O Together não oferece cache para o 7B, então
  o 7B paga a entrada cheia nos dois cenários (desfavorece o A4).

Uso:
    uv run --with transformers python -m src.evaluation.run_custo
"""

from __future__ import annotations

import argparse
import statistics as st

from src.data.db import Database, not_leaked
from src.data.llm.utils import load_prompt
from src.evaluation.run_benchmark import ARMS

# US$ por milhão de tokens, https://www.together.ai/pricing, consultados em
# 2026-10-24. Mudar um preço é mudar o número da monografia: atualizar a data junto.
DATA_PRECOS = "2026-10-24"
PRECOS = {
    "deepseek": {"in": 1.32, "out": 3.96, "cache": 0.13},  # DeepSeek V4 Pro
    "glm": {"in": 1.40, "out": 4.40, "cache": 0.26},  # GLM-5.2
    # Qwen2.5 7B Instruct Turbo, sem cache no provedor: cache = preço cheio.
    "7b": {"in": 0.30, "out": 0.30, "cache": 0.30},
    "7b_lora": {"in": 0.45, "out": 0.45, "cache": 0.45},  # +50%, hipótese
}
# Braço → cenários de preço aplicáveis. Só os braços que entram no argumento.
CENARIOS = {
    "A1": ["deepseek"],
    "A1g": ["glm"],
    "A2": ["deepseek"],
    "A2g": ["glm"],
    "X-a2r": ["deepseek"],
    "A3": ["7b"],
    "A3m": ["7b"],
    "A4": ["7b", "7b_lora"],
}
# Um número por braço para a figura custo × validade: sem cache, e o A4 no cenário mais caro
# (+50% de adapter), que é o conservador contra a
# hipótese do trabalho. A3 e A3m não têm adapter.
CENARIO_FIGURA = {
    "A1": "deepseek", "A1g": "glm", "A2": "deepseek",
    "A2g": "glm", "X-a2r": "deepseek", "A3": "7b", "A3m": "7b",
    "A4": "7b_lora",
}  # fmt: skip
POR_REQUISICOES = 1_000_000


def custo(t_in: float, t_out: float, preco: dict, t_cache: float = 0.0) -> float:
    """Custo de UMA requisição em US$. `t_cache` tokens da entrada saem a preço
    de cache; o resto da entrada, a preço cheio."""
    if t_cache and preco.get("cache") is None:
        raise ValueError("cenário sem preço de cache")
    cheio = t_in - t_cache
    total = cheio * preco["in"] + t_out * preco["out"]
    if t_cache:
        total += t_cache * preco["cache"]
    return total / 1e6


def custo_figura(arm: str, m: dict) -> float:
    """US$ por milhão de requisições no cenário de referência da figura."""
    return custo(m["t_in"], m["t_out"], PRECOS[CENARIO_FIGURA[arm]]) * POR_REQUISICOES


def prefixo_fixo(prompt: str) -> str:
    """Trecho do prompt anterior à descrição: igual em toda requisição."""
    return prompt.split("{description}", 1)[0]


def medir_braco(db: Database, arm: str, tok) -> dict:
    """Tokens médios de entrada e de saída, prefixo cacheável e validade."""
    prompt = load_prompt(ARMS[arm].prompt)
    linhas = db.query(
        """SELECT e.raw_output, e.xsd_valid, s.raw_text
           FROM benchmark_eval e JOIN samples s ON s.id = e.sample_id
           WHERE e.arm = ?"""
        + not_leaked("e.sample_id"),
        (arm,),
    )
    n = lambda texto: len(tok.encode(texto))  # noqa: E731
    return {
        "n": len(linhas),
        "t_in": st.mean(n(prompt.replace("{description}", r["raw_text"] or "")) for r in linhas),
        "t_out": st.mean(n(r["raw_output"] or "") for r in linhas),
        "t_prefixo": n(prefixo_fixo(prompt)),
        "validade": sum(r["xsd_valid"] or 0 for r in linhas) / len(linhas),
    }


def linhas_de_custo(arm: str, m: dict) -> list[dict]:
    saida = []
    for nome in CENARIOS[arm]:
        preco = PRECOS[nome]
        variantes = [("sem cache", 0.0)]
        if preco["cache"] is not None:
            variantes.append(("com cache", m["t_prefixo"]))
        for rotulo, t_cache in variantes:
            c = custo(m["t_in"], m["t_out"], preco, t_cache)
            saida.append(
                {
                    "braco": arm,
                    "cenario": f"{nome} ({rotulo})",
                    "por_1M": c * POR_REQUISICOES,
                    # Sem saída válida o custo por válida não é definido (A3m).
                    "por_1M_validas": (
                        c / m["validade"] * POR_REQUISICOES if m["validade"] else None
                    ),
                }
            )
    return saida


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--arms", nargs="+", default=list(CENARIOS))
    args = p.parse_args()

    from src.evaluation.run_tcr import TOKENIZER, _tokenizer

    tok = _tokenizer(TOKENIZER)
    print(f"preços de {DATA_PRECOS}; tokenizador {TOKENIZER}\n")
    print(f"{'braço':6} | {'entrada':>7} | {'saída':>5} | {'prefixo':>7} | válidas")
    medidas = {}
    with Database() as db:
        for arm in args.arms:
            m = medidas[arm] = medir_braco(db, arm, tok)
            print(
                f"{arm:6} | {m['t_in']:7.0f} | {m['t_out']:5.0f} | {m['t_prefixo']:7d}"
                f" | {m['validade']:.1%}"
            )
    print(f"\n{'braço':6} | {'cenário':32} | US$/1M req. | US$/1M válidas")
    for arm in args.arms:
        for li in linhas_de_custo(arm, medidas[arm]):
            print(
                f"{li['braco']:6} | {li['cenario']:32} | {li['por_1M']:11.0f}"
                f" | {'---' if li['por_1M_validas'] is None else f'{li["por_1M_validas"]:.0f}':>14}"
            )


if __name__ == "__main__":
    main()
