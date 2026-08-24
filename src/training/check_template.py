"""Pré-voo de um modelo base candidato — só o tokenizador, sem GPU e sem pesos.

Existe para que a integração de um segundo modelo base falhe **aqui**, de graça,
e não no pod alugado. Checa as duas coisas que quebram em silêncio ao trocar de
família:

1. **Invariante de prefixo exato.** `montar()` aborta se o `chat_template` do
   modelo não produzir o prompt como prefixo em *tokens* do exemplo completo —
   é a condição de que a máscara de perda esteja alinhada.

2. **Fidelidade de ida-e-volta.** `decode(encode(t)) == t`. Parece redundante e
   não é: o DeepSeek-Coder sob `transformers` 5.5 carrega como `LlamaTokenizer`
   e **descarta todos os espaços na codificação** — `start "Collect relevant
   information"` vira `start"Collectrelevantinformation"`. A DSL resultante
   ainda parseia e ainda gera XML válido, mas nenhum rótulo casa com a
   referência, e a fidelidade topológica zera em 100% dos itens.

   Esta checagem existe porque a versão anterior deste script **não a fazia** e
   deixou passar exatamente esse defeito: verificava só a invariante de prefixo
   em ids, que continua satisfeita quando prompt e alvo são igualmente
   destruídos. Custou um treino e uma avaliação inteira. Verificar a invariante
   errada é pior que não verificar, porque produz confiança.

3. **Taxa de descarte acima de `--seq`.** Tokenizadores diferentes segmentam a
   DSL de modo diferente. Se um candidato descartar muito mais exemplos que o
   Qwen, os dois braços treinam sobre corpora de tamanhos distintos e a
   replicação deixa de ser comparável — confunde efeito de modelo com efeito de
   dados.

    uv run --with transformers python -m src.training.check_template
    uv run --with transformers python -m src.training.check_template --modelos <id> ...
"""

from __future__ import annotations

import argparse
import statistics
from pathlib import Path

from src.training.train_sft import BASE, SEQ, carregar, montar

CANDIDATOS = (
    BASE,  # referência: o braço A4 já treinado
    "deepseek-ai/deepseek-coder-6.7b-instruct",
    "ibm-granite/granite-8b-code-instruct-4k",
    "mistralai/Mistral-7B-Instruct-v0.3",
)


def avaliar(nome: str, exemplos: list[dict], seq: int) -> dict:
    from transformers import AutoTokenizer

    try:
        tok = AutoTokenizer.from_pretrained(nome, trust_remote_code=False)
    except Exception as erro:  # rede, licença aceita, repo inexistente
        return {"modelo": nome, "erro": f"{type(erro).__name__}: {str(erro)[:120]}"}

    # Ida-e-volta antes de qualquer outra coisa: um tokenizador que não devolve o
    # texto que recebeu invalida treino e avaliação de uma vez só.
    sonda = exemplos[0]["completion"] if exemplos else 'task "A b c"'
    ida = tok(sonda, add_special_tokens=False)["input_ids"]
    if tok.decode(ida, skip_special_tokens=True) != sonda:
        return {"modelo": nome, "erro": "round-trip QUEBRA — decode(encode(t)) != t"}

    try:
        usados = montar(tok, exemplos, seq)
    except SystemExit as erro:
        return {"modelo": nome, "erro": f"template divergente — {erro}"}
    except Exception as erro:
        return {"modelo": nome, "erro": f"{type(erro).__name__}: {str(erro)[:120]}"}

    comprimentos = sorted(len(x["input_ids"]) for x in usados)
    return {
        "modelo": nome,
        "vocab": len(tok),
        "usados": len(usados),
        "descartados": len(exemplos) - len(usados),
        "mediana": statistics.median(comprimentos),
        "p90": comprimentos[int(0.9 * len(comprimentos))],
        "max": comprimentos[-1],
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dados", default="experiments/sft")
    p.add_argument("--seq", type=int, default=SEQ)
    p.add_argument("--modelos", nargs="+", default=list(CANDIDATOS))
    args = p.parse_args()

    exemplos = carregar(Path(args.dados) / "train.jsonl")
    print(f"{len(exemplos)} exemplos de treino, seq={args.seq}\n")

    linhas = [avaliar(m, exemplos, args.seq) for m in args.modelos]

    print(f"\n{'modelo':45} {'vocab':>7} {'usados':>7} {'descart':>8} {'mediana':>8} {'p90':>6}")
    for r in linhas:
        if "erro" in r:
            print(f"{r['modelo'][:45]:45} {'FALHOU':>7}  {r['erro']}")
        else:
            print(
                f"{r['modelo'][:45]:45} {r['vocab']:7d} {r['usados']:7d} "
                f"{r['descartados']:8d} {r['mediana']:8.0f} {r['p90']:6d}"
            )


if __name__ == "__main__":
    main()
