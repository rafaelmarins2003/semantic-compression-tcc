"""Tabelas complementares de `resultados.tex` que não saem de `run_analysis`.

Três recortes descritivos foram digitados à mão na monografia e, quando os dados
mudaram (correção do `xs:ID` em 2026-08-25), não havia como recalculá-los sem
reconstruir o método por arqueologia. Este módulo fixa as três definições.

Uso: uv run python -m src.evaluation.run_tabelas
"""

import argparse
import statistics as st

from src.data.db import Database
from src.evaluation.export_figuras import per_item_medians, teto_humano
from src.evaluation.run_benchmark import MIN_REF_SCORE, references
from src.evaluation.topology import (
    LABEL_MATCH_THRESHOLD,
    activity_labels,
    compare_xml,
    label_alignment,
    normalize_label,
    xml_direct_follows,
)


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


def referencias_multiplas(db) -> dict[str, list[str]]:
    """Os 24 itens com mais de uma referência **admitida** (nota ≥ 4).

    Contar toda linha de `gold_models` daria o mesmo conjunto hoje, por acidente
    dos dados: as reprovadas estão em itens que já têm várias aprovadas. A regra
    correta é a de admissão, a mesma de `run_benchmark.references`.
    """
    por_item: dict[str, list[str]] = {}
    for r in db.query(
        "SELECT sample_id, gold_xml FROM gold_models"
        " WHERE score IS NULL OR score >= ? ORDER BY variant",
        (MIN_REF_SCORE,),
    ):
        por_item.setdefault(r["sample_id"], []).append(r["gold_xml"])
    return {s: v for s, v in por_item.items() if len(v) >= 2}


def teto(db, bracos: list[str]) -> list[dict]:
    """DF-F1 restrito aos itens com referência múltipla, comparável ao teto humano.

    O teto foi medido entre especialistas nesses mesmos itens; usar os 53 tornaria
    as linhas incomparáveis — foi o que a `fig:df-f1-teto` fez até 30/08, exibindo
    barras de 53 itens sob uma linha de teto de 24.

    O próprio teto é **calculado**, e não constante: era o último número derivado
    do capítulo que vivia como literal no código.
    """
    multi = referencias_multiplas(db)
    valor_teto = teto_humano(multi, LABEL_MATCH_THRESHOLD)
    linhas = [{
        "origem": "teto humano", "n": len(multi),
        "df_f1": round(valor_teto, 4), "%_do_teto": "---",
    }]  # fmt: skip

    def linha(origem: str, medianas: dict[str, float]) -> dict:
        ids = [i for i in medianas if i in multi]
        v = st.mean(medianas[i] for i in ids)
        return {
            "origem": origem, "n": len(ids), "df_f1": round(v, 4),
            "%_do_teto": f"{100 * v / valor_teto:.0f}%",
        }  # fmt: skip

    linhas += [linha(a, per_item_medians(db, a)) for a in bracos]

    pipeline = {}
    for s in db.query("SELECT id, xml FROM samples WHERE source='pmo' AND xml IS NOT NULL"):
        if s["id"] in multi:
            pipeline[s["id"]] = max(compare_xml(g, s["xml"])["df_f1"] for g in multi[s["id"]])
    linhas.append(linha("pipeline de augmentation", pipeline))
    return sorted(linhas, key=lambda r: -r["df_f1"])


def _arestas(xml_text: str) -> int:
    """Tamanho do multiconjunto direct-follows — a contagem de arestas."""
    return sum(xml_direct_follows(xml_text)[0].values())


def _por_item(valores: dict[str, list[float]], agregado) -> float | None:
    """Mediana das repetições por item, depois `agregado` entre os itens."""
    medianas = [st.median(v) for v in valores.values() if v]
    return agregado(medianas) if medianas else None


