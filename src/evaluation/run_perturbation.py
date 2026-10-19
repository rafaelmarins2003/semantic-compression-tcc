"""Monta os casos de perturbação e roda o juiz neles.

    uv run python -m src.evaluation.run_perturbation --build            # planeja
    uv run python -m src.evaluation.run_perturbation --build --execute  # grava casos
    uv run python -m src.evaluation.run_perturbation --judge            # planeja
    uv run python -m src.evaluation.run_perturbation --judge --execute [--workers 8]

Base: o gold primário dos itens do PMo, menos os 7 cujo texto vazou para o treino
(auditoria de 2026-10-14, P2). Os mutantes são determinísticos; só a paráfrase chama
um LLM (Ollama Cloud, família diferente da do juiz). O juiz usa `run_judge`, com as
mesmas 3 repetições e a mesma tabela `judge_eval` da validação no Zenodo.
"""

from __future__ import annotations

import argparse
import copy
import json
import random

from src.data.db import Database
from src.data.llm.clients import env_key, generate_ollama_cloud
from src.data.llm.utils import load_prompt
from src.data.migrations.create_judge_eval import ensure_schema as ensure_judge_schema
from src.data.migrations.create_perturbation_cases import ensure_schema
from src.evaluation import perturb as pt
from src.evaluation.judge import prompt_sha
from src.evaluation.render import render
from src.evaluation.run_judge import execute, pending

# Texto do PET no holdout (auditoria de 2026-10-14, P2): fora de toda avaliação.
LEAKED = {"pmo_20", "pmo_49", "pmo_50", "pmo_51", "pmo_52", "pmo_53", "pmo_54"}
PARAPHRASE_MODEL = "glm-5.3:cloud"
TRIES = 10  # sementes tentadas até um mutante mudar de fato o processo


def golds(db: Database) -> list[dict]:
    linhas = db.query(
        "SELECT g.sample_id, g.gold_xml, s.raw_text FROM gold_models g"
        " JOIN samples s ON s.id = g.sample_id"
        " WHERE g.source = 'pmo' AND g.variant = 'primary' ORDER BY g.sample_id"
    )
    return [dict(r) for r in linhas if r["sample_id"] not in LEAKED]


def _case(sid: str, kind: str, n: int, ops: list, g: dict, detail: dict | None = None) -> dict:
    return {
        "case_id": f"{sid}:{kind}", "sample_id": sid, "kind": kind, "n_defects": n,
        "operators": json.dumps(ops), "detail": json.dumps(detail) if detail else None,
        "xml": pt.to_xml(g),
    }  # fmt: skip


def mutant_cases(sid: str, gold_xml: str, description: str) -> list[dict]:
    """Intacto, um mutante por operador aplicável e um com 3 defeitos.

    Mutante que não muda a renderização (ex.: trocar duas tarefas simétricas em
    ramos paralelos) não é defeito; tenta outra semente e, se nenhuma servir, o
    operador fica de fora deste item.
    """
    base = pt.graph(gold_xml)
    intacto = render(pt.to_xml(base))
    casos = [_case(sid, "intact", 0, [], base)]
    for kind, n in [(op, 1) for op in pt.OPERATORS] + [("triple", 3)]:
        for k in range(TRIES):
            g, rng = copy.deepcopy(base), random.Random(f"{sid}:{kind}:{k}")
            ops = pt.mutate_many(g, 3, rng, description) if n == 3 else (
                [kind] if pt.mutate(g, kind, rng, description) else []
            )  # fmt: skip
            if len(ops) == n and render(pt.to_xml(g)) != intacto:
                casos.append(_case(sid, kind, n, ops, g))
                break
    return casos


def last_json_object(texto: str) -> dict:
    """Último objeto JSON do texto.

    O Kimi às vezes raciocina em voz alta na resposta, mesmo com `think=False`, e só
    no fim entrega o JSON (em cerca ```json ou não). Isso apareceu na primeira
    execução real (2026-10-19), não no teste da véspera.
    """
    decoder = json.JSONDecoder()
    for i in range(len(texto) - 1, -1, -1):
        if texto[i] != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(texto, i)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    raise ValueError(f"sem objeto JSON na resposta: {texto[:120]!r}")


