"""Subamostras aninhadas do conjunto de treino, para a curva de aprendizado.

Três decisões que este script existe para tornar explícitas:

1. **Amostra por grupo, não por exemplo.** A pergunta da curva é "mais dados
   ajudariam?", e nesse corpus "mais dados" significa mais *documentos de
   origem* — 95,3% do treino vem de um único handbook. Sortear exemplos soltos
   mediria o efeito de rotular mais seções do mesmo documento, que é outra
   pergunta. O grupo é a mesma unidade de `export_dataset.dividir`.

2. **Frações aninhadas.** A ordem dos grupos vem do sha1 do nome e cada fração é
   um prefixo dessa ordem, logo 25% ⊂ 50% ⊂ 100%. Sem isso a curva mistura
   efeito de volume com efeito de composição do corpus.

3. **`val.jsonl` copiado sem alteração.** Pontos avaliados em conjuntos
   diferentes não formam uma curva.

O ponto de 100% da curva é o adapter que já existe (`experiments/sft/adapter`),
não um treino novo: regerá-lo produziria outro adapter e invalidaria os números
do braço A4 já reportados sob protocolo congelado.

    uv run python -m src.training.subsample
    uv run python -m src.training.subsample --frac 25 50 --dados experiments/sft
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from src.training.train_sft import carregar

FRACOES = (25, 50)


def prefixo(exemplos: list[dict], frac: float) -> list[dict]:
    """Prefixo determinístico da ordem sha1 dos grupos, até cobrir `frac`."""
    porgrupo: dict[str, list[dict]] = {}
    for e in exemplos:
        porgrupo.setdefault(e["group"], []).append(e)

    ordem = sorted(porgrupo, key=lambda g: hashlib.sha1(g.encode()).hexdigest())
    alvo = len(exemplos) * frac
    escolhidos: list[dict] = []
    for g in ordem:
        if len(escolhidos) >= alvo:
            break
        escolhidos.extend(porgrupo[g])
    return sorted(escolhidos, key=lambda e: e["id"])


def escrever(destino: Path, treino: list[dict], val_origem: Path) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "train.jsonl").write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in treino), encoding="utf-8"
    )
    shutil.copy(val_origem, destino / "val.jsonl")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dados", default="experiments/sft")
    p.add_argument("--frac", type=int, nargs="+", default=list(FRACOES))
    args = p.parse_args()

    raiz = Path(args.dados)
    completo = carregar(raiz / "train.jsonl")
    grupos_val = {e["group"] for e in carregar(raiz / "val.jsonl")}
    n_grupos = len({e["group"] for e in completo})
    print(f"treino completo: {len(completo)} exemplos, {n_grupos} grupos")

    anterior: set[str] = set()
    for pct in sorted(args.frac):
        sub = prefixo(completo, pct / 100)
        ids = {e["id"] for e in sub}
        grupos = {e["group"] for e in sub}

        if not anterior <= ids:
            raise SystemExit(f"lc{pct} não contém a fração anterior — aninhamento quebrado")
        if grupos & grupos_val:
            raise SystemExit(f"lc{pct} vazou {len(grupos & grupos_val)} grupo(s) para a validação")
        anterior = ids

        destino = raiz / f"lc{pct}"
        escrever(destino, sub, raiz / "val.jsonl")
        real = 100 * len(sub) / len(completo)
        print(
            f"  lc{pct}: {len(sub):3d} exemplos ({real:.1f}%), {len(grupos):3d} grupos → {destino}"
        )


if __name__ == "__main__":
    main()
