"""Harness de avaliação dos braços (spec 003).

Duas fases separadas de propósito:

    generate   cara, em rede, NÃO determinística. Grava a saída crua.
    score      barata, local, determinística. Recalculável sem rede (--rescore).

Separá-las é o que torna o AC-3 satisfazível: repontuar saídas já gravadas
produz linhas idênticas, o que não valeria se a pontuação exigisse gerar de novo
([ADR 0003](../../specs/adr/0003-nao-determinismo-temperatura-zero.md)).

    uv run python -m src.evaluation.run_benchmark --arm A2 --dry-run
    uv run python -m src.evaluation.run_benchmark --arm A2 --execute
    uv run python -m src.evaluation.run_benchmark --arm A2 --rescore
    uv run python -m src.evaluation.run_benchmark --arm A2 --retranspile
"""

from __future__ import annotations

import argparse
import hashlib
import statistics
import subprocess
import time
from dataclasses import dataclass

from src.data.db import HOLDOUT_SPLIT, Database
from src.data.llm.clients import LLMError, env_key, generate_ollama_cloud, load_dotenv
from src.data.llm.utils import load_prompt
from src.data.migrations.create_benchmark_eval import ensure_schema
from src.evaluation.topology import compare_xml
from src.transpiler.xml import transpile
from src.transpiler.xsd import validate_bpmn_xsd

K_REPS = 3
TEMPERATURE = 0.0
MIN_REF_SCORE = 4.0
EVAL_SOURCE = "pmo"


SMALL_MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"
SFT_ADAPTER = "experiments/sft/adapter"  # produzido na Fase 7; ausente até lá
# Famílias adicionais dos braços de replicação. Todas aprovadas no pré-voo de
# `src.training.check_template`, que desde 2026-08-23 testa **ida-e-volta do
# tokenizador** antes de qualquer outra coisa.
#
# `deepseek-coder-6.7b-instruct` foi tentado e REPROVA: sob transformers 5.5 ele
# carrega como LlamaTokenizer e apaga os espaços na codificação, o que zera a
# fidelidade sem derrubar a validade. Mantido aqui como registro do que não usar.
BASE_DEEPSEEK = "deepseek-ai/deepseek-coder-6.7b-instruct"  # REPROVADO, ver X-ds
BASE_GRANITE = "ibm-granite/granite-4.1-8b"
BASE_MIMO = "XiaomiMiMo/MiMo-7B-RL"
BASE_MISTRAL = "mistralai/Mistral-7B-Instruct-v0.3"


@dataclass(frozen=True)
class Arm:
    prompt: str
    model: str
    emits: str  # "xml" | "dsl"
    max_tokens: int
    backend: str = "ollama_cloud"
    adapter: str | None = None
    # Executar código do repositório do modelo. Declarado por braço porque é
    # informação experimental: um braço que exige isso não está em pé de
    # igualdade com um que não exige.
    trust_remote_code: bool = False