def oraculo(db, bracos: list[str]) -> list[dict]:
    """tab:res-oraculo: a DSL do próprio pipeline contra o gold, ao lado dos braços.

    Três colunas com convenções distintas e declaradas, porque medem coisas
    distintas:

    * **DF-F1** segue a regra congelada — máximo sobre as referências admitidas,
      geração inválida conta zero.
    * **Rótulos alinhados** e **arestas** são calculados **só sobre as gerações
      válidas**: documento que não existe não tem rótulo nem aresta a comparar, e
      zerá-lo faria a coluna medir validade, que é o que a primeira já mede.

    A tabela existe para localizar o déficit do pipeline (estrutura? vocabulário?),
    e misturar validade nas colunas de diagnóstico esconderia exatamente isso.
    """
    gold = {
        r["sample_id"]: r["gold_xml"]
        for r in db.query("SELECT sample_id, gold_xml FROM gold_models WHERE variant='primary'")
    }
    refs = {sid: {r["variant"]: r["gold_xml"] for r in references(db, sid)} for sid in gold}

    linhas = [{
        "origem": "gold (referência)", "df_f1": None, "rótulos": None,
        "arestas": st.median(_arestas(x) for x in gold.values()), "n": len(gold),
    }]  # fmt: skip

    for a in bracos:
        rot: dict[str, list[float]] = {}
        arestas: dict[str, list[float]] = {}
        n_ref: dict[str, list[float]] = {}
        n_cand: dict[str, list[float]] = {}
        for r in db.query(
            "SELECT sample_id, output_xml, ref_variant, xsd_valid FROM benchmark_eval WHERE arm=?",
            (a,),
        ):
            if not (r["xsd_valid"] and r["output_xml"] and r["ref_variant"]):
                continue
            sid, ref_xml = r["sample_id"], refs[r["sample_id"]][r["ref_variant"]]
            rot.setdefault(sid, []).append(label_alignment(ref_xml, r["output_xml"]))
            arestas.setdefault(sid, []).append(_arestas(r["output_xml"]))
            n_ref.setdefault(sid, []).append(len(activity_labels(ref_xml)))
            n_cand.setdefault(sid, []).append(len(activity_labels(r["output_xml"])))
        linhas.append({
            "origem": a, "df_f1": round(st.mean(per_item_medians(db, a).values()), 4),
            "rótulos": round(_por_item(rot, st.mean), 3),
            "arestas": _por_item(arestas, st.median), "n": len(rot),
            "n_rótulos_ref": _por_item(n_ref, st.median),
            "n_rótulos_cand": _por_item(n_cand, st.median),
        })  # fmt: skip

    vals, aux = [], []
    for s in db.query("SELECT id, xml FROM samples WHERE source='pmo' AND xml IS NOT NULL"):
        admitidas = list(refs[s["id"]].values())
        melhor = max(admitidas, key=lambda g: compare_xml(g, s["xml"])["df_f1"])
        vals.append(compare_xml(melhor, s["xml"])["df_f1"])
        aux.append((label_alignment(melhor, s["xml"]), _arestas(s["xml"])))
    linhas.append({
        "origem": "pipeline de augmentation", "df_f1": round(st.mean(vals), 4),
        "rótulos": round(st.mean(r for r, _ in aux), 3),
        "arestas": st.median(e for _, e in aux), "n": len(aux),
    })  # fmt: skip
    return linhas


