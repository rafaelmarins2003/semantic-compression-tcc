"""Leitura dos logs de treino para a curva de aprendizado."""

from src.evaluation import export_contrastes


def test_treino_reads_train_pairs_and_best_eval_loss(tmp_path, monkeypatch):
    (tmp_path / "sft_x.log").write_text(
        "  exemplos usados 167  descartados por exceder 4096 tokens: 6\n"
        "  exemplos usados 78  descartados por exceder 4096 tokens: 0\n"
        "{'eval_loss': '0.5731', 'epoch': 1}\n{'eval_loss': '0.4945', 'epoch': 3}\n"
        "{'eval_loss': 0.5015, 'epoch': 2}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(export_contrastes, "LOGS", tmp_path)
    assert export_contrastes._treino("sft_x") == (167, 0.4945)