# Congelado na spec 003 §4/§6.2. Trocar aqui é emenda, não ajuste.
ARMS: dict[str, Arm] = {
    "A1": Arm("benchmark/xml_direct.md", "deepseek-v4-pro:cloud", "xml", 8192),
    "A1g": Arm("benchmark/xml_direct.md", "glm-5.2:cloud", "xml", 8192),
    "A2": Arm("benchmark/dsl_grammar.md", "deepseek-v4-pro:cloud", "dsl", 2048),
    "A2g": Arm("benchmark/dsl_grammar.md", "glm-5.2:cloud", "dsl", 2048),
    "A3": Arm("benchmark/dsl_grammar.md", SMALL_MODEL, "dsl", 2048, "local"),
    # Controle de A4: mesmo modelo e MESMO prompt do A4, sem o adapter. Com ele,
    # A4 vs A3m isola o efeito do ajuste supervisionado (só os pesos mudam),
    # enquanto A4 vs A3 mede a intervenção inteira (pesos + dispensa da gramática).
    "A3m": Arm("benchmark/dsl_minimal.md", SMALL_MODEL, "dsl", 2048, "local"),
    "A4": Arm("benchmark/dsl_minimal.md", SMALL_MODEL, "dsl", 2048, "local", SFT_ADAPTER),
    # --- Exploratórios, declarados em 2026-08-23, antes de executar ---
    # NÃO integram os sete braços pré-registrados nem qualquer contraste da spec
    # 003 §4; entram no texto rotulados como exploratórios. Respondem a duas
    # perguntas que os sete braços deixam em aberto:
    #   X-lc25/X-lc50 — a validade ainda sobe com mais dados, ou saturou? Modelo,
    #     prompt e protocolo idênticos aos do A4; só o volume de documentos de
    #     treino muda (`src.training.subsample`). O ponto de 100% da curva é o
    #     próprio A4: retreiná-lo produziria outro adapter e invalidaria os
    #     números já reportados.
    #   X-ds — o resultado do A4 é propriedade do método ou do Qwen? Outra
    #     família de modelo, todo o resto constante. Se não replicar, a alegação
    #     enfraquece; é por isso que vale medir.
    "X-lc25": Arm(
        "benchmark/dsl_minimal.md", SMALL_MODEL, "dsl", 2048, "local", f"{SFT_ADAPTER}-lc25"
    ),
    "X-lc50": Arm(
        "benchmark/dsl_minimal.md", SMALL_MODEL, "dsl", 2048, "local", f"{SFT_ADAPTER}-lc50"
    ),
    # X-ds ficou INVÁLIDO: o tokenizador do DeepSeek apaga espaços na codificação,
    # de modo que o braço mediu o tokenizador, não o método. As linhas seguem no
    # banco como evidência; nenhum número dele vai para o texto.
    "X-ds": Arm(
        "benchmark/dsl_minimal.md", BASE_DEEPSEEK, "dsl", 2048, "local", f"{SFT_ADAPTER}-ds"
    ),
    # --- Replicação em outras famílias, declarada em 2026-08-23 antes de rodar ---
    # Pergunta: os 86,8% de validade do A4 são propriedade do método ou do Qwen?
    # Três linhagens de três organizações independentes (Alibaba, IBM, Xiaomi ou
    # Mistral AI), com prompt, dados, hiperparâmetros e protocolo idênticos.
    #
    # COMPROMISSO REGISTRADO ANTES DA EXECUÇÃO: **todo braço que treinar entra no
    # texto**, replique ou não. Rodar três e reportar o melhor seria escolha a
    # posteriori — o vício que o pré-registro existe para impedir.
    #
    # X-mi passa por portão: exige `trust_remote_code` (arquitetura fora do
    # transformers) e tem camadas de multi-token prediction, cuja interação com
    # LoRA `all-linear` é desconhecida. Se o smoke falhar, treina-se X-ms no
    # lugar, sem depurar arquitetura em GPU alugada.
    "X-gr": Arm(
        "benchmark/dsl_minimal.md", BASE_GRANITE, "dsl", 2048, "local", f"{SFT_ADAPTER}-gr"
    ),
    "X-mi": Arm(
        "benchmark/dsl_minimal.md", BASE_MIMO, "dsl", 2048, "local", f"{SFT_ADAPTER}-mi", True
    ),
    "X-ms": Arm(
        "benchmark/dsl_minimal.md", BASE_MISTRAL, "dsl", 2048, "local", f"{SFT_ADAPTER}-ms"
    ),
}


def spec_commit() -> str:
    """HEAD atual. Liga cada linha ao estado congelado da spec (AC-7)."""
    out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
    return out.stdout.strip() or "unknown"


def prompt_digest(name: str) -> tuple[str, str]:
    texto = load_prompt(name)
    return texto, hashlib.sha256(texto.encode("utf-8")).hexdigest()


