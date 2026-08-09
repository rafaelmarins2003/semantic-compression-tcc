"""Piloto de seleção do modelo gerador (spec 004 §4.1b).

Roda o pipeline completo — preprocess → JSON → DSL → XML → XSD — sobre uma
amostra estratificada, para cada configuração de modelo candidata, e mede o que
de fato distingue modelos.

**Não usa DF-F1**: DF-F1 compara o JSON gerado contra o XML derivado desse mesmo
JSON, então mede a cadeia determinística e fica ~1,0 para qualquer modelo.

**Nunca toca no holdout**: escolher o gerador dos dados de treino olhando o
conjunto de avaliação seria contaminação.

    uv run python -m src.data.llm.run_model_pilot --dry-run
    uv run python -m src.data.llm.run_model_pilot --execute
"""

from __future__ import annotations

import argparse
import json
import random
import re
import warnings

from src.data.db import Database
from src.data.deterministic.graph import load_llm
from src.data.deterministic.json_to_dsl import convert
from src.data.llm.clients import LLMError, env_key, generate_ollama_cloud, load_dotenv
from src.data.llm.run_generate_json import _extract_json_object
from src.data.llm.run_generate_json import build_prompt as build_json_prompt
from src.data.llm.run_preprocess import build_prompt as build_preprocess_prompt
from src.data.migrations.create_model_pilot import ensure_schema
from src.transpiler import transpile
from src.transpiler.xsd import validate_bpmn_xsd

# (rótulo, modelo do preprocess, modelo do JSON)
CONFIGS = [
    ("controle", "kimi-k2.6:cloud", "deepseek-v4-pro:cloud"),
    ("glm52", "glm-5.2:cloud", "glm-5.2:cloud"),
    ("dsflash", "deepseek-v4-flash:0731-cloud", "deepseek-v4-flash:0731-cloud"),
]

# Estratificação: o handbook é 88% da base, mas o PET precisa estar representado.
STRATA = {"gitlab_handbook": 30, "pet": 20}
SEED = 42

# Marcadores de português: diacríticos raros em inglês + palavras funcionais.
# `do`, `com` e `sim` ficaram DE FORA de propósito: são palavras inglesas comuns
# ("Do the review", "com port", "sim card") e geravam falso positivo.
_PT_CHARS = re.compile(r"[ãõçáâêôú]", re.IGNORECASE)
_PT_WORDS = re.compile(
    r"\b(de|da|das|dos|para|não|processo|solicitação|usuário|cliente|enviar|registrar)\b",
    re.IGNORECASE,
)


def sample_ids(db: Database) -> list[dict]:
    """Amostra estratificada por fonte, apenas de splits de treino."""
    rng = random.Random(SEED)
    picked: list[dict] = []
    for source, n in STRATA.items():
        rows = [
            dict(r)
            for r in db.query(
                "SELECT id, source, raw_text FROM samples "
                "WHERE source = ? AND split IN ('sft','grpo') "
                "AND raw_text IS NOT NULL ORDER BY id",
                (source,),
            )
        ]
        picked.extend(rng.sample(rows, min(n, len(rows))))
    return picked


def _pt_markers(graph) -> int:
    labels = [n.name for n in graph.nodes.values()] + [n.lane for n in graph.nodes.values()]
    return sum(1 for lbl in labels if lbl and (_PT_CHARS.search(lbl) or _PT_WORDS.search(lbl)))


def _rule_violations(graph) -> int:
    """connection_rules do prompt: saída obrigatória exceto fim, entrada exceto início."""
    bad = 0
    for nid, node in graph.nodes.items():
        if node.type != "endEvent" and not graph.succs.get(nid):
            bad += 1
        if node.type != "startEvent" and not graph.preds.get(nid):
            bad += 1
    return bad


def evaluate_sample(row: dict, *, pp_model: str, json_model: str, api_key: str) -> dict:
    """Roda o pipeline inteiro para uma amostra e devolve as métricas."""
    out: dict = {"stage_failed": None, "error_message": None}
    try:
        sys_p, user_p = build_preprocess_prompt(row["raw_text"])
        out["stage_failed"] = "preprocess"
        structured = generate_ollama_cloud(
            user_p, api_key=api_key, model=pp_model, system_prompt=sys_p, temperature=0.0
        )

        out["stage_failed"] = "json"
        _, json_user = build_json_prompt(structured)
        raw = generate_ollama_cloud(json_user, api_key=api_key, model=json_model, temperature=0.0)
        data = json.loads(_extract_json_object(raw))
        out["json_ok"] = 1

        out["stage_failed"] = "dsl"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            graph = load_llm(data)
            dsl = convert(data)
        out["dsl_ok"] = 1 if dsl.strip() else 0
        out["n_nodes"] = len(graph.nodes)
        out["n_gateways"] = sum(1 for n in graph.nodes.values() if "Gateway" in n.type)
        out["n_lanes"] = len({n.lane for n in graph.nodes.values() if n.lane})
        out["n_flows"] = sum(len(v) for v in graph.succs.values())
        out["rule_violations"] = _rule_violations(graph)
        out["pt_markers"] = _pt_markers(graph)

        out["stage_failed"] = "xml"
        xml = transpile(dsl)
        out["xml_ok"] = 1
        out["xsd_ok"] = 1 if validate_bpmn_xsd(xml) == [] else 0
        out["stage_failed"] = None
    except (LLMError, json.JSONDecodeError, Exception) as exc:  # noqa: B014
        out["error_message"] = f"{type(exc).__name__}: {str(exc)[:300]}"
    return out


