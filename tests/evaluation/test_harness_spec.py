"""Critérios de aceitação do harness (spec 003 §5, AC-1 a AC-8).

Os ACs descrevem **comportamento do harness**, nunca resultado do experimento:
nenhum teste aqui afirma que a DSL vence. Resultado esperado é hipótese (§6.1) e
não vira teste — é justamente o que o pré-registro protege.

Os testes de escrita usam banco temporário. Os de leitura pulam quando a base de
pesquisa não está disponível, para não quebrar a suíte num clone sem o dataset.
"""

from __future__ import annotations

import sqlite3

import pytest

from src.data.db import _DB_PATH, HOLDOUT_SPLIT, Database
from src.data.migrations.create_benchmark_eval import ensure_schema
from src.evaluation import run_benchmark as rb
from src.evaluation.run_tcr import ratios, strip_di
from src.transpiler.layout import add_layout
from src.transpiler.xml import transpile

# Gerado pelo próprio transpiler, e não escrito à mão: o XML do corpus é
# serializado por uma única rotina, e um fixture com espaçamento idiossincrático
# faria o AC-4 comparar formatação em vez de conteúdo.
XML_MINIMO = transpile('process "T" { start -> task "Do work" -> end }')


@pytest.fixture
def banco(tmp_path):
    """Banco temporário com o esquema real, uma amostra de holdout e uma de treino."""
    caminho = tmp_path / "t.db"
    with Database(caminho) as db:  # deixa o próprio Database criar o esquema
        db._conn.execute(
            "INSERT INTO samples (id, source, stage, split, raw_text)"
            " VALUES ('pmo_x','pmo','descriptions',?,'texto')",
            (HOLDOUT_SPLIT,),
        )
        db._conn.execute(
            "INSERT INTO samples (id, source, stage, split, raw_text)"
            " VALUES ('gl_y','gitlab_handbook','curated','sft','texto')"
        )
        ensure_schema(db._conn)
        db._conn.executescript(
            "CREATE TABLE IF NOT EXISTS gold_models (id INTEGER PRIMARY KEY,"
            " sample_id TEXT, source TEXT, variant TEXT, format TEXT, gold_xml TEXT,"
            " score REAL, source_file TEXT);"
        )
        db._conn.execute(
            "INSERT INTO gold_models (sample_id, source, variant, format, gold_xml,"
            " score, source_file) VALUES ('pmo_x','pmo','primary','bpmn2',?,NULL,'x.bpmn')",
            (XML_MINIMO,),
        )
        db._conn.commit()
        yield db


def _linha(db, **campos):
    """Grava uma linha de benchmark com o mínimo de proveniência exigido."""
    base = dict(
        arm="A2", sample_id="pmo_x", rep=1, model_id="m", prompt_name="p",
        prompt_sha256="abc", spec_commit="deadbeef",
    )  # fmt: skip
    base.update(campos)
    cols = ",".join(base)
    db._conn.execute(
        f"INSERT INTO benchmark_eval ({cols}) VALUES ({','.join('?' * len(base))})",
        tuple(base.values()),
    )
    db._conn.commit()


# ── AC-1 ──────────────────────────────────────────────────────────────────────


def test_ac1_refuses_training_samples(banco):
    """Item de treino no conjunto avaliado tem de parar o harness, não passar."""
    contaminado = [{"id": "gl_y"}, {"id": "pmo_x"}]

    with pytest.raises(ValueError, match="AC-1"):
        rb.assert_holdout_only(banco, contaminado)

    rb.assert_holdout_only(banco, [{"id": "pmo_x"}])  # holdout puro não levanta


def test_ac1_holdout_query_selects_only_holdout(banco):
    assert [a["id"] for a in rb.holdout(banco)] == ["pmo_x"]


# ── AC-2 ──────────────────────────────────────────────────────────────────────