def paraphrase_case(sid: str, gold_xml: str, api_key: str) -> dict:
    base = pt.graph(gold_xml)
    rotulos = pt.labels(base)
    pedido = load_prompt("perturbation/paraphrase.md").replace("{labels}", json.dumps(rotulos))
    texto = generate_ollama_cloud(pedido, api_key=api_key, model=PARAPHRASE_MODEL, temperature=0)
    mapa = last_json_object(texto)
    faltam = [r for r in rotulos if not str(mapa.get(r, "")).strip()]
    if faltam:
        raise ValueError(f"{sid}: paráfrase sem {len(faltam)} rótulo(s), ex. {faltam[0]!r}")
    detail = {"model": PARAPHRASE_MODEL, "mapping": {r: mapa[r].strip() for r in rotulos}}
    return _case(sid, "paraphrase", 0, [], pt.paraphrased(base, detail["mapping"]), detail)


def build(db: Database, execute_: bool) -> None:
    feitos = {r["case_id"] for r in db.query("SELECT case_id FROM perturbation_cases")}
    itens = golds(db)
    novos = [
        c
        for it in itens
        for c in mutant_cases(it["sample_id"], it["gold_xml"], it["raw_text"])
        if c["case_id"] not in feitos
    ]
    sem_parafrase = [it for it in itens if f"{it['sample_id']}:paraphrase" not in feitos]
    print(
        f"itens={len(itens)}  mutantes novos={len(novos)}  paráfrases a gerar={len(sem_parafrase)}"
    )
    if not execute_:
        print("dry-run: nada gravado. Use --execute.")
        return
    api_key = env_key("OLLAMA_API_KEY") if sem_parafrase else ""
    for it in sem_parafrase:
        try:
            novos.append(paraphrase_case(it["sample_id"], it["gold_xml"], api_key))
        except Exception as exc:  # fica pendente para a próxima execução
            print(f"  FALHA paráfrase {it['sample_id']}: {str(exc)[:160]}")
    for c in novos:
        cols = ", ".join(c)
        db._conn.execute(
            f"INSERT INTO perturbation_cases ({cols}) VALUES ({', '.join('?' * len(c))})",
            tuple(c.values()),
        )
    db._conn.commit()
    print(f"gravados={len(novos)}")


def judge_targets(db: Database) -> list[dict]:
    linhas = db.query(
        "SELECT c.case_id, c.sample_id, c.xml, s.raw_text FROM perturbation_cases c"
        " JOIN samples s ON s.id = c.sample_id ORDER BY c.case_id"
    )
    return [
        {
            "target": f"pert:{r['case_id']}",
            "kind": "perturbation",
            "sample_id": r["sample_id"],
            "arm": None,
            "expert_score": None,
            "description": r["raw_text"],
            "xml": r["xml"],
        }  # fmt: skip
        for r in linhas
    ]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    modo = p.add_mutually_exclusive_group(required=True)
    modo.add_argument("--build", action="store_true", help="monta e grava os casos")
    modo.add_argument("--judge", action="store_true", help="roda o juiz nos casos")
    p.add_argument("--execute", action="store_true", help="sem isto, só planeja")
    p.add_argument("--workers", type=int, default=6)
    args = p.parse_args()
    with Database() as db:
        ensure_schema(db._conn)
        ensure_judge_schema(db._conn)
        if args.build:
            return build(db, args.execute)
        sha = prompt_sha()
        fila = pending(db, judge_targets(db), sha)
        print(f"prompt_sha={sha[:12]}  pendentes={len(fila)}")
        if args.execute:
            print(execute(db, fila, env_key("META_API_KEY"), args.workers))


if __name__ == "__main__":
    main()
