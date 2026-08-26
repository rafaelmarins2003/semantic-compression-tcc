"""Tabelas complementares de `resultados.tex` que não saem de `run_analysis`.

Três recortes descritivos foram digitados à mão na monografia e, quando os dados
mudaram (correção do `xs:ID` em 2026-08-25), não havia como recalculá-los sem
reconstruir o método por arqueologia. Este módulo fixa as três definições.

Uso: uv run python -m src.evaluation.run_tabelas
"""

import argparse
import statistics as st

from src.data.db import Database
from src.evaluation.export_figuras import per_item_medians

TETO_HUMANO = 0.1449


def contraste_condicional(db, dsl: str, xml: str) -> list[dict]:
    """DF-F1 do par DSL/XML em todos os itens e só onde o braço DSL valida.

    Exploratório: condicionar em variável posterior à intervenção introduz viés
    de seleção. O recorte responde "quanto da desvantagem é perda de validade".
    """
    md, mx = per_item_medians(db, dsl), per_item_medians(db, xml)
    validos = {
        r["sample_id"]
        for r in db.query(
            "SELECT DISTINCT sample_id FROM benchmark_eval WHERE arm=? AND xsd_valid=1", (dsl,)
        )
    }
    todos = sorted(set(md) & set(mx))
    linhas = []
    for rotulo, ids in [("todos", todos), (f"só onde {dsl} valida", sorted(set(todos) & validos))]:
        d, x = st.mean(md[i] for i in ids), st.mean(mx[i] for i in ids)
        # A diferença publicada usa os valores já arredondados, para que o leitor
        # consiga refazer a subtração com o que está impresso na tabela.
        linhas.append({
            "recorte": f"{dsl} vs {xml} ({rotulo})", "n": len(ids),
            "dsl": round(d, 4), "xml": round(x, 4), "dif": round(round(d, 4) - round(x, 4), 4),
        })  # fmt: skip
    return linhas


def mf_f1(db, bracos: list[str]) -> list[dict]:
    """MF-F1 nos itens cuja referência primária tem `messageFlow` (hoje, dois)."""
    itens = [
        r["sample_id"]
        for r in db.query(
            "SELECT sample_id FROM gold_models"
            " WHERE variant='primary' AND gold_xml LIKE '%messageFlow%'"
        )
    ]
    marca = ",".join("?" * len(itens))
    linhas = []
    for a in bracos:
        rs = db.query(
            f"SELECT mf_f1, output_xml FROM benchmark_eval WHERE arm=? AND sample_id IN ({marca})",
            (a, *itens),
        )
        emitiram = sum(1 for r in rs if r["output_xml"] and "messageFlow" in r["output_xml"])
        linhas.append({
            "braço": a, "mf_f1": round(st.mean([r["mf_f1"] or 0.0 for r in rs]), 3),
            "emitiram": f"{emitiram}/{len(rs)}",
        })  # fmt: skip
    return linhas


def teto(db, bracos: list[str]) -> list[dict]:
    """DF-F1 restrito aos itens com referência múltipla, comparável ao teto humano.

    O teto foi medido entre especialistas nesses mesmos itens; usar os 53 tornaria
    as linhas incomparáveis.
    """
    multi = {
        r["sample_id"]
        for r in db.query("SELECT sample_id FROM gold_models GROUP BY sample_id HAVING COUNT(*)>1")
    }
    linhas = []
    for a in bracos:
        m = per_item_medians(db, a)
        ids = [i for i in m if i in multi]
        v = st.mean(m[i] for i in ids)
        linhas.append({
            "braço": a, "n": len(ids), "df_f1": round(v, 4),
            "%_do_teto": f"{100 * v / TETO_HUMANO:.0f}%",
        })  # fmt: skip
    return linhas


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--arms", nargs="+", default=["A1", "A1g", "A2", "A2g", "A3"])
    args = p.parse_args()

    with Database() as db:
        print("=== Contraste condicional (exploratório, tab:res-condicional) ===")
        for par in [("A2", "A1"), ("A2g", "A1g")]:
            for linha in contraste_condicional(db, *par):
                print(linha)
        print("\n=== MF-F1 (tab:res-mf) ===")
        for linha in mf_f1(db, args.arms):
            print(linha)
        print(f"\n=== DF-F1 vs teto humano {TETO_HUMANO} (tab:res-teto) ===")
        for linha in teto(db, args.arms):
            print(linha)


if __name__ == "__main__":
    main()