def test_ac2_invalid_xml_scores_zero(banco):
    """XML inválido pontua zero **com linha gravada** — nunca exceção nem ausência."""
    refs = rb.references(banco, "pmo_x")

    for candidato in ("<definitions><naofecha", "", None):
        pontos = rb.score_candidate(candidato, refs)
        assert pontos["df_f1"] == 0.0
        assert pontos["xsd_valid"] == 0
        assert pontos["df_exact"] == 0

    _linha(banco, **rb.score_candidate("<quebrado", refs))
    gravadas = banco.query("SELECT df_f1, xsd_valid FROM benchmark_eval")
    assert len(gravadas) == 1 and gravadas[0]["df_f1"] == 0.0


# ── AC-3 ──────────────────────────────────────────────────────────────────────


def test_ac3_rerun_is_deterministic(banco):
    """Repontuar duas vezes produz linhas idênticas exceto o carimbo de tempo.

    Só é satisfazível porque a pontuação está separada da geração: repontuar não
    chama o modelo, e o ADR 0003 mostrou que a geração não é determinística.
    """
    _linha(banco, output_xml=XML_MINIMO)
    campos = (
        "arm, sample_id, rep, xsd_valid, df_precision, df_recall, df_f1, df_exact,"
        " nodes_match, mf_precision, mf_recall, mf_f1, ref_variant, n_refs"
    )

    rb.rescore(banco, "A2")
    primeira = [tuple(r) for r in banco.query(f"SELECT {campos} FROM benchmark_eval")]
    rb.rescore(banco, "A2")
    segunda = [tuple(r) for r in banco.query(f"SELECT {campos} FROM benchmark_eval")]

    assert primeira == segunda
    assert primeira[0][6] == 1.0, "gold contra si mesmo tem de dar DF-F1 = 1"


# ── AC-4 ──────────────────────────────────────────────────────────────────────


def test_ac4_tcr_ignores_layout():
    """A TCR é invariante a BPMNDI: o mesmo processo com e sem layout dá o mesmo
    valor. Sem `strip_di`, materializar layout na coluna inflaria a métrica ~3x
    em silêncio — o erro dos "91%", já cometido uma vez neste projeto.

    A invariância vale a menos de espaço em branco final: `strip_di` reserializa
    e não recoloca a quebra de linha terminal. Imaterial (1 token em ~1000) e
    inalcançável em produção, onde a função é identidade por não haver DI.
    """
    tok = lambda t, **_: {"input_ids": list(t)}  # noqa: E731 — tokenizador de teste
    com_layout = add_layout(XML_MINIMO)
    assert len(com_layout) > len(XML_MINIMO) * 1.5, "o fixture precisa de fato ter DI"

    assert strip_di(com_layout).strip() == XML_MINIMO.strip()
    assert "BPMNDiagram" not in strip_di(com_layout)

    linha = lambda x: [{"input_dsl": "d", "output_xml": x.strip()}]  # noqa: E731
    assert ratios(linha(com_layout), tok, with_layout=False) == pytest.approx(
        ratios(linha(XML_MINIMO), tok, with_layout=False)
    )


def test_ac4_with_layout_flag_is_opt_in_and_inflates():
    """`--with-layout` existe só para demonstrar o viés; nunca é o caminho padrão."""
    tok = lambda t, **_: {"input_ids": list(t)}  # noqa: E731
    linha = [{"input_dsl": "d", "output_xml": XML_MINIMO}]

    assert ratios(linha, tok, with_layout=True) > ratios(linha, tok, with_layout=False)


# ── AC-5 ──────────────────────────────────────────────────────────────────────


def test_ac5_df_delegates_to_topology(banco, monkeypatch):
    """O harness não pode reimplementar a projeção: uma segunda implementação
    divergiria da usada no eixo 2 e os números deixariam de ser comparáveis."""
    chamadas = []
    real = rb.compare_xml

    def espiao(gold, cand):
        chamadas.append((gold, cand))
        return real(gold, cand)

    monkeypatch.setattr(rb, "compare_xml", espiao)
    rb.score_candidate(XML_MINIMO, rb.references(banco, "pmo_x"))

    assert len(chamadas) == 1, "score_candidate tem de delegar a topology.compare_xml"