def strip_fence(texto: str) -> str:
    """Remove cerca markdown em volta da saída.

    Aplicada **identicamente a todos os braços**. Sem isso, a métrica mediria
    aderência à instrução "não use cerca" em vez de qualidade do modelo — e o
    viés não seria neutro, já que emitir ```xml é hábito muito mais treinado que
    emitir ```dsl. Não é retry: nada é regerado.
    """
    t = texto.strip()
    if not t.startswith("```"):
        return t
    linhas = t.splitlines()
    if len(linhas) >= 2 and linhas[-1].strip().startswith("```"):
        return "\n".join(linhas[1:-1]).strip()
    # Cerca sem fechamento: acontece sempre que a saída é truncada pelo teto de
    # tokens. Exigir o par deixava a abertura no texto e reprovava o candidato
    # por defeito do harness. O viés não era neutro — os braços de XML são ao
    # mesmo tempo os que mais emitem cerca e os que mais chegam perto do teto.
    return "\n".join(linhas[1:]).strip()


def to_xml(arm: Arm, raw: str) -> tuple[str | None, int | None, str | None]:
    """(xml, parse_ok, parse_error). Braço de XML não transpila: parse_ok fica NULL."""
    limpo = strip_fence(raw)
    if arm.emits == "xml":
        return limpo, None, None
    try:
        return transpile(limpo), 1, None
    except Exception as exc:  # falha de gramática é RESULTADO, não erro a tratar
        return None, 0, f"{type(exc).__name__}: {exc}"


def references(db: Database, sample_id: str) -> list[dict]:
    """Referência primária do PMo mais as alternativas do Zenodo com nota ≥ 4."""
    return [
        dict(r)
        for r in db.query(
            "SELECT variant, gold_xml, score FROM gold_models"
            " WHERE sample_id = ? AND (score IS NULL OR score >= ?)"
            " ORDER BY variant",
            (sample_id, MIN_REF_SCORE),
        )
    ]


ZERO = {
    "xsd_valid": 0, "df_precision": 0.0, "df_recall": 0.0, "df_f1": 0.0, "df_exact": 0,
    "df_strict_precision": 0.0, "df_strict_recall": 0.0, "df_strict_f1": 0.0,
    "df_strict_exact": 0, "nodes_match": 0, "mf_precision": 0.0, "mf_recall": 0.0,
    "mf_f1": 0.0, "ref_variant": None,
}  # fmt: skip


def score_candidate(candidate_xml: str | None, refs: list[dict]) -> dict:
    """Máximo de DF-F1 entre as referências admitidas (spec 003 §4).

    O argmax é por DF-F1 — a métrica primária — e as demais colunas vêm **da
    mesma** referência vencedora. Misturar o melhor MF-F1 de uma com o melhor
    DF-F1 de outra descreveria um modelo de referência que não existe.

    Candidato ausente ou que não transpila pontua zero, com linha gravada (AC-2).
    """
    base = dict(ZERO, n_refs=len(refs))
    if candidate_xml is None or not refs:
        return base
    valido = validate_bpmn_xsd(candidate_xml) == []
    melhor = None
    for ref in refs:
        r = compare_xml(ref["gold_xml"], candidate_xml)
        if melhor is None or r["df_f1"] > melhor[1]["df_f1"]:
            melhor = (ref["variant"], r)
    variante, r = melhor
    return {
        "xsd_valid": int(valido),
        "df_precision": r["df_precision"], "df_recall": r["df_recall"], "df_f1": r["df_f1"],
        "df_exact": int(r["df_exact"]),
        "df_strict_precision": r["df_strict_precision"],
        "df_strict_recall": r["df_strict_recall"],
        "df_strict_f1": r["df_strict_f1"], "df_strict_exact": int(r["df_strict_exact"]),
        "nodes_match": int(r["nodes_match"]),
        "mf_precision": r["mf_precision"], "mf_recall": r["mf_recall"], "mf_f1": r["mf_f1"],
        "ref_variant": variante, "n_refs": len(refs),
    }  # fmt: skip


