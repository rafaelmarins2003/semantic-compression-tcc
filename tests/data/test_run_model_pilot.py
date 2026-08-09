"""Heurística de idioma do piloto (spec 004 §4.1b).

A primeira versão marcava `do` e `com` como português e reprovava rótulos
ingleses legítimos ("Do the review"). Estes testes travam a correção.
"""

from __future__ import annotations

import pytest

from src.data.llm.run_model_pilot import _PT_CHARS, _PT_WORDS


def _is_pt(label: str) -> bool:
    return bool(_PT_CHARS.search(label) or _PT_WORDS.search(label))


@pytest.mark.parametrize(
    "label",
    [
        "Do the review",
        "Check com port",
        "Update do-not-call list",
        "Send confirmation to customer",
        "Provide quote",
        "Review Request",
        "Sim card activation",
    ],
)
def test_english_labels_are_not_flagged(label):
    assert not _is_pt(label)


@pytest.mark.parametrize(
    "label",
    [
        "Registrar solicitação",
        "Análise de crédito",
        "Enviar para o cliente",
        "Aprovação",
        "Não conforme",
    ],
)
def test_portuguese_labels_are_flagged(label):
    assert _is_pt(label)