def run(args: argparse.Namespace) -> None:
    load_dotenv()
    api_key = env_key("OLLAMA_API_KEY") if args.execute else ""

    with Database() as db:
        ensure_schema(db._conn)
        rows = sample_ids(db)
        if args.limit:
            rows = rows[: args.limit]

        if not args.execute:
            by_source: dict[str, int] = {}
            for r in rows:
                by_source[r["source"]] = by_source.get(r["source"], 0) + 1
            plan = {"amostra": len(rows), "por_fonte": by_source}
            plan["configs"] = [c[0] for c in CONFIGS]
            print(plan)
            print(f"chamadas de LLM previstas: {len(rows) * len(CONFIGS) * 2}")
            return

        # As linhas são gravadas como "<run_label>:<config>", então o filtro precisa
        # ser por prefixo. Com `=` o DELETE nunca casava e reexecutar duplicaria.
        prefix = f"{args.run_label}:%"
        if args.restart:
            db._conn.execute("DELETE FROM model_pilot WHERE run_label LIKE ?", (prefix,))
            db._conn.commit()

        # Retomada: pares (config, amostra) já gravados não são refeitos. Falha de
        # modelo é resultado medido, não erro transitório — não se repete tampouco.
        done = {
            (r["run_label"], r["sample_id"])
            for r in db.query(
                "SELECT run_label, sample_id FROM model_pilot WHERE run_label LIKE ?", (prefix,)
            )
        }
        if done:
            print(f"[resume] {len(done)} pares já gravados serão pulados")

        for label, pp_model, json_model in CONFIGS:
            full_label = f"{args.run_label}:{label}"
            for i, row in enumerate(rows, 1):
                if (full_label, row["id"]) in done:
                    continue
                res = evaluate_sample(
                    row, pp_model=pp_model, json_model=json_model, api_key=api_key
                )
                db._conn.execute(
                    "INSERT INTO model_pilot (run_label, sample_id, source, preprocess_model,"
                    " json_model, prompt_version, stage_failed, json_ok, dsl_ok, xml_ok, xsd_ok,"
                    " n_nodes, n_gateways, n_lanes, n_flows, rule_violations, pt_markers,"
                    " error_message) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        full_label,
                        row["id"],
                        row["source"],
                        pp_model,
                        json_model,
                        args.prompt_version,
                        res.get("stage_failed"),
                        res.get("json_ok", 0),
                        res.get("dsl_ok", 0),
                        res.get("xml_ok", 0),
                        res.get("xsd_ok", 0),
                        res.get("n_nodes"),
                        res.get("n_gateways"),
                        res.get("n_lanes"),
                        res.get("n_flows"),
                        res.get("rule_violations"),
                        res.get("pt_markers"),
                        res.get("error_message"),
                    ),
                )
                db._conn.commit()
                print(f"[{label} {i}/{len(rows)}] {row['id']} -> {res.get('stage_failed') or 'ok'}")
        summarize(db, args.run_label)


def summarize(db: Database, run_label: str) -> None:
    sql = """
        SELECT run_label, count(*) n,
               round(avg(xsd_ok) * 100, 1)          AS pct_xsd,
               round(avg(json_ok) * 100, 1)         AS pct_json,
               round(avg(n_nodes), 1)               AS nodes,
               round(avg(n_gateways), 2)            AS gateways,
               round(avg(n_lanes), 2)               AS lanes,
               round(avg(rule_violations), 2)       AS violacoes,
               round(avg(pt_markers), 2)            AS marcadores_pt
        FROM model_pilot WHERE run_label LIKE ? GROUP BY run_label ORDER BY pct_xsd DESC
    """
    print("\n== resumo ==")
    for r in db.query(sql, (f"{run_label}:%",)):
        print(dict(r))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--execute", action="store_true", help="Sem isso, só mostra o plano.")
    p.add_argument("--run-label", default="pilot_v2_en")
    p.add_argument("--prompt-version", default="bpmn_json_generator_v2_en")
    p.add_argument("--limit", type=int, default=0, help="Trunca a amostra (para teste).")
    p.add_argument(
        "--restart", action="store_true", help="Apaga o run e recomeça em vez de retomar."
    )
    p.add_argument("--summary-only", action="store_true")
    return p.parse_args()


if __name__ == "__main__":
    _args = parse_args()
    if _args.summary_only:
        with Database() as _db:
            summarize(_db, _args.run_label)
    else:
        run(_args)
