"""Invariantes dos prompts dos braços (spec 003 §4, §6.2).

Estes testes não medem qualidade de prompt — travam as garantias de **justiça
do desenho experimental**, que são parte do pré-registro. Se um deles quebrar, o
contraste A2 vs A1 deixou de isolar o efeito da DSL, e o resultado do benchmark
não sustenta a hipótese H1.
"""

from __future__ import annotations

import re

import pytest
from lark.exceptions import UnexpectedInput

from src.data.llm.utils import load_prompt
from src.dsl.parser import parse
from src.evaluation.run_benchmark import prompt_digest
from src.evaluation.topology import compare_xml
from src.transpiler.xml import transpile
from src.transpiler.xsd import validate_bpmn_xsd

BRACOS = (
    "benchmark/xml_direct.md",
    "benchmark/dsl_grammar.md",
    "benchmark/dsl_minimal.md",
    "benchmark/dsl_grammar_labelref.md",
)
PROMPTS_COM_GRAMATICA = ("benchmark/dsl_grammar.md", "benchmark/dsl_grammar_labelref.md")
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


# --- Gramática do prompt vs. grammar.lark -------------------------------------
# O <output_format> de `dsl_grammar.md` é uma gramática em prosa, escrita à mão,
# independente de `grammar.lark`. Se as duas divergirem, uma falha do A2 pode ser
# defeito do prompt e não limitação do modelo (foi o caso da emenda E-1). Cada
# entrada abaixo é (trecho literal do prompt, programa mínimo que o exercita).
# Listados à mão, não extraídos por regex: os trechos são fragmentos, e uma lista
# explícita é auditável por quem lê.


def _proc(flow: str) -> str:
    return f'process "P" {{ {flow} }}'


CONSTRUCOES_DOCUMENTADAS = [
    ('start "Name"', _proc('start "Name" -> end')),
    ("start                   end", _proc("start -> end")),
    ('end:error "Timeout"', _proc('start -> end:error "Timeout"')),
    ('catch:timer "After 3d"', _proc('start -> catch:timer "After 3d" -> end')),
    ('throw:message "Notify"', _proc('start -> throw:message "Notify" -> end')),
    (
        "task | user | service | manual | script | send | receive | rule",
        _proc(
            'start -> task "a" -> user "b" -> service "c" -> manual "d" -> script "e"'
            ' -> send "f" -> receive "g" -> rule "h" -> end'
        ),
    ),
    ('xor "Question?" {', _proc('start -> xor "Q?" { ["c1"] -> task "a" ["c2"] -> task "b" }')),
    ('or  "Question?" {', _proc('start -> or "Q?" { ["c1"] -> task "a" ["c2"] -> task "b" }')),
    (
        "and             { FLOW ; FLOW ; FLOW }",
        _proc('start -> and { task "a" ; task "b" ; task "c" }'),
    ),
    ("[:message] -> FLOW", _proc('start -> event { [:message] -> task "a" [:timer] -> task "b" }')),
    ('["no"] -> ()', _proc('start -> xor "Q?" { ["yes"] -> task "a" ["no"] -> () } -> end')),
    (
        'task "Fetch" #fetch',
        _proc('start -> task "Fetch" #fetch -> xor "ok?" { ["no"] -> #fetch ["yes"] -> end }'),
    ),
    (
        '@lane "Actor" { FLOW }',
        'process "P" { @lane "A" { start -> task "x" } @lane "B" { -> task "y" -> end } }',
    ),
    (
        'subprocess "Name" { BODY }',
        _proc('start -> subprocess "S" { start -> task "a" -> end } -> end'),
    ),
    ('call "Name"', _proc('start -> call "C" -> end')),
    (
        'message "Name" from #source to #target',
        'collaboration "C" { pool "A" { start -> send "s" #s -> end }'
        ' pool "B" { start -> receive "r" #r -> end } message "m" from #s to #r }',
    ),
    ('pool "Name" { BODY }', 'pool "P" { start -> end }'),
    ('note "Free text"', 'note "x" process "P" { start -> end }'),
    (
        'task "Ship" (performer="Carrier", dueDate="P3D")',
        _proc('start -> task "Ship" (performer="Carrier", dueDate="P3D") -> end'),
    ),
    ("// starts a comment.", _proc("start // comentário\n -> end")),
]