def insert_row(db: Database, linha: dict) -> None:
    """Grava uma linha derivando o SQL das chaves do dict.

    Deliberadamente não é um INSERT escrito à mão: a versão anterior listava 29
    colunas e uma tupla posicional paralela, e ao acrescentar as quatro colunas
    `df_strict_*` a lista de colunas foi atualizada mas a tupla não — erro que
    só apareceu na primeira execução integrada. Derivando ambos da mesma fonte,
    a divergência deixa de ser possível.
    """
    cols = ", ".join(linha)
    db._conn.execute(
        f"INSERT INTO benchmark_eval ({cols}, scored_at)"
        f" VALUES ({', '.join('?' * len(linha))}, datetime('now'))",
        tuple(linha.values()),
    )
    db._conn.commit()


def generate(arm: Arm, prompt: str, descricao: str, api_key: str) -> tuple[str, bool, int]:
    """(saída, truncada, latência_ms). Sem retry: falha é resultado medido (AC-6)."""
    pedido = prompt.replace("{description}", descricao)
    if arm.backend == "local":
        from src.evaluation.local_model import generate_local  # dep pesada, opcional

        inicio = time.monotonic()
        texto, truncado = generate_local(
            pedido,
            model_id=arm.model,
            adapter=arm.adapter,
            max_tokens=arm.max_tokens,
            trust_remote_code=arm.trust_remote_code,
        )
        return texto, truncado, int((time.monotonic() - inicio) * 1000)
    inicio = time.monotonic()
    texto, meta = generate_ollama_cloud(
        pedido,
        api_key=api_key,
        model=arm.model,
        temperature=TEMPERATURE,
        num_predict=arm.max_tokens,
        with_meta=True,
    )
    return texto, meta.get("done_reason") == "length", int((time.monotonic() - inicio) * 1000)


def holdout(db: Database) -> list[dict]:
    """Só o conjunto de avaliação (AC-1). O filtro é por split, na origem."""
    return [
        dict(r)
        for r in db.query(
            "SELECT id, raw_text FROM samples WHERE source = ? AND split = ? ORDER BY id",
            (EVAL_SOURCE, HOLDOUT_SPLIT),
        )
    ]


def assert_holdout_only(db: Database, amostras: list[dict]) -> None:
    """AC-1: falha alto se um item de treino entrar no conjunto de avaliação.

    `holdout()` já filtra por split, então em operação normal isto nunca dispara.
    Existe como rede de segurança: se alguém trocar `EVAL_SOURCE`, afrouxar a
    consulta ou repovoar `samples` com split errado, o harness **para** em vez de
    produzir números contaminados que ninguém notaria depois.
    """
    treino = {
        r["id"] for r in db.query("SELECT id FROM samples WHERE split != ?", (HOLDOUT_SPLIT,))
    }
    vazados = sorted({a["id"] for a in amostras} & treino)
    if vazados:
        raise ValueError(
            f"AC-1 violado: {len(vazados)} amostra(s) de treino no conjunto de "
            f"avaliação — {vazados[:3]}"
        )


