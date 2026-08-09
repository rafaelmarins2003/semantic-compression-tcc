"""TCR — razão de compressão de tokens, conforme spec 003 §3.3.

TCR = tokens(XML lógico) / tokens(DSL), tokenizador Qwen2.5-Coder-7B.
Valores > 1 indicam DSL mais compacta; redução derivada = 1 - 1/TCR.

O XML do numerador é o XML **lógico** (sem BPMNDI). Medir contra XML com layout
infla o resultado em ~3x sem acrescentar semântica — ver spec 003 §3.3.
`--with-layout` existe apenas para demonstrar esse viés, não para reportar.

Requer o extra `training` (transformers):
    uv run --with transformers python -m src.evaluation.run_tcr
"""

from __future__ import annotations

import argparse
import random
import statistics as st

from src.data.db import Database

DEFAULT_SOURCE_DSL_VERSION = "json_to_dsl_v8"
DEFAULT_XML_TRANSPILER_VERSION = "dsl_to_xml_v3"
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


def ratios(rows: list[dict], tok, *, with_layout: bool) -> list[float]:
    from src.transpiler.layout import add_layout

    out = []
    for row in rows:
        dsl_tokens = len(tok(row["input_dsl"], add_special_tokens=False)["input_ids"])
        if not dsl_tokens:
            continue
        xml = add_layout(row["output_xml"]) if with_layout else row["output_xml"]
        out.append(len(tok(xml, add_special_tokens=False)["input_ids"]) / dsl_tokens)
    return out


def run(args: argparse.Namespace) -> None:
    rows = Database().query(
        """SELECT sample_id, input_dsl, output_xml FROM xml_transpiler_runs
           WHERE status='succeeded' AND source_dsl_version=?
             AND xml_transpiler_version=?""",
        (args.source_dsl_version, args.xml_transpiler_version),
    )
    if not rows:
        raise SystemExit("nenhum par encontrado para as versões informadas")

    tok = _tokenizer(args.tokenizer)
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
    return p.parse_args()


if __name__ == "__main__":
    run(parse_args())
