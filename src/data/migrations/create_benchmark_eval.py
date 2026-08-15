"""Migration: cria a tabela `benchmark_eval` (spec 003 §5, §11).

Uma linha por (braço, amostra, repetição). Com k=3 e 53 itens, cada braço rende
159 linhas; a unidade de análise é a **mediana por item** (§6.3), calculada na
leitura e não gravada — gravar a mediana esconderia a dispersão entre execuções,
que o ADR 0003 exige reportar.

Colunas em três blocos, refletindo as duas fases do harness:

  proveniência  preenchida sempre; é o AC-7 (`arm`, `model_id`, `prompt_sha256`,
                `spec_commit`) e o que liga qualquer número da tese a este spec.
  geração       preenchida pela fase de rede, cara e não determinística.
  pontuação     preenchida pela fase determinística, recalculável sem rede.

A separação existe para que o AC-3 seja satisfazível: reexecutar a pontuação
sobre saídas já gravadas produz linhas idênticas, o que **não** valeria se ela
dependesse de gerar de novo — ver ADR 0003 (temperatura 0 não é determinística).

`NULL` em `df_f1` significa "ainda não pontuado"; falha de geração ou de parse é
gravada como **0.0**, nunca NULL — o AC-2 exige linha com zero, jamais ausência.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[3] / "data" / "dataset.db"

CREATE_BENCHMARK_EVAL_TABLE = """
CREATE TABLE IF NOT EXISTS benchmark_eval (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    arm            TEXT    NOT NULL,
    sample_id      TEXT    NOT NULL,
    rep            INTEGER NOT NULL,

    -- proveniência (AC-7)
    model_id       TEXT    NOT NULL,
    prompt_name    TEXT    NOT NULL,
    prompt_sha256  TEXT    NOT NULL,
    spec_commit    TEXT    NOT NULL,

    -- geração
    raw_output     TEXT,
    output_xml     TEXT,
    truncated      INTEGER NOT NULL DEFAULT 0,
    gen_error      TEXT,
    latency_ms     INTEGER,

    -- transpilação (só nos braços que emitem DSL)
    parse_ok       INTEGER,
    parse_error    TEXT,

    -- pontuação
    xsd_valid      INTEGER,
    -- primária: rótulos alinhados (spec 003 §3.2a)
    df_precision   REAL,
    df_recall      REAL,
    df_f1          REAL,
    df_exact       INTEGER,
    -- secundária: igualdade textual de rótulo, mede estrutura E redação
    df_strict_precision REAL,
    df_strict_recall    REAL,
    df_strict_f1        REAL,
    df_strict_exact     INTEGER,
    nodes_match    INTEGER,
    mf_precision   REAL,
    mf_recall      REAL,
    mf_f1          REAL,
    ref_variant    TEXT,
    n_refs         INTEGER,
    scored_at      TEXT,

    created_at     TEXT DEFAULT (datetime('now')),

    UNIQUE(arm, sample_id, rep),
    FOREIGN KEY(sample_id) REFERENCES samples(id)
);

CREATE INDEX IF NOT EXISTS idx_benchmark_eval_arm ON benchmark_eval(arm);
CREATE INDEX IF NOT EXISTS idx_benchmark_eval_sample ON benchmark_eval(sample_id);
"""


def ensure_schema(con: sqlite3.Connection) -> None:
    con.executescript(CREATE_BENCHMARK_EVAL_TABLE)


def run(path: Path = DB_PATH, *, recreate: bool = False) -> None:
    con = sqlite3.connect(path)
    try:
        if recreate:
            con.execute("DROP TABLE IF EXISTS benchmark_eval")
        ensure_schema(con)
        con.commit()
        count = con.execute("SELECT count(*) FROM benchmark_eval").fetchone()[0]
        print({"table": "benchmark_eval", "rows": count, "recreated": recreate})
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--recreate", action="store_true")
    return p.parse_args()


if __name__ == "__main__":
    run(recreate=parse_args().recreate)
