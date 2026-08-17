"""Exporta os dados das figuras da monografia como CSV.

Os `.tex` das figuras leem estes arquivos via pgfplots, de modo que reexecutar
um braço e rodar este script regenera as figuras sem edição manual — nenhum
número é transcrito à mão para o documento.

Uso:
    uv run python -m src.evaluation.export_figuras
"""

from __future__ import annotations

import argparse
import collections
import statistics as st
import warnings
from collections import Counter
from pathlib import Path

from src.data.db import Database
from src.evaluation.run_benchmark import MIN_REF_SCORE, per_item_medians
from src.evaluation.topology import (
    _prf,
    align_labels,
    xml_direct_follows,
)

BRACOS = ["A1", "A1g", "A2", "A2g", "A3", "A3m", "A4"]
EMITE = {
    "A1": "xml",
    "A1g": "xml",
    "A2": "dsl",
    "A2g": "dsl",
    "A3": "dsl",
    "A3m": "dsl",
    "A4": "dsl",
}
LIMIARES = [0.5, 0.4, 0.3, 0.2, 0.1, 0.01]
# Perdas de validação do SFT (época 1, 2, 3). O treino rodou em nuvem e o
# `log_history` completo se perdeu com o pod; estes três valores vêm dos
# `trainer_state.json` dos checkpoints e são o critério de parada.
EVAL_SFT = [(1, 0.4402), (2, 0.4160), (3, 0.4216)]


def escrever(caminho: Path, cabecalho: str, linhas: list[str]) -> None:
    caminho.write_text(cabecalho + "\n" + "\n".join(linhas) + "\n", encoding="utf-8")
    print(f"  {caminho.name:24s} {len(linhas)} linhas")


def _rotulos(df: Counter) -> set[str]:
    return {x for par in df for x in par}


def f1_no_limiar(limiar: float, ref_xml: str, cand_xml: str) -> float:
    """DF-F1 recalculado com outro limiar de casamento de rótulos.

    Só para a figura de sensibilidade: o valor congelado do protocolo é 0,5, e
    os demais pontos existem para mostrar que a métrica satura, não para
    substituir o número primário.

    XML malformado pontua **zero**, como em `compare_xml`. Sem isso, as gerações
    truncadas dos braços de XML — que são justamente as piores — sairiam da
    média em vez de entrar como zero, e a figura mostraria o baseline melhor do
    que a tabela (medido: A1 subia de 0,1942 para 0,2070).
    """
    try:
        dr, _ = xml_direct_follows(ref_xml)
        dc, _ = xml_direct_follows(cand_xml)
    except Exception:
        return 0.0
    mapa = align_labels(_rotulos(dr), _rotulos(dc), limiar)
    traduz = mapa.get
    reescrito = Counter({(traduz(a, a), traduz(b, b)): n for (a, b), n in dc.items()})
    return _prf(dr, reescrito)[2]


