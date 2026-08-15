"""Análise estatística dos braços (spec 003 §6.3).

**Escrito antes de qualquer braço rodar.** Análise redigida depois de ver os
resultados pode ser ajustada a eles — escolher o teste, a lateralidade ou o
conjunto de contrastes em função do que favorece a hipótese é exatamente o que o
pré-registro existe para impedir. Este módulo fixa tudo isso em código.

    uv run python -m src.evaluation.run_analysis
    uv run python -m src.evaluation.run_analysis --metric df_strict_f1
"""

from __future__ import annotations

import argparse
import random
import statistics as st

from scipy.stats import wilcoxon

from src.data.db import Database
from src.evaluation.run_benchmark import ARMS, per_item_medians

# Contrastes **planejados**, fixados aqui para que a correção múltipla não vire
# pesca. Qualquer outro par é exploratório e reportado como tal (§6.3).
CONTRASTES = [("A2", "A1"), ("A2g", "A1g"), ("A4", "A2")]
EXPLORATORIOS = [("A4", "A3m"), ("A4", "A3"), ("A3", "A3m")]
BOOTSTRAP_N = 10_000
SEED = 42
ALPHA = 0.05


def pareado(a: dict[str, float], b: dict[str, float]) -> tuple[list[float], list[float]]:
    """Alinha dois braços pelos itens que ambos têm. A comparação é pareada."""
    comuns = sorted(set(a) & set(b))
    return [a[i] for i in comuns], [b[i] for i in comuns]


def bootstrap_ci(diferencas: list[float], n: int = BOOTSTRAP_N) -> tuple[float, float]:
    """IC95% da mediana das diferenças pareadas, semente fixa (§6.3)."""
    rng = random.Random(SEED)
    medianas = sorted(
        st.median(rng.choices(diferencas, k=len(diferencas))) for _ in range(n)
    )
    return medianas[int(0.025 * n)], medianas[int(0.975 * n)]


def rank_biserial(x: list[float], y: list[float]) -> float:
    """Correlação rank-biserial: acompanhante padrão do Wilcoxon pareado.

    Proporção de pares em que x supera y menos a proporção inversa. Varia de -1
    a 1 e não depende da escala, então é comparável entre métricas. Reportado
    porque com n = 53 o valor-p sozinho diz pouco (§6.3).
    """
    ganhos = sum(a > b for a, b in zip(x, y, strict=True))
    perdas = sum(a < b for a, b in zip(x, y, strict=True))
    total = ganhos + perdas
    return (ganhos - perdas) / total if total else 0.0


def holm(pvalores: list[float]) -> list[float]:
    """Correção de Holm, com imposição de monotonicidade.

    Preferida a Bonferroni por ser uniformemente mais poderosa mantendo o mesmo
    controle da taxa de erro familiar. Aplicada **apenas** aos três contrastes
    planejados; incluir os exploratórios diluiria o poder sem justificativa.
    """
    m = len(pvalores)
    ordenados = sorted(range(m), key=lambda i: pvalores[i])
    ajustados = [0.0] * m
    anterior = 0.0
    for posicao, indice in enumerate(ordenados):
        valor = min(1.0, (m - posicao) * pvalores[indice])
        anterior = ajustados[indice] = max(anterior, valor)
    return ajustados


