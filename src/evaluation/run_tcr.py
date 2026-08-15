"""TCR — razão de compressão de tokens, conforme spec 003 §3.3.

TCR = tokens(XML lógico) / tokens(DSL), tokenizador Qwen2.5-Coder-7B.
Valores > 1 indicam DSL mais compacta; redução derivada = 1 - 1/TCR.

O XML do numerador é o XML **lógico** (sem BPMNDI). Medir contra XML com layout
infla o resultado em ~3x sem acrescentar semântica — ver spec 003 §3.3.
`--with-layout` existe apenas para demonstrar esse viés, não para reportar.

Dois modos, com **a mesma definição** de TCR — por isso vivem no mesmo módulo:

    corpus   sobre `xml_transpiler_runs` (a base de treino). É o 6,01 da tese.
    braço    sobre `benchmark_eval` (as saídas do experimento). É a H4 da §6.1.

Requer o extra `training` (transformers):

    uv run --with transformers python -m src.evaluation.run_tcr
    uv run --with transformers python -m src.evaluation.run_tcr --arm A2
    uv run --with transformers python -m src.evaluation.run_tcr --all-arms
"""

from __future__ import annotations

import argparse
import random
import statistics as st

from src.data.db import Database

# Base ativa. Estes defaults ficaram apontando para a base PT antiga (v8/v3) e o
# comando sem argumentos media o corpus obsoleto: 5,08 em vez de 6,01. Ao trocar
# a base ativa, atualizar aqui — o número vai para a monografia.
DEFAULT_SOURCE_DSL_VERSION = "json_to_dsl_v10_en"
DEFAULT_XML_TRANSPILER_VERSION = "dsl_to_xml_v5_en"
TOKENIZER = "Qwen/Qwen2.5-Coder-7B"
BOOTSTRAP_N = 10_000
SEED = 42


def _tokenizer(name: str):
    try:
        from transformers import AutoTokenizer
    except ImportError as exc:  # pragma: no cover - depende do extra `training`
        raise SystemExit(
            "transformers não instalado. Use: uv run --with transformers python -m "
            "src.evaluation.run_tcr"
        ) from exc
    return AutoTokenizer.from_pretrained(name)


def _ci95(values: list[float], n: int = BOOTSTRAP_N) -> tuple[float, float]:
    """IC95% da média por bootstrap, seed fixa para reprodutibilidade."""
    rng = random.Random(SEED)
    means = sorted(st.mean(rng.choices(values, k=len(values))) for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n)]


BPMN_DI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"


def strip_di(xml_text: str) -> str:
    """Remove `BPMNDiagram` — a TCR é normativamente definida sobre XML lógico.

    Hoje `xml_transpiler_runs.output_xml` já é lógico, então isto é identidade.
    Existe como defesa (AC-4): se o layout algum dia for materializado nessa
    coluna — risco registrado no TODO —, sem esta remoção a TCR inflaria cerca
    de 3x em silêncio. É exatamente o erro dos "91%", já cometido uma vez.
    """
    from lxml import etree

    try:
        raiz = etree.fromstring(xml_text.encode("utf-8"))
    except etree.XMLSyntaxError:
        return xml_text  # medir o texto cru é melhor que descartar a amostra
    diagramas = raiz.findall(f"{{{BPMN_DI_NS}}}BPMNDiagram")
    if not diagramas:
        return xml_text
    for d in diagramas:
        raiz.remove(d)
    return etree.tostring(raiz, encoding="unicode")


def ratios(rows: list[dict], tok, *, with_layout: bool) -> list[float]:
    from src.transpiler.layout import add_layout

    out = []
    for row in rows:
        dsl_tokens = len(tok(row["input_dsl"], add_special_tokens=False)["input_ids"])
        if not dsl_tokens:
            continue
        xml = add_layout(row["output_xml"]) if with_layout else strip_di(row["output_xml"])
        out.append(len(tok(xml, add_special_tokens=False)["input_ids"]) / dsl_tokens)
    return out


