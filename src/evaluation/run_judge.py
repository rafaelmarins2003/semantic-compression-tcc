"""Roda o juiz de fidelidade e grava as notas em `judge_eval`.

    uv run python -m src.evaluation.run_judge --zenodo [--execute] [--workers 6]
    uv run python -m src.evaluation.run_judge --arms A1,A2 [--execute] [--workers 6]

`--zenodo` é a validação (T5): os 222 modelos do Zenodo com nota de especialista,
3 repetições cada. Todos entram, inclusive os 17 que são cópia do gold do PMo: aqui
não há referência, só texto e modelo, então a cópia não tem vantagem.

`--arms` é a fidelidade dos braços (T6): toda saída válida no XSD dos braços
pedidos, nos 46 itens do PMo fora do vazamento, 3 repetições cada. O juiz recebe o
mesmo texto que o braço recebeu. Saída inválida não é julgada: a fidelidade é
condicionada à validade, que já é medida à parte.

Retomável: alvos já pontuados com o prompt atual são pulados, e falhas ficam
pendentes para a próxima execução. As notas são gravadas a cada lote, para que uma
interrupção não perca o que já foi pago.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from src.data.db import LEAKED_HOLDOUT, Database
from src.data.ingestion.import_gold_zenodo import ZENODO_DIR
from src.data.llm.clients import env_key, run_parallel
from src.data.migrations.create_judge_eval import ensure_schema
from src.evaluation.judge import JUDGE_MODEL, judge, prompt_sha

K_REPS = 3
MAIN_ARMS = "A1,A1g,A2,A2g,X-a2r,A4"
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


def benchmark_targets(db: Database, arms: list[str]) -> list[dict]:
    """Um alvo por saída válida no XSD, fora dos itens vazados."""
    linhas = db.query(
        "SELECT b.id, b.arm, b.sample_id, b.output_xml, s.raw_text FROM benchmark_eval b"
        " JOIN samples s ON s.id = b.sample_id"
        f" WHERE b.xsd_valid = 1 AND b.arm IN ({', '.join('?' * len(arms))})"
        " ORDER BY b.arm, b.sample_id, b.rep",
        tuple(arms),
    )
    return [
        {
            "target": f"bench:{r['id']}",
            "kind": "benchmark",
            "sample_id": r["sample_id"],
            "arm": r["arm"],
            "expert_score": None,
            "description": r["raw_text"] or "",
            "xml": r["output_xml"],
        }  # fmt: skip
        for r in linhas
        if r["sample_id"] not in LEAKED_HOLDOUT
    ]


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
    with Database() as db:
        ensure_schema(db._conn)
        alvos = zenodo_targets() if args.zenodo else benchmark_targets(db, args.arms.split(","))
        fila = pending(db, alvos, sha)
        print(f"prompt_sha={sha[:12]}  alvos={len(alvos)}  pendentes={len(fila)} (k={K_REPS})")
        if not args.execute:
            print("dry-run: nada chamado. Use --execute.")
            return
        resumo = execute(db, fila, env_key("META_API_KEY"), args.workers)
        print(resumo)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    modo = p.add_mutually_exclusive_group(required=True)
    modo.add_argument("--zenodo", action="store_true", help="validação (T5)")
    modo.add_argument(
        "--arms", nargs="?", const=MAIN_ARMS, help=f"fidelidade dos braços (T6); padrão {MAIN_ARMS}"
    )
    p.add_argument("--execute", action="store_true", help="sem isto, só planeja")
    p.add_argument("--workers", type=int, default=6)
    return p.parse_args()


if __name__ == "__main__":
    run(parse_args())