def teto_humano(refs: dict[str, list[str]], limiar: float) -> float:
    """Concordância entre referências de especialista, mesma régua dos braços.

    Pares exatamente idênticos são descartados: em 17 dos 24 itens a referência
    primária coincide com uma das alternativas (mesma fonte), e mantê-los
    mediria autocomparação.
    """
    por_item = []
    for xs in refs.values():
        notas = []
        for i, x in enumerate(xs):
            vs = [f1_no_limiar(limiar, y, x) for j, y in enumerate(xs) if j != i]
            vs = [v for v in vs if v < 1.0] or [0.0]
            notas.append(max(vs))
        if notas:
            por_item.append(st.mean(notas))
    return st.mean(por_item) if por_item else 0.0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    # Dentro da raiz do documento LaTeX: o pgfplots resolve o caminho da tabela
    # relativo a `main.tex`, não ao diretório do projeto.
    p.add_argument("--out", default="article/Atualização Template TCC Unifor 2022.2/figuras/dados")
    args = p.parse_args()
    warnings.simplefilter("ignore")

    destino = Path(args.out)
    destino.mkdir(parents=True, exist_ok=True)

    with Database() as db:
        medianas = {a: per_item_medians(db, a) for a in BRACOS}
        # Mesma regra de admissão de `run_benchmark.references()`: primária do
        # PMo mais alternativas com nota ≥ MIN_REF_SCORE. Usar todas as linhas
        # de `gold_models` fazia a figura divergir da tabela.
        refs: dict[str, list[str]] = collections.defaultdict(list)
        for r in db.query(
            "SELECT sample_id, gold_xml FROM gold_models"
            " WHERE score IS NULL OR score >= ? ORDER BY variant",
            (MIN_REF_SCORE,),
        ):
            refs[r["sample_id"]].append(r["gold_xml"])

        validade, custo = [], []
        for a in BRACOS:
            linha = db.query(
                """SELECT COUNT(*) n, SUM(COALESCE(parse_ok,1)) p, SUM(xsd_valid) x
                   FROM benchmark_eval WHERE arm = ?""",
                (a,),
            )[0]
            n = linha["n"] or 1
            f1 = st.mean(medianas[a].values()) if medianas[a] else 0.0
            pct_parse = 100 * (linha["p"] or 0) / n
            pct_xsd = 100 * (linha["x"] or 0) / n
            validade.append(f"{a},{pct_parse:.1f},{pct_xsd:.1f},{EMITE[a]}")
            custo.append((a, f1, pct_xsd))

        # Tokens emitidos: mesma medição da TCR (§Eixo 4), com o tokenizador do
        # modelo base. Contagem de palavras não serve — a grandeza econômica é
        # token, e a razão entre notações não sobrevive à aproximação.
        from src.evaluation.run_tcr import TOKENIZER, _tokenizer, arm_report

        tok = _tokenizer(TOKENIZER)
        toks = {a: arm_report(db, a, tok).get("tokens_emitidos_mediana", 0) for a in BRACOS}

        multi = {s: v for s, v in refs.items() if len(v) >= 3}
        # Todos os 53 itens, saída inválida contando zero — idêntico ao critério
        # da métrica primária. Restringir aos válidos inflaria os braços de DSL
        # (A2 subiria de 0,1375 para 0,23) e a figura deixaria de ser comparável
        # com a tabela principal.
        # As três réplicas, agregadas por mediana no item — a mesma unidade de
        # análise da tabela principal. Usar só a réplica 1 fazia a figura
        # divergir do texto nos braços em nuvem, que não são determinísticos.
        candidatos: dict[str, dict[str, list[str | None]]] = {}
        for a in ("A1", "A2", "A4"):
            porsample: dict[str, list[str | None]] = collections.defaultdict(list)
            for r in db.query(
                "SELECT sample_id, output_xml FROM benchmark_eval WHERE arm = ? ORDER BY rep",
                (a,),
            ):
                porsample[r["sample_id"]].append(r["output_xml"])
            candidatos[a] = dict(porsample)

    escrever(destino / "validade.csv", "braco,parse,xsd,emite", validade)
    escrever(
        destino / "df_f1.csv",
        "braco,df_f1,emite",
        [f"{a},{st.mean(medianas[a].values()):.4f},{EMITE[a]}" for a in BRACOS if medianas[a]],
    )
    escrever(
        destino / "custo.csv",
        "braco,df_f1,xsd,tokens",
        [f"{a},{f1:.4f},{x:.1f},{toks[a]:.0f}" for a, f1, x in custo],
    )
    escrever(destino / "sft_eval.csv", "epoca,eval_loss", [f"{e},{v:.4f}" for e, v in EVAL_SFT])

    print("  calculando sensibilidade ao limiar (pode levar ~1 min)…")
    linhas = []
    for limiar in LIMIARES:
        col = [f"{limiar}"]
        for a in ("A1", "A2", "A4"):
            vs = [
                st.median(
                    [max(f1_no_limiar(limiar, g, x) for g in refs[s]) if x else 0.0 for x in reps]
                )
                for s, reps in candidatos[a].items()
                if s in refs
            ]
            col.append(f"{st.mean(vs):.4f}" if vs else "0")
        col.append(f"{teto_humano(multi, limiar):.4f}")
        linhas.append(",".join(col))
    escrever(destino / "limiar.csv", "limiar,A1,A2,A4,teto", linhas)


if __name__ == "__main__":
    main()
