"""Roda o juiz de fidelidade e grava as notas em `judge_eval`.

    uv run python -m src.evaluation.run_judge --zenodo --dry-run
    uv run python -m src.evaluation.run_judge --zenodo --execute [--workers 6]

`--zenodo` é a validação (T5): os 222 modelos do Zenodo com nota de especialista,
3 repetições cada. Todos entram, inclusive os 17 que são cópia do gold do PMo: aqui
não há referência, só texto e modelo, então a cópia não tem vantagem.

Retomável: alvos já pontuados com o prompt atual são pulados, e falhas ficam
pendentes para a próxima execução. As notas são gravadas a cada lote, para que uma
interrupção não perca o que já foi pago.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from src.data.db import Database
from src.data.ingestion.import_gold_zenodo import ZENODO_DIR
from src.data.llm.clients import env_key, run_parallel
from src.data.migrations.create_judge_eval import ensure_schema
from src.evaluation.judge import JUDGE_MODEL, judge, prompt_sha

K_REPS = 3
BATCH = 24


def zenodo_targets(zenodo_dir: Path = ZENODO_DIR) -> list[dict]:
    """Um alvo por modelo do Zenodo que tem nota de especialista."""
    alvos = []
    for pasta in sorted(p for p in zenodo_dir.iterdir() if p.is_dir()):
        texto = (zenodo_dir / f"{pasta.name}.txt").read_text(encoding="utf-8")
        for modelo in sorted(pasta.glob("*.bpmn2.xml")):
            nota = modelo.with_name(modelo.name.replace(".bpmn2.xml", ".quality.txt"))
            if not nota.exists() or not nota.read_text().strip():
                continue
            alvos.append(
                {
                    "target": f"zenodo:{pasta.name}/{modelo.name.removesuffix('.bpmn2.xml')}",
                    "kind": "zenodo",
                    "sample_id": pasta.name,
                    "arm": None,
                    "expert_score": float(nota.read_text().strip()),
                    "description": texto,
                    "xml": modelo.read_text(encoding="utf-8"),
                }
            )
    return alvos


def pending(db: Database, alvos: list[dict], sha: str, k: int = K_REPS) -> list[tuple[dict, int]]:
    feitos = {
        (r["target"], r["rep"])
        for r in db.query("SELECT target, rep FROM judge_eval WHERE prompt_sha = ?", (sha,))
    }
    return [(a, rep) for a in alvos for rep in range(k) if (a["target"], rep) not in feitos]


def _row(alvo: dict, rep: int, resultado: dict, ms: int) -> dict:
    uso = resultado.get("usage") or {}
    return {
        "target": alvo["target"], "kind": alvo["kind"], "sample_id": alvo["sample_id"],
        "arm": alvo["arm"], "expert_score": alvo["expert_score"], "rep": rep,
        "model_id": resultado.get("model") or JUDGE_MODEL, "prompt_sha": resultado["prompt_sha"],
        "score": resultado["score"], "problems": json.dumps(resultado["problems"]),
        "finish_reason": resultado.get("finish_reason"),
        "prompt_tokens": uso.get("prompt_tokens"),
        "completion_tokens": uso.get("completion_tokens"),
        "reasoning_tokens": (uso.get("completion_tokens_details") or {}).get("reasoning_tokens"),
        "latency_ms": ms,
    }  # fmt: skip


def insert_row(db: Database, linha: dict) -> None:
    cols = ", ".join(linha)
    db._conn.execute(
        f"INSERT INTO judge_eval ({cols}) VALUES ({', '.join('?' * len(linha))})",
        tuple(linha.values()),
    )


def _task(alvo: dict, rep: int, api_key: str):
    def call() -> dict:
        inicio = time.monotonic()
        # seed = rep: as repetições diferem entre si e cada uma é reproduzível
        # na medida em que a API permitir (modelo de raciocínio não garante).
        resultado = judge(alvo["description"], alvo["xml"], api_key=api_key, seed=rep)
        return _row(alvo, rep, resultado, int((time.monotonic() - inicio) * 1000))

    return call


def execute(db: Database, fila: list[tuple[dict, int]], api_key: str, workers: int) -> dict:
    ok = falhas = 0
    for i in range(0, len(fila), BATCH):
        lote = fila[i : i + BATCH]
        resultados = run_parallel([_task(a, rep, api_key) for a, rep in lote], max_workers=workers)
        for (alvo, rep), res in zip(lote, resultados):
            if isinstance(res, Exception):
                falhas += 1
                print(f"  FALHA {alvo['target']} rep={rep}: {str(res)[:160]}")
                continue
            insert_row(db, res)
            ok += 1
        db._conn.commit()
        print(f"[judge] {min(i + BATCH, len(fila))}/{len(fila)}  ok={ok} falhas={falhas}")
    return {"ok": ok, "falhas": falhas}


def run(args: argparse.Namespace) -> None:
    sha = prompt_sha()
    alvos = zenodo_targets()
    with Database() as db:
        ensure_schema(db._conn)
        fila = pending(db, alvos, sha)
        print(f"prompt_sha={sha[:12]}  alvos={len(alvos)}  pendentes={len(fila)} (k={K_REPS})")
        if not args.execute:
            print("dry-run: nada chamado. Use --execute.")
            return
        resumo = execute(db, fila, env_key("META_API_KEY"), args.workers)
        print(resumo)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--zenodo", action="store_true", required=True, help="validação (T5)")
    p.add_argument("--execute", action="store_true", help="sem isto, só planeja")
    p.add_argument("--workers", type=int, default=6)
    return p.parse_args()


if __name__ == "__main__":
    run(parse_args())