def teto_rotulos(db) -> dict:
    """Concordância de **rótulos** entre especialistas — o par do teto de DF-F1.

    Mesma regra do `teto_humano`: cada referência é candidata contra a que mais
    a favorece, pares idênticos descartados. É o parâmetro contra o qual a coluna
    de rótulos da `tab:res-oraculo` deve ser lida.
    """
    por_sample: dict[str, list[str]] = {}
    for r in db.query(
        "SELECT sample_id, gold_xml FROM gold_models WHERE score IS NULL OR score >= ?",
        (MIN_REF_SCORE,),
    ):
        por_sample.setdefault(r["sample_id"], []).append(r["gold_xml"])

    itens = []
    for xs in por_sample.values():
        if len(xs) < 2:
            continue
        notas = []
        for i, x in enumerate(xs):
            # Empate resolvido pela primeira referência, como em `score_candidate`
            # (comparação estrita): o desempate faz diferença de quase um ponto
            # percentual, então não pode ficar por conta da ordem de iteração.
            melhor = None
            for j, y in enumerate(xs):
                if i == j:
                    continue
                f1 = compare_xml(y, x)["df_f1"]
                if f1 < 1.0 and (melhor is None or f1 > melhor[0]):
                    melhor = (f1, y)
            if melhor:
                notas.append(label_alignment(melhor[1], x))
        if notas:
            itens.append(st.mean(notas))
    return {"teto_de_rótulos": round(st.mean(itens), 3), "itens": len(itens)}


def ancoragem(db, bracos: list[str]) -> list[dict]:
    """Proporção das palavras do rótulo que ocorrem no texto de origem.

    Responde à suspeita de que os dois saltos de LLM do pipeline afastariam o
    vocabulário da descrição original. Mede-se a mesma coisa na referência
    humana, que é o parâmetro: se o especialista também não copia palavras do
    texto, afastar-se dele não é defeito do pipeline.
    """
    fonte = {
        r["id"]: set(normalize_label(r["raw_text"]).split())
        for r in db.query("SELECT id, raw_text FROM samples WHERE source='pmo'")
    }

    def taxa(xml_text: str, sid: str) -> float | None:
        palavras = [p for r in activity_labels(xml_text) for p in normalize_label(r).split()]
        return sum(p in fonte[sid] for p in palavras) / len(palavras) if palavras else None

    linhas = []
    for r in db.query("SELECT sample_id, gold_xml FROM gold_models WHERE variant='primary'"):
        linhas.append(taxa(r["gold_xml"], r["sample_id"]))
    saida = [{"origem": "gold (referência)", "ancoragem": round(st.mean(filtrar(linhas)), 3)}]

    for a in bracos:
        por_item: dict[str, list[float]] = {}
        for r in db.query(
            "SELECT sample_id, output_xml, xsd_valid FROM benchmark_eval WHERE arm=?", (a,)
        ):
            if r["xsd_valid"] and r["output_xml"]:
                v = taxa(r["output_xml"], r["sample_id"])
                if v is not None:
                    por_item.setdefault(r["sample_id"], []).append(v)
        saida.append({"origem": a, "ancoragem": round(_por_item(por_item, st.mean), 3)})

    vals = [
        taxa(s["xml"], s["id"])
        for s in db.query("SELECT id, xml FROM samples WHERE source='pmo' AND xml IS NOT NULL")
    ]
    saida.append({
        "origem": "pipeline de augmentation", "ancoragem": round(st.mean(filtrar(vals)), 3),
    })  # fmt: skip
    return saida


def filtrar(vs: list[float | None]) -> list[float]:
    return [v for v in vs if v is not None]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--arms", nargs="+", default=["A1", "A1g", "A2", "A2g", "A3", "A3m", "A4"])
    args = p.parse_args()

    with Database() as db:
        print("=== Contraste condicional (exploratório, tab:res-condicional) ===")
        for par in [("A2", "A1"), ("A2g", "A1g")]:
            for linha in contraste_condicional(db, *par):
                print(linha)
        print("\n=== MF-F1 (tab:res-mf) ===")
        for linha in mf_f1(db, args.arms):
            print(linha)
        print("\n=== DF-F1 vs teto humano (tab:res-teto) ===")
        for linha in teto(db, args.arms):
            print(linha)
        print(teto_rotulos(db))
        print("\n=== Oráculo do pipeline (tab:res-oraculo) ===")
        for linha in oraculo(db, ["A1", "A2", "A4"]):
            print(linha)
        print("\n=== Ancoragem no texto de origem (§5.6.9) ===")
        for linha in ancoragem(db, ["A1"]):
            print(linha)


if __name__ == "__main__":
    main()
