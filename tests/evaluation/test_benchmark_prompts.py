"""Invariantes dos prompts dos braços (spec 003 §4, §6.2).

Estes testes não medem qualidade de prompt — travam as garantias de **justiça
do desenho experimental**, que são parte do pré-registro. Se um deles quebrar, o
contraste A2 vs A1 deixou de isolar o efeito da DSL, e o resultado do benchmark
não sustenta a hipótese H1.
"""

from __future__ import annotations

import re

import pytest

from src.data.llm.utils import load_prompt
from src.evaluation.topology import compare_xml
from src.transpiler.xml import transpile
from src.transpiler.xsd import validate_bpmn_xsd

BRACOS = ("benchmark/xml_direct.md", "benchmark/dsl_grammar.md", "benchmark/dsl_minimal.md")
COMPARTILHADOS = ("role", "language", "modeling_rules", "output_contract")


def _sem_comentario(texto: str) -> str:
    """Remove comentários HTML.

    Necessário: os comentários de cabeçalho citam nomes de tag literalmente
    (ex.: "o bloco <modeling_rules> permanece idêntico"), e sem removê-los um
    casamento ingênuo de regex começa dentro do comentário.
    """
    return re.sub(r"<!--.*?-->", "", texto, flags=re.S)


def bloco(texto: str, tag: str) -> str | None:
    achado = re.search(rf"<{tag}>(.*?)</{tag}>", _sem_comentario(texto), re.S)
    return achado.group(1) if achado else None


def exemplo_de_notacao(nome: str) -> str:
    corpo = bloco(load_prompt(nome), "notation_example")
    assert corpo is not None, f"{nome} não tem <notation_example>"
    return corpo.split("study.\n", 1)[1].strip()


@pytest.mark.parametrize("tag", COMPARTILHADOS)
def test_blocos_compartilhados_sao_identicos(tag):
    """A única diferença permitida entre os prompts é o formato de saída.

    Instrução de modelagem diferente entre braços faria o benchmark medir
    "qual prompt é melhor" em vez de "qual formato é melhor".
    """
    valores = {nome: bloco(load_prompt(nome), tag) for nome in BRACOS}
    assert all(v is not None for v in valores.values()), f"<{tag}> ausente: {valores}"
    assert len(set(valores.values())) == 1, f"<{tag}> diverge entre os braços"


def test_exemplo_da_dsl_parseia_e_transpila():
    xml = transpile(exemplo_de_notacao("benchmark/dsl_grammar.md"))
    assert validate_bpmn_xsd(xml) == []


def test_exemplo_do_xml_e_valido_no_xsd():
    assert validate_bpmn_xsd(exemplo_de_notacao("benchmark/xml_direct.md")) == []


def test_os_dois_exemplos_sao_o_mesmo_processo():
    """Garantia central de justiça: nenhum braço recebe padrão de modelagem que
    o outro não recebeu. Os exemplos diferem só em notação."""
    xml_da_dsl = transpile(exemplo_de_notacao("benchmark/dsl_grammar.md"))
    resultado = compare_xml(exemplo_de_notacao("benchmark/xml_direct.md"), xml_da_dsl)
    assert resultado["df_exact"], resultado
    assert resultado["df_f1"] == 1.0
    assert resultado["nodes_match"]


def test_prompt_do_a4_nao_carrega_gramatica():
    """A4 é o modelo finetunado: a linguagem está nos pesos.

    Acrescentar gramática aqui quebraria o casamento com o prompt de treino do
    SFT (o modelo passaria a inferir fora da distribuição) e enfraqueceria o
    argumento econômico da tese, movendo custo da saída para a entrada.
    """
    minimal = load_prompt("benchmark/dsl_minimal.md")
    assert bloco(minimal, "notation_example") is None
    formato = bloco(minimal, "output_format")
    assert len(formato.split()) < 10, "output_format do A4 deixou de ser mínimo"
    for palavra in ("xor", "@lane", "subprocess", "TASK_TYPE", "->"):
        assert palavra not in formato, f"gramática vazou para o prompt do A4: {palavra!r}"


def test_prompt_de_xml_proibe_diagram_interchange():
    """Proibir BPMNDI favorece o baseline: o teto de 8192 tokens vai inteiro
    para a lógica do processo, e a métrica ignora layout de qualquer forma."""
    formato = bloco(load_prompt("benchmark/xml_direct.md"), "output_format")
    assert "BPMNDiagram" in formato and "Do NOT emit" in formato


@pytest.mark.parametrize("nome", BRACOS)
def test_todo_prompt_tem_slot_de_entrada(nome):
    assert "{description}" in load_prompt(nome)