def arm_report(db: Database, arm: str, tok) -> dict:
    """TCR e tokens emitidos de um braço do benchmark (spec 003 §6.1, H4).

    **Tokens emitidos** é a grandeza econômica e existe em todo braço: é o que o
    modelo teve de produzir. Comparável entre braços item a item — é ela que
    sustenta a alegação de custo, não a TCR.

    **TCR** só é definida onde há representação intermediária: nos braços de DSL
    é `tokens(XML reconstituído) / tokens(DSL emitida)`. Nos braços que emitem
    XML direto não há compressão a medir — a razão seria 1 por construção, e
    reportá-la como se fosse resultado confundiria o leitor.

    Linhas com falha de geração ou de transpilação ficam de fora da TCR (não há
    o que medir) mas entram na contagem, para que a taxa apareça no relatório.
    """
    from src.evaluation.run_benchmark import ARMS, strip_fence

    emite_dsl = ARMS[arm].emits == "dsl"
    linhas = [
        dict(r)
        for r in db.query(
            "SELECT sample_id, raw_output, output_xml FROM benchmark_eval WHERE arm = ?",
            (arm,),
        )
    ]
    if not linhas:
        return {"braço": arm, "estado": "sem dados"}

    n_tokens = lambda t: len(tok(t, add_special_tokens=False)["input_ids"])  # noqa: E731
    emitidos, razoes, descartadas = [], [], 0
    for linha in linhas:
        bruto = strip_fence(linha["raw_output"] or "")
        if not bruto:
            descartadas += 1
            continue
        saida = n_tokens(bruto)
        emitidos.append(saida)
        if emite_dsl and linha["output_xml"] and saida:
            razoes.append(n_tokens(strip_di(linha["output_xml"])) / saida)

    relatorio = {
        "braço": arm,
        "emite": ARMS[arm].emits,
        "n": len(linhas),
        "sem_saida": descartadas,
        "tokens_emitidos_mediana": round(st.median(emitidos), 1) if emitidos else None,
        "tokens_emitidos_media": round(st.mean(emitidos), 1) if emitidos else None,
    }
    if razoes:
        media = st.mean(razoes)
        low, high = _ci95(razoes)
        relatorio |= {
            "tcr_mean": round(media, 2),
            "ci95": [round(low, 2), round(high, 2)],
            "tcr_median": round(st.median(razoes), 2),
            "reducao_pct": round((1 - 1 / media) * 100, 1),
            "n_tcr": len(razoes),
        }
    elif emite_dsl:
        relatorio["tcr"] = "sem transpilação bem-sucedida"
    else:
        relatorio["tcr"] = "não se aplica — braço emite XML direto"
    return relatorio


def run(args: argparse.Namespace) -> None:
    tok = _tokenizer(args.tokenizer)

    if args.arm or args.all_arms:
        from src.evaluation.run_benchmark import ARMS

        alvos = sorted(ARMS) if args.all_arms else [args.arm]
        with Database(read_only=True) as db:
            for braco in alvos:
                print(arm_report(db, braco, tok))
        return

    rows = Database().query(
        """SELECT sample_id, input_dsl, output_xml FROM xml_transpiler_runs
           WHERE status='succeeded' AND source_dsl_version=?
             AND xml_transpiler_version=?""",
        (args.source_dsl_version, args.xml_transpiler_version),
    )
    if not rows:
        raise SystemExit("nenhum par encontrado para as versões informadas")

    values = ratios([dict(r) for r in rows], tok, with_layout=args.with_layout)
    mean = st.mean(values)
    low, high = _ci95(values)
    print(
        {
            "denominador": "XML com BPMNDI (viés — não reportar)"
            if args.with_layout
            else "XML lógico",
            "n": len(values),
            "tcr_mean": round(mean, 2),
            "ci95": [round(low, 2), round(high, 2)],
            "tcr_median": round(st.median(values), 2),
            "reducao_pct": round((1 - 1 / mean) * 100, 1),
        }
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-dsl-version", default=DEFAULT_SOURCE_DSL_VERSION)
    p.add_argument("--xml-transpiler-version", default=DEFAULT_XML_TRANSPILER_VERSION)
    p.add_argument("--tokenizer", default=TOKENIZER)
    p.add_argument(
        "--with-layout",
        action="store_true",
        help="Mede contra XML com BPMNDI para demonstrar o viés. Não usar em relatório.",
    )
    p.add_argument("--arm", help="Mede sobre as saídas deste braço, não sobre o corpus.")
    p.add_argument("--all-arms", action="store_true", help="Relatório de todos os braços.")
    return p.parse_args()


if __name__ == "__main__":
    run(parse_args())