# ── AC-6 ──────────────────────────────────────────────────────────────────────


def test_ac6_no_silent_retry():
    """Falha de parse vira `parse_ok=0` e o erro é preservado — sem regerar.

    Retry esconderia a taxa de falha sintática, que é resultado da tese: é
    exatamente o que a transpilação determinística promete eliminar.
    """
    xml, parse_ok, erro = rb.to_xml(rb.ARMS["A2"], 'process { "isto nao parseia"')

    assert xml is None
    assert parse_ok == 0
    assert erro and "Unexpected" in erro


def test_ac6_generation_is_called_once_per_item(monkeypatch):
    """Sem laço de repetição escondido no caminho de geração."""
    chamadas = []

    def falso(*a, **k):
        chamadas.append(1)
        raise rb.LLMError("falha simulada")

    monkeypatch.setattr(rb, "generate_ollama_cloud", falso)
    with pytest.raises(rb.LLMError):
        rb.generate(rb.ARMS["A2"], "{description}", "texto", "chave")

    assert len(chamadas) == 1


# ── AC-7 ──────────────────────────────────────────────────────────────────────


def test_ac7_provenance_columns_present(banco):
    """Todo número da tese tem de ser rastreável até o spec que o gerou."""
    _linha(banco, output_xml=XML_MINIMO)
    linha = banco.query(
        "SELECT arm, model_id, prompt_name, prompt_sha256, spec_commit FROM benchmark_eval"
    )[0]

    assert all(linha[c] for c in linha.keys()), f"proveniência incompleta: {dict(linha)}"


def test_ac7_prompt_hash_identifies_the_prompt():
    """`prompt_sha256` concretiza o `prompt_version` do spec: prompts diferentes
    têm hashes diferentes, e o mesmo prompt é estável entre execuções."""
    _, h1 = rb.prompt_digest("benchmark/dsl_grammar.md")
    _, h2 = rb.prompt_digest("benchmark/dsl_grammar.md")
    _, outro = rb.prompt_digest("benchmark/dsl_minimal.md")

    assert h1 == h2 and h1 != outro and len(h1) == 64


# ── AC-8 ──────────────────────────────────────────────────────────────────────


def test_ac8_rerun_replaces_rows(banco):
    """Reexecutar substitui as linhas do braço em vez de duplicar."""
    _linha(banco, output_xml=XML_MINIMO)
    _linha(banco, arm="A1", output_xml=XML_MINIMO)

    with pytest.raises(sqlite3.IntegrityError):
        _linha(banco, output_xml=XML_MINIMO)  # mesmo (arm, sample_id, rep)

    banco._conn.rollback()
    banco._conn.execute("DELETE FROM benchmark_eval WHERE arm = 'A2'")
    _linha(banco, output_xml=XML_MINIMO)

    assert len(banco.query("SELECT 1 FROM benchmark_eval WHERE arm='A2'")) == 1
    assert len(banco.query("SELECT 1 FROM benchmark_eval WHERE arm='A1'")) == 1, (
        "apagar um braço não pode afetar os demais"
    )


# ── integração com a base real ────────────────────────────────────────────────


def test_arms_cobrem_os_bracos_do_spec():
    """A3m é o controle de A4: mesmo modelo e mesmo prompt, sem o adapter."""
    assert sorted(rb.ARMS) == ["A1", "A1g", "A2", "A2g", "A3", "A3m", "A4"]
    assert rb.ARMS["A3m"].prompt == rb.ARMS["A4"].prompt
    assert rb.ARMS["A3m"].model == rb.ARMS["A4"].model
    assert rb.ARMS["A3m"].adapter is None and rb.ARMS["A4"].adapter
    assert rb.K_REPS == 3 and rb.TEMPERATURE == 0.0 and rb.MIN_REF_SCORE == 4.0
    assert {a.max_tokens for a in rb.ARMS.values() if a.emits == "xml"} == {8192}
    assert {a.max_tokens for a in rb.ARMS.values() if a.emits == "dsl"} == {2048}


