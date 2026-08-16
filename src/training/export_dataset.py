"""Exporta o conjunto de SFT para JSONL — pares (prompt do A4, DSL de destino).

Duas garantias que este módulo existe para dar:

1. **O prompt é o mesmo do braço A4.** Carrega `benchmark/dsl_minimal.md` do
   mesmo arquivo versionado que o harness usa e grava seu `sha256` no manifesto.
   Divergência entre prompt de treino e de inferência colocaria o modelo fora da
   distribuição em avaliação, e o efeito seria creditado ao método.

2. **A validação é agrupada por documento de origem.** 95,3% do treino vem de um
   mesmo handbook, com várias seções por arquivo e redação templatizada. Corte
   aleatório colocaria seções irmãs dos dois lados e a perda de validação
   mediria memorização, não generalização — inutilizando o critério de parada.

Exemplos:
    uv run python -m src.training.export_dataset
    uv run python -m src.training.export_dataset --val-frac 0.15 --out experiments/sft
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from src.data.db import Database
from src.data.llm.utils import load_prompt

PROMPT = "benchmark/dsl_minimal.md"
DSL_VERSION = "json_to_dsl_v10_en"
VAL_FRAC = 0.10
SEQ_LIMIT = 4096  # ver metodologia §Ajuste Supervisionado: 1024 truncaria 98%


def pares(db: Database) -> list[dict]:
    """Pares de alta confiança: equivalência topológica exata no eixo 2.

    `df_exact=1` é o filtro de qualidade — treinar sobre par cuja DSL não
    reconstrói o processo de origem ensinaria o erro junto com o formato.
    """
    sql = """
        SELECT s.id, s.source, s.raw_text, s.dsl, s.metadata
        FROM samples s
        JOIN topology_eval t ON t.sample_id = s.id
        WHERE s.split = 'sft' AND t.df_exact = 1 AND t.source_dsl_version = ?
          AND s.raw_text IS NOT NULL AND s.dsl IS NOT NULL
        GROUP BY s.id
        ORDER BY s.id
    """
    return [dict(r) for r in db.query(sql, (DSL_VERSION,))]


def grupo(linha: dict) -> str:
    """Documento de origem — a unidade que não pode cruzar treino/validação."""
    try:
        arquivo = (json.loads(linha["metadata"] or "{}") or {}).get("source_file")
    except (json.JSONDecodeError, TypeError):
        arquivo = None
    return f"{linha['source']}:{arquivo or linha['id']}"


def dividir(linhas: list[dict], val_frac: float) -> tuple[list[dict], list[dict]]:
    """Split por grupo, determinístico.

    A ordem vem do sha1 do nome do grupo, não de RNG: o mesmo comando em outra
    máquina precisa produzir o mesmo par de arquivos, senão a época escolhida
    deixa de ser reproduzível.
    """
    porgrupo: dict[str, list[dict]] = {}
    for linha in linhas:
        porgrupo.setdefault(grupo(linha), []).append(linha)

    ordem = sorted(porgrupo, key=lambda g: hashlib.sha1(g.encode()).hexdigest())
    alvo = int(len(linhas) * val_frac)
    val_grupos: set[str] = set()
    acumulado = 0
    for g in ordem:
        if acumulado >= alvo:
            break
        val_grupos.add(g)
        acumulado += len(porgrupo[g])

    treino = [x for g, xs in porgrupo.items() if g not in val_grupos for x in xs]
    val = [x for g, xs in porgrupo.items() if g in val_grupos for x in xs]
    return sorted(treino, key=lambda x: x["id"]), sorted(val, key=lambda x: x["id"])


def exemplo(linha: dict, gabarito: str) -> dict:
    return {
        "id": linha["id"],
        "source": linha["source"],
        "group": grupo(linha),
        "prompt": gabarito.replace("{description}", linha["raw_text"]),
        "completion": linha["dsl"].strip(),
    }


def escrever(caminho: Path, exemplos: list[dict]) -> None:
    caminho.write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in exemplos), encoding="utf-8"
    )


def estatisticas(exemplos: list[dict], tok) -> dict:
    """Comprimentos em tokens. Sem tokenizador, devolve só a contagem."""
    if tok is None:
        return {"n": len(exemplos)}
    comp = [
        len(tok(e["prompt"], add_special_tokens=False)["input_ids"])
        + len(tok(e["completion"], add_special_tokens=False)["input_ids"])
        for e in exemplos
    ]
    comp.sort()
    q = lambda p: comp[min(len(comp) - 1, int(p * len(comp)))]  # noqa: E731
    return {
        "n": len(exemplos),
        "tokens_mediana": q(0.5),
        "tokens_p90": q(0.9),
        "tokens_max": comp[-1],
        f"acima_de_{SEQ_LIMIT}": sum(1 for c in comp if c > SEQ_LIMIT),
    }


def carregar_tokenizador(nome: str | None):
    if not nome:
        return None
    try:
        from transformers import AutoTokenizer
    except ImportError:
        print("[aviso] transformers ausente — estatísticas de token omitidas")
        return None
    return AutoTokenizer.from_pretrained(nome)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default="experiments/sft")
    p.add_argument("--val-frac", type=float, default=VAL_FRAC)
    p.add_argument("--tokenizer", default="Qwen/Qwen2.5-Coder-7B-Instruct")
    p.add_argument("--no-stats", action="store_true", help="pula a contagem de tokens")
    args = p.parse_args()

    gabarito = load_prompt(PROMPT)
    if "{description}" not in gabarito:
        raise SystemExit(f"{PROMPT} não tem o slot {{description}}")
    digest = hashlib.sha256(gabarito.encode()).hexdigest()

    with Database() as db:
        linhas = pares(db)
    if not linhas:
        raise SystemExit("nenhum par encontrado — confira a versão do conversor")

    treino, val = dividir(linhas, args.val_frac)
    ex_treino = [exemplo(x, gabarito) for x in treino]
    ex_val = [exemplo(x, gabarito) for x in val]

    destino = Path(args.out)
    destino.mkdir(parents=True, exist_ok=True)
    escrever(destino / "train.jsonl", ex_treino)
    escrever(destino / "val.jsonl", ex_val)

    tok = None if args.no_stats else carregar_tokenizador(args.tokenizer)
    manifesto = {
        "prompt": PROMPT,
        "prompt_sha256": digest,
        "dsl_version": DSL_VERSION,
        "total": len(linhas),
        "grupos": len({grupo(x) for x in linhas}),
        "treino": estatisticas(ex_treino, tok),
        "val": estatisticas(ex_val, tok),
        "grupos_val": sorted({e["group"] for e in ex_val}),
        "vazamento_de_grupo": sorted(
            {e["group"] for e in ex_treino} & {e["group"] for e in ex_val}
        ),
    }
    if manifesto["vazamento_de_grupo"]:
        raise SystemExit(f"grupos em ambos os lados: {manifesto['vazamento_de_grupo']}")

    (destino / "manifest.json").write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in manifesto.items() if k != "grupos_val"}, indent=2))
    print(f"\nescrito em {destino}/  (train.jsonl, val.jsonl, manifest.json)")


if __name__ == "__main__":
    main()