def comparar(nome_a: str, nome_b: str, a: dict, b: dict) -> dict | None:
    """Wilcoxon pareado bilateral + tamanho de efeito + IC da diferença.

    **Bilateral**, embora H1/H1g/H3 sejam direcionais ("A2 ≥ A1"): a alegação é
    de não inferioridade, e quem a responde é o intervalo de confiança, não a
    lateralidade do teste. Bilateral é a escolha conservadora, e evita a suspeita
    de que a direção foi escolhida depois de ver os dados.
    """
    x, y = pareado(a, b)
    if not x:
        return None
    diferencas = [i - j for i, j in zip(x, y, strict=True)]
    nao_nulas = [d for d in diferencas if d != 0]
    if not nao_nulas:  # scipy levanta quando tudo empata
        p = 1.0
    else:
        p = float(wilcoxon(x, y, zero_method="wilcox", alternative="two-sided").pvalue)
    lo, hi = bootstrap_ci(diferencas)
    return {
        "contraste": f"{nome_a} vs {nome_b}",
        "n": len(x),
        f"mediana_{nome_a}": round(st.median(x), 4),
        f"mediana_{nome_b}": round(st.median(y), 4),
        "dif_mediana": round(st.median(diferencas), 4),
        "ic95": [round(lo, 4), round(hi, 4)],
        "efeito_rb": round(rank_biserial(x, y), 3),
        "empates": len(diferencas) - len(nao_nulas),
        "p": p,
    }


def descrever(db: Database, braco: str, metrica: str) -> dict | None:
    linhas = db.query(
        """SELECT COUNT(*) n, SUM(xsd_valid) xsd, SUM(COALESCE(parse_ok,1)) parse_ok,
                  SUM(truncated) truncadas, SUM(gen_error IS NOT NULL) erros
           FROM benchmark_eval WHERE arm = ?""",
        (braco,),
    )[0]
    if not linhas["n"]:
        return None
    medianas = per_item_medians(db, braco, metrica)
    espalhamento: dict[str, list[float]] = {}
    for r in db.query(f"SELECT sample_id, {metrica} v FROM benchmark_eval WHERE arm=?", (braco,)):
        espalhamento.setdefault(r["sample_id"], []).append(r["v"] or 0.0)
    amplitudes = [max(v) - min(v) for v in espalhamento.values() if len(v) > 1]
    return {
        "braço": braco,
        "gerações": linhas["n"],
        "itens": len(medianas),
        "xsd_%": round(100 * linhas["xsd"] / linhas["n"], 1),
        "parse_%": round(100 * linhas["parse_ok"] / linhas["n"], 1),
        "truncadas": linhas["truncadas"],
        "erros": linhas["erros"],
        f"{metrica}_mediana": round(st.mean(medianas.values()), 4) if medianas else None,
        "dispersão_máx": round(max(amplitudes), 4) if amplitudes else 0.0,
        "itens_divergentes": sum(a > 0 for a in amplitudes),
    }


def run(args: argparse.Namespace) -> None:
    with Database(read_only=True) as db:
        print(f"=== Descritivo por braço (métrica: {args.metric}) ===")
        disponiveis = {}
        for braco in ARMS:
            d = descrever(db, braco, args.metric)
            if d:
                disponiveis[braco] = per_item_medians(db, braco, args.metric)
                print(d)
            else:
                print({"braço": braco, "estado": "sem dados"})

        def bloco(titulo: str, pares: list[tuple[str, str]], corrigir: bool) -> None:
            print(f"\n=== {titulo} ===")
            achados = []
            for a, b in pares:
                if a in disponiveis and b in disponiveis:
                    r = comparar(a, b, disponiveis[a], disponiveis[b])
                    if r:
                        achados.append(r)
                else:
                    print({"contraste": f"{a} vs {b}", "estado": "braço ausente"})
            if corrigir and achados:
                for r, p in zip(achados, holm([r["p"] for r in achados]), strict=True):
                    r["p_holm"] = round(p, 5)
                    r["significativo"] = p < ALPHA
            for r in achados:
                r["p"] = round(r["p"], 5)
                print(r)

        bloco("Contrastes planejados (Holm sobre os três)", CONTRASTES, corrigir=True)
        bloco("Exploratórios — SEM correção, não confirmatórios", EXPLORATORIOS, corrigir=False)

        print(
            "\nNota: n = 53 é pequeno. Reportar tamanho de efeito e IC, não só o"
            " valor-p (§6.3). Resultado contrário às hipóteses é publicável (§6.1)."
        )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--metric", default="df_f1", help="df_f1 (primária) | df_strict_f1 | mf_f1")
    return p.parse_args()


if __name__ == "__main__":
    run(parse_args())