def test_conjunto_de_avaliacao_tem_53_itens():
    if not _DB_PATH.exists():
        pytest.skip("banco de pesquisa não disponível")
    with Database(read_only=True) as db:
        assert len(rb.holdout(db)) == 53


# ── TCR por braço (spec 003 §6.1, H4) ────────────────────────────────────────


def _tok_falso(t, **_):
    """Tokenizador de teste: um token por caractere. Evita baixar o Qwen."""
    return {"input_ids": list(t)}


def test_tcr_por_braco_mede_dsl_contra_xml(banco):
    """Braço de DSL: TCR = tokens(XML reconstituído) / tokens(DSL emitida)."""
    from src.evaluation.run_tcr import arm_report

    _linha(banco, arm="A2", raw_output='process "P" { start -> end }', output_xml=XML_MINIMO)
    r = arm_report(banco, "A2", _tok_falso)

    assert r["emite"] == "dsl"
    assert r["tcr_mean"] > 1.0, "o XML tem de ser mais verboso que a DSL"
    assert r["tokens_emitidos_mediana"] == len('process "P" { start -> end }')
    assert r["reducao_pct"] > 0


def test_tcr_nao_se_aplica_a_braco_de_xml_direto(banco):
    """Sem representação intermediária não há compressão a medir. Reportar 1,0
    como se fosse resultado confundiria o leitor."""
    from src.evaluation.run_tcr import arm_report

    _linha(banco, arm="A1", raw_output=XML_MINIMO, output_xml=XML_MINIMO)
    r = arm_report(banco, "A1", _tok_falso)

    assert r["emite"] == "xml"
    assert "tcr_mean" not in r
    assert "não se aplica" in r["tcr"]
    # `strip_fence` normaliza a saída antes de contar — a mesma normalização que
    # a pontuação usa, então o número de tokens reflete o que foi de fato medido.
    assert r["tokens_emitidos_mediana"] == len(XML_MINIMO.strip()), "tokens valem sempre"


def test_strip_fence_remove_cerca_sem_fechamento():
    """Saída truncada pelo teto de tokens não tem cerca de fechamento.

    Regressão do A3m (2026-08-16): exigir o par ``` deixava a abertura no texto
    e reprovava o candidato por defeito do harness, não do modelo. O viés não é
    neutro — os braços de XML são os que mais emitem cerca e os que mais se
    aproximam do teto, então o bug penalizava justamente o baseline.
    """
    from src.evaluation.run_benchmark import strip_fence

    truncada = '```xml\n<definitions>\n  <process id="p"'
    assert strip_fence(truncada) == '<definitions>\n  <process id="p"'

    # o caso fechado continua valendo, e a cerca interna não é tocada
    fechada = '```dsl\nprocess "P" { start -> end }\n```'
    assert strip_fence(fechada) == 'process "P" { start -> end }'
    assert strip_fence("sem cerca alguma") == "sem cerca alguma"


def test_tcr_por_braco_ignora_linha_sem_saida(banco):
    """Falha de geração não entra na TCR, mas aparece na contagem."""
    from src.evaluation.run_tcr import arm_report

    _linha(banco, arm="A2", rep=1, raw_output="", gen_error="LLMError: falhou")
    _linha(banco, arm="A2", rep=2, raw_output='process "P" { start -> end }',
           output_xml=XML_MINIMO)  # fmt: skip
    r = arm_report(banco, "A2", _tok_falso)

    assert r["n"] == 2 and r["sem_saida"] == 1
    assert r["n_tcr"] == 1


def test_tcr_por_braco_sem_dados(banco):
    from src.evaluation.run_tcr import arm_report

    assert arm_report(banco, "A4", _tok_falso)["estado"] == "sem dados"
