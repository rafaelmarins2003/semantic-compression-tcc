"""Fidelidade dos braços: alvos sem vazados, agregação por item e contraste pareado."""

import json

import pytest

from src.data.db import LEAKED_HOLDOUT, Database
from src.data.migrations.create_benchmark_eval import ensure_schema as bench_schema
from src.data.migrations.create_judge_eval import ensure_schema as judge_schema
from src.evaluation.run_fidelity import contrast, describe, load
from src.evaluation.run_judge import benchmark_targets


@pytest.fixture
def banco(tmp_path):
    db = Database(tmp_path / "t.db")
    bench_schema(db._conn)
    judge_schema(db._conn)
    for sid in ("pmo_01", "pmo_49"):
        db._conn.execute(
            "INSERT INTO samples (id, source, stage, split, raw_text, metadata)"
            " VALUES (?, 'pmo', 'descriptions', 'holdout', 'Do A.', ?)",
            (sid, json.dumps({"origin": "x"})),
        )
    for i, (arm, sid, valido) in enumerate(
        [("A1", "pmo_01", 1), ("A1", "pmo_01", 0), ("A1", "pmo_49", 1), ("A4", "pmo_01", 1)]
    ):
        db._conn.execute(
            "INSERT INTO benchmark_eval (arm, sample_id, rep, model_id, prompt_name,"
            " prompt_sha256, spec_commit, output_xml, xsd_valid)"
            " VALUES (?, ?, ?, 'm', 'p', 's', 'c', '<x/>', ?)",
            (arm, sid, i, valido),
        )
    db._conn.commit()
    yield db
    db.close()


def test_targets_are_valid_outputs_outside_leaked_items(banco):
    alvos = benchmark_targets(banco, ["A1", "A4"])
    assert {(a["arm"], a["sample_id"]) for a in alvos} == {("A1", "pmo_01"), ("A4", "pmo_01")}
    assert "pmo_49" in LEAKED_HOLDOUT


def test_item_score_is_mean_of_output_medians(banco):
    for target, arm, notas in [("bench:1", "A1", [2, 3, 3]), ("bench:9", "A1", [5, 5, 4])]:
        for rep, nota in enumerate(notas):
            banco._conn.execute(
                "INSERT INTO judge_eval (target, kind, sample_id, arm, rep, model_id,"
                " prompt_sha, score, problems) VALUES (?, 'benchmark', 'pmo_01', ?, ?, 'm',"
                " 'sha', ?, '{}')",
                (target, arm, rep, nota),
            )
    assert load(banco, "sha") == {"A1": {"pmo_01": 4.0}}


def test_contrast_is_paired_on_common_items():
    a = {"pmo_01": 4.0, "pmo_02": 3.0, "pmo_03": 5.0}
    b = {"pmo_01": 3.0, "pmo_02": 3.0}
    r = contrast(a, b, {"pmo_01", "pmo_02", "pmo_03"})
    assert r["itens_pareados"] == 2 and r["dif_media"] == 0.5
    assert describe(a, {"pmo_01", "pmo_09"})["itens_cobertos"] == "1/2"
