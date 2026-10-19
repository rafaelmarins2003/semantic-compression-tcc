"""Migration: cria a tabela `perturbation_cases` (validação do juiz por perturbação).

Uma linha por caso: o gold do PMo intacto, um mutante com 1 defeito por operador
aplicável, um mutante com 3 defeitos e uma paráfrase. Os mutantes são
determinísticos (semente = id do caso); a paráfrase vem de um LLM e por isso fica
gravada, com o mapeamento de rótulos em `detail`, para que a análise seja
recalculável sem rede.
"""

from __future__ import annotations

import sqlite3

CREATE_PERTURBATION_CASES_TABLE = """
CREATE TABLE IF NOT EXISTS perturbation_cases (
    case_id     TEXT PRIMARY KEY,   -- '<sample_id>:<kind>'
    sample_id   TEXT NOT NULL,
    kind        TEXT NOT NULL,      -- intact | <operador> | triple | paraphrase
    n_defects   INTEGER NOT NULL,   -- 0, 1 ou 3 (paráfrase: 0)
    operators   TEXT NOT NULL,      -- JSON: operadores aplicados
    detail      TEXT,               -- JSON: mapeamento da paráfrase e modelo usado
    xml         TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now'))
);
"""


def ensure_schema(con: sqlite3.Connection) -> None:
    con.executescript(CREATE_PERTURBATION_CASES_TABLE)
