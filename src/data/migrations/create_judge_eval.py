"""Migration: cria a tabela `judge_eval` (P1 da auditoria de 2026-10-14).

Uma linha por (alvo, repetição, versão do prompt). O alvo é um modelo do Zenodo
(validação do juiz, T5) ou uma saída do benchmark (fidelidade dos braços, T6).
`prompt_sha` faz parte da chave: se a rubrica mudar, as notas antigas ficam
gravadas ao lado das novas, e todas as tentativas podem ser reportadas.

Falha de chamada não vira linha: o alvo continua pendente e entra na próxima
execução. O resumo de cada execução conta as falhas.
"""

from __future__ import annotations

import sqlite3

CREATE_JUDGE_EVAL_TABLE = """
CREATE TABLE IF NOT EXISTS judge_eval (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    target            TEXT    NOT NULL,  -- 'zenodo:E_j01/3' ou 'bench:<benchmark_eval.id>'
    kind              TEXT    NOT NULL,  -- 'zenodo' | 'benchmark'
    sample_id         TEXT    NOT NULL,  -- processo do Zenodo ou item do PMo
    arm               TEXT,              -- só para kind='benchmark'
    expert_score      REAL,              -- só para kind='zenodo'
    rep               INTEGER NOT NULL,
    model_id          TEXT    NOT NULL,
    prompt_sha        TEXT    NOT NULL,
    score             REAL    NOT NULL,
    problems          TEXT    NOT NULL,  -- JSON: problemas por critério
    finish_reason     TEXT,
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    reasoning_tokens  INTEGER,
    latency_ms        INTEGER,
    created_at        TEXT DEFAULT (datetime('now')),
    UNIQUE(target, rep, prompt_sha)
);

CREATE INDEX IF NOT EXISTS idx_judge_eval_kind ON judge_eval(kind, prompt_sha);
"""


def ensure_schema(con: sqlite3.Connection) -> None:
    con.executescript(CREATE_JUDGE_EVAL_TABLE)