def run(args: argparse.Namespace) -> None:
    arm = ARMS[args.arm]
    prompt, digest = prompt_digest(arm.prompt)
    commit = spec_commit()

    load_dotenv()
    api_key = env_key("OLLAMA_API_KEY") if args.execute else ""

    with Database() as db:
        ensure_schema(db._conn)
        amostras = holdout(db)
        if args.limit:
            amostras = amostras[: args.limit]
        assert_holdout_only(db, amostras)

        if args.dry_run:
            print({
                "arm": args.arm, "model": arm.model, "prompt": arm.prompt,
                "prompt_sha256": digest[:12], "spec_commit": commit[:12],
                "itens": len(amostras), "k": K_REPS,
                "gerações": len(amostras) * K_REPS, "max_tokens": arm.max_tokens,
            })  # fmt: skip
            return

        if args.retranspile:
            retranspile(db, args.arm)
            return rescore(db, args.arm)

        if args.rescore:
            return rescore(db, args.arm)

        if args.restart:
            db._conn.execute("DELETE FROM benchmark_eval WHERE arm = ?", (args.arm,))
            db._conn.commit()

        feitos = {
            (r["sample_id"], r["rep"])
            for r in db.query(
                "SELECT sample_id, rep FROM benchmark_eval WHERE arm = ?", (args.arm,)
            )
        }
        if feitos:
            print(f"[resume] {len(feitos)} gerações já gravadas serão puladas")

        for rep in range(1, K_REPS + 1):
            for i, amostra in enumerate(amostras, 1):
                if (amostra["id"], rep) in feitos:
                    continue
                raw, truncada, ms, erro = "", False, None, None
                try:
                    raw, truncada, ms = generate(arm, prompt, amostra["raw_text"] or "", api_key)
                except (LLMError, OSError) as exc:
                    erro = f"{type(exc).__name__}: {exc}"
                xml, parse_ok, parse_erro = (None, None, None) if erro else to_xml(arm, raw)
                pontos = score_candidate(xml, references(db, amostra["id"]))
                insert_row(
                    db,
                    dict(
                        pontos,
                        arm=args.arm,
                        sample_id=amostra["id"],
                        rep=rep,
                        model_id=arm.model,
                        prompt_name=arm.prompt,
                        prompt_sha256=digest,
                        spec_commit=commit,
                        raw_output=raw,
                        output_xml=xml,
                        truncated=int(truncada),
                        gen_error=erro,
                        latency_ms=ms,
                        parse_ok=parse_ok,
                        parse_error=parse_erro,
                    ),
                )
                estado = erro or parse_erro or f"F1={pontos['df_f1']:.3f}"
                print(f"[{args.arm} rep{rep} {i}/{len(amostras)}] {amostra['id']}: {estado}")
        summarize(db, args.arm)


def retranspile(db: Database, braco: str) -> int:
    """Reconstrói `output_xml` a partir de `raw_output`, sem chamar o modelo.

    `rescore` sozinho parte de `output_xml` e por isso não absorve conserto na
    camada de parsing ou de transpilação — limitação registrada em
    `docs/registro-tecnico.md` e efetivamente encontrada em 2026-08-23, quando
    um `#id` redeclarado passou a gerar `xs:ID` duplicado. Regerar com o modelo
    para incorporar um conserto determinístico seria trocar a saída avaliada;
    re-transpilar mantém a geração intacta e refaz só a parte determinística.

    Devolve quantas linhas mudaram de XML.
    """
    arm = ARMS[braco]
    linhas = db.query(
        "SELECT id, raw_output, output_xml FROM benchmark_eval"
        " WHERE arm = ? AND raw_output IS NOT NULL",
        (braco,),
    )
    mudadas = 0
    for linha in linhas:
        xml, parse_ok, parse_error = to_xml(arm, linha["raw_output"])
        if (xml or "") == (linha["output_xml"] or ""):
            continue
        mudadas += 1
        db._conn.execute(
            "UPDATE benchmark_eval SET output_xml=?, parse_ok=?, parse_error=? WHERE id=?",
            (xml, parse_ok, parse_error, linha["id"]),
        )
    db._conn.commit()
    print(f"[retranspile] {len(linhas)} linhas relidas, {mudadas} com XML alterado")
    return mudadas


