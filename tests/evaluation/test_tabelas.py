"""Convenção da coluna de rótulos alinhados (tab:res-oraculo).

A coluna existiu por semanas com convenção não documentada e divergente entre
linhas — duas células vinham de sonda primária-only e as demais da regra do
máximo, e nenhuma reproduzia. Estes testes fixam a definição em código, que é o
que faltava: o número da monografia passa a ter uma referência executável.
"""

from src.evaluation.topology import label_alignment
from src.transpiler.xml import transpile

DOIS = 'process "P" { start -> task "Provide Quote" -> task "Ship Order" -> end }'


def xml(dsl: str) -> str:
    return transpile(dsl)


def test_documento_identico_alinha_tudo():
    assert label_alignment(xml(DOIS), xml(DOIS)) == 1.0


def test_caixa_e_pontuacao_nao_contam_como_divergencia():
    outro = 'process "P" { start -> task "provide quote" -> task "ship, order" -> end }'
    assert label_alignment(xml(DOIS), xml(outro)) == 1.0


def test_metade_dos_rotulos_casa():
    outro = 'process "P" { start -> task "Provide Quote" -> task "Archive Invoice" -> end }'
    assert label_alignment(xml(DOIS), xml(outro)) == 0.5


def test_eventos_anonimos_nao_inflam_a_taxa():
    """Sem excluir `<start>`/`<end>`, dois processos sem um rótulo em comum
    pontuariam 0,5 só por ambos terem início e fim — a coluna mediria tipo de
    evento, não denominação de atividade."""
    outro = 'process "P" { start -> task "Archive Invoice" -> task "Notify Team" -> end }'
    assert label_alignment(xml(DOIS), xml(outro)) == 0.0
