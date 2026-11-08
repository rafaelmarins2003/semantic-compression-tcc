"""Dados das figuras de contrastes e da curva de aprendizado (capítulo de Resultados).

    uv run python -m src.evaluation.export_contrastes

Reaproveita as funções de `run_validity` e `run_fidelity`, de modo que a figura e
as tabelas saem do mesmo cálculo, com as mesmas sementes. A curva lê a perda na
validação dos logs de treino em `experiments/sft/`, porque só o A4 tem
`trainer_state` salvo.
"""

from __future__ import annotations

import argparse
import re
import statistics
from pathlib import Path

from src.data.db import LEAKED_HOLDOUT, Database
from src.evaluation import run_fidelity, run_validity
from src.evaluation.judge import prompt_sha

ROTULO = {"X-a2r": "A2r"}
# braço -> log do treino do adaptador
CURVA = {"X-lc25": "sft_lc25", "X-lc50": "sft_lc50", "A4": "sft_a4"}
LOGS = Path("experiments/sft")


def _nome(a: str, b: str) -> str:
    return f"{ROTULO.get(a, a)} $-$ {ROTULO.get(b, b)}"


def _linha(y: int, a: str, b: str, dif: float, lo: float, hi: float, veredito: str) -> str:
    # y: posição no eixo, de cima para baixo; em/ep: barras de erro para o pgfplots
    return f"{y},{_nome(a, b)},{dif},{lo},{hi},{dif - lo:.3f},{hi - dif:.3f},{veredito}"


def contrastes(db: Database) -> dict[str, list[str]]:
    bracos = {arm for par in run_validity.CONTRASTS for arm in par}
    val = {arm: run_validity.item_validity(db, arm) for arm in bracos}
    validade = []
    for k, (a, b) in enumerate(run_validity.CONTRASTS):
        r = run_validity.contrast(val[a], val[b])
        y = len(run_validity.CONTRASTS) - k
        validade.append(_linha(y, a, b, r["dif_pp"], *r["ic95_pp"], r["veredito"]))
    notas = run_fidelity.load(db, prompt_sha())
    itens = {s for s in run_fidelity.text_type(db) if s not in LEAKED_HOLDOUT}
    fidelidade = []
    for k, (a, b) in enumerate(run_fidelity.CONTRASTS):
        r = run_fidelity.contrast(notas[a], notas[b], itens)
        y = len(run_fidelity.CONTRASTS) - k
        fidelidade.append(_linha(y, a, b, r["dif_media"], *r["ic95"], r["veredito"]))
    return {"validade": validade, "fidelidade": fidelidade}


def _treino(log: str) -> tuple[int, float]:
    """(pares de treino usados, menor perda na validação) de um log de treino."""
    texto = (LOGS / f"{log}.log").read_text(encoding="utf-8")
    pares = int(re.search(r"exemplos usados (\d+)", texto).group(1))  # 1ª ocorrência: treino
    perdas = [float(x) for x in re.findall(r"'eval_loss': '?([0-9.]+)", texto)]
    return pares, min(perdas)


def curva(db: Database) -> list[str]:
    linhas = []
    for arm, log in CURVA.items():
        pares, perda = _treino(log)
        validade = 100 * statistics.mean(run_validity.item_validity(db, arm).values())
        linhas.append(f"{arm},{pares},{perda:.4f},{validade:.1f}")
    return sorted(linhas, key=lambda x: int(x.split(",")[1]))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default="article/paper/figuras/dados")
    destino = Path(p.parse_args().out)
    destino.mkdir(parents=True, exist_ok=True)
    with Database(read_only=True) as db:
        cabecalho = "y,contraste,dif,lo,hi,em,ep,veredito"
        tabelas = {f"contrastes_{m}.csv": (cabecalho, v) for m, v in contrastes(db).items()}
        tabelas["curva.csv"] = ("braco,pares,perda,validade", curva(db))
    for nome, (cabecalho, linhas) in tabelas.items():
        (destino / nome).write_text("\n".join([cabecalho, *linhas]) + "\n", encoding="utf-8")
        print(f"  {destino / nome}: {len(linhas)} linhas")


if __name__ == "__main__":
    main()