def rescore(db: Database, braco: str) -> None:
    """Repontua saídas já gravadas. Determinístico — é o AC-3."""
    linhas = db.query(
        "SELECT id, sample_id, output_xml FROM benchmark_eval WHERE arm = ?", (braco,)
    )
    for linha in linhas:
        p = score_candidate(linha["output_xml"], references(db, linha["sample_id"]))
        db._conn.execute(
            "UPDATE benchmark_eval SET xsd_valid=?, df_precision=?, df_recall=?, df_f1=?,"
            " df_exact=?, nodes_match=?, mf_precision=?, mf_recall=?, mf_f1=?, ref_variant=?,"
            " n_refs=?, scored_at=datetime('now') WHERE id=?",
            (
                p["xsd_valid"],
                p["df_precision"],
                p["df_recall"],
                p["df_f1"],
                p["df_exact"],
                p["nodes_match"],
                p["mf_precision"],
                p["mf_recall"],
                p["mf_f1"],
                p["ref_variant"],
                p["n_refs"],
                linha["id"],
            ),  # fmt: skip
        )
    db._conn.commit()
    print(f"[rescore] {len(linhas)} linhas repontuadas")
    summarize(db, braco)


def per_item_medians(db: Database, braco: str, coluna: str = "df_f1") -> dict[str, float]:
    """Mediana das k execuções de cada item — a unidade de análise da §6.3.

    Mediana e não média: o ADR 0003 mostrou saídas ocasionalmente degeneradas, e
    uma execução que falha o XSD puxaria a média de forma desproporcional.
    """
    valores: dict[str, list[float]] = {}
    for r in db.query(
        f"SELECT sample_id, {coluna} v FROM benchmark_eval WHERE arm = ? ORDER BY sample_id, rep",
        (braco,),
    ):
        valores.setdefault(r["sample_id"], []).append(r["v"] or 0.0)
    return {s: statistics.median(v) for s, v in valores.items()}


def summarize(db: Database, braco: str) -> None:
    """Resumo do braço. O número reportado é a média **das medianas por item**.

    Média direta sobre as 159 linhas daria peso maior a itens cujas execuções
    divergiram, que é exatamente o que a mediana por item existe para evitar.
    """
    contagens = db.query(
        """SELECT COUNT(*) n, SUM(gen_error IS NOT NULL) erros, SUM(truncated) truncadas,
                  SUM(COALESCE(parse_ok, 1)) parse_ok, SUM(xsd_valid) xsd
           FROM benchmark_eval WHERE arm = ?""",
        (braco,),
    )[0]
    medianas = per_item_medians(db, braco)
    estritas = per_item_medians(db, braco, "df_strict_f1")
    # Dispersão intra-item: evidência empírica do ADR 0003, exigida pela §6.3.
    espalhamento: dict[str, float] = {}
    for r in db.query("SELECT sample_id, df_f1 FROM benchmark_eval WHERE arm = ?", (braco,)):
        espalhamento.setdefault(r["sample_id"], []).append(r["df_f1"] or 0.0)
    amplitudes = [max(v) - min(v) for v in espalhamento.values() if len(v) > 1]

    print(f"\n== {braco} ==")
    print(dict(contagens))
    if medianas:
        print(
            {
                "itens": len(medianas),
                "df_f1_mediana_por_item": round(statistics.mean(medianas.values()), 4),
                "df_strict_f1": round(statistics.mean(estritas.values()), 4) if estritas else None,
                "dispersao_intra_item_max": round(max(amplitudes), 4) if amplitudes else 0.0,
                "itens_com_divergencia": sum(a > 0 for a in amplitudes),
            }
        )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--arm", required=True, choices=sorted(ARMS))
    p.add_argument("--execute", action="store_true", help="Sem isto, só planeja.")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--rescore", action="store_true", help="Repontua sem gerar.")
    p.add_argument(
        "--retranspile",
        action="store_true",
        help="Refaz output_xml a partir de raw_output e repontua. Absorve conserto"
        " determinístico (parsing/transpilação) sem chamar o modelo.",
    )
    p.add_argument("--restart", action="store_true", help="Apaga o braço e recomeça.")
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args()
    if not (args.execute or args.dry_run or args.rescore or args.retranspile):
        args.dry_run = True
    return args


if __name__ == "__main__":
    run(parse_args())