# O que o prompt declara inválido precisa falhar no parser.
CONSTRUCOES_PROIBIDAS = [
    ("`catch` and `throw` require a kind", _proc('start -> catch "X" -> end')),
    ("`and` branches ... are separated by `;`", _proc('start -> and { task "a" task "b" }')),
    ("Ids are never quoted", _proc('start -> task "a" #"a" -> end')),
]


# Só o prompt do A2r documenta referência por rótulo (registro-tecnico, A2r).
CONSTRUCOES_DO_A2R = [
    (
        '#"Label"',
        _proc('start -> task "Fetch data" -> xor "ok?" { ["no"] -> #"Fetch data" ["yes"] -> end }'),
    ),
    (
        'task "Fetch data" -> ... -> #"Fetch data"',
        _proc('start -> task "Fetch data" -> task "b" -> #"Fetch data"'),
    ),
    ("#fetch to point at it from anywhere", _proc('start -> #fetch -> task "Fetch" #fetch -> end')),
    ("events, tasks, `call` and `message` only", _proc('start -> call "C" (a="b") -> end (c="d")')),
]


def _formato_dsl(nome: str = "benchmark/dsl_grammar.md") -> str:
    return bloco(load_prompt(nome), "output_format")


@pytest.mark.parametrize("nome", PROMPTS_COM_GRAMATICA)
@pytest.mark.parametrize(("trecho", "programa"), CONSTRUCOES_DOCUMENTADAS, ids=lambda v: v[:30])
def test_construcao_documentada_no_prompt_parseia(trecho, programa, nome):
    assert trecho in _formato_dsl(nome), f"trecho não está mais em {nome}: {trecho!r}"
    parse(programa)


@pytest.mark.parametrize(("trecho", "programa"), CONSTRUCOES_DO_A2R, ids=lambda v: v[:30])
def test_construcao_do_a2r_transpila(trecho, programa):
    assert trecho in _formato_dsl("benchmark/dsl_grammar_labelref.md"), trecho
    assert validate_bpmn_xsd(transpile(programa)) == []


def test_a2r_difere_do_a2_so_nas_referencias_e_nas_duas_correcoes():
    """O A2r só isola o mecanismo de referência se nada mais mudar. Os
    comentários HTML também contam: `load_prompt` não os remove, então eles
    chegam ao modelo."""
    a2 = load_prompt("benchmark/dsl_grammar.md")
    a2r = load_prompt("benchmark/dsl_grammar_labelref.md")

    def sem_trechos_alterados(texto: str) -> str:
        texto = re.sub(r"\n(IDENTIFIERS AND )?REFERENCES\n.*?\n\n", "\n", texto, flags=re.S)
        return re.sub(r"\nPROPERTIES — [^\n]*", "", texto)

    assert sem_trechos_alterados(a2) == sem_trechos_alterados(a2r)
    assert a2 != a2r


@pytest.mark.parametrize(("regra", "programa"), CONSTRUCOES_PROIBIDAS, ids=lambda v: v[:30])
def test_construcao_proibida_pelo_prompt_falha(regra, programa):
    with pytest.raises(UnexpectedInput):
        parse(programa)


# Hashes gravados em `benchmark_eval.prompt_sha256` (registro-tecnico, auditoria
# de proveniência). Editar um destes arquivos desliga as linhas já geradas do
# texto que as produziu: correção vai para um prompt novo, não para o congelado.
PROMPTS_CONGELADOS = {
    "benchmark/xml_direct.md": "0dbf1e014ff2",
    "benchmark/dsl_grammar.md": "c6bb757ea9b1",
    "benchmark/dsl_minimal.md": "11eaf38e2435",
    "benchmark/dsl_grammar_labelref.md": "b49d66cbcc41",
}


@pytest.mark.parametrize(("nome", "sha"), PROMPTS_CONGELADOS.items())
def test_prompt_congelado_nao_mudou(nome, sha):
    assert prompt_digest(nome)[1][:12] == sha
