"""Ajuste supervisionado do Qwen2.5-Coder-7B-Instruct com QLoRA — braço A4.

Quatro decisões que este script existe para garantir, e que erram em silêncio se
não forem explícitas:

1. **Formato idêntico ao da inferência.** O texto de treino é construído pelo
   mesmo `apply_chat_template` que `src.evaluation.local_model.build_inputs` usa,
   e o script *verifica* que o prompt é prefixo exato do exemplo completo. Sem
   isso o A4 infere fora da distribuição em que treinou.

2. **Perda só na completação.** Os tokens do prompt recebem rótulo -100. Treinar
   sobre o prompt gastaria capacidade reproduzindo um texto fixo de 756 tokens,
   idêntico em todos os 690 exemplos.

3. **`seq 4096`, medido e não convencionado.** Com 1024 — valor usual para este
   porte — 98% dos exemplos truncariam, e o corte cai no fim, isto é, no alvo. O
   sintoma seria queda de validade sintática atribuída por engano ao método.

4. **Parada por validação agrupada.** Com corpus pequeno a perda de treino não
   serve de critério; o split vem de `export_dataset.py`, agrupado por documento.

Exemplos:
    uv run python -m src.training.train_sft --smoke      # 20 passos, valida setup
    uv run python -m src.training.train_sft
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

BASE = "Qwen/Qwen2.5-Coder-7B-Instruct"
DADOS = "experiments/sft"
SAIDA = "experiments/sft/adapter"
SEQ = 4096
SEED = 42


def carregar(caminho: Path) -> list[dict]:
    with caminho.open(encoding="utf-8") as f:
        return [json.loads(linha) for linha in f if linha.strip()]


def montar(tok, exemplos: list[dict], seq: int) -> list[dict]:
    """Tokeniza mascarando o prompt. Falha alto se o template divergir.

    O prompt precisa ser prefixo em *tokens*, não só em texto: se a fronteira
    entre prompt e completação cair no meio de um token, a máscara desalinha e o
    modelo treina sobre pedaço do prompt sem que nada acuse.
    """
    saida, truncados, divergentes = [], 0, 0
    for e in exemplos:
        conversa = [{"role": "user", "content": e["prompt"]}]
        texto_prompt = tok.apply_chat_template(
            conversa, tokenize=False, add_generation_prompt=True
        )
        texto_full = tok.apply_chat_template(
            [*conversa, {"role": "assistant", "content": e["completion"]}], tokenize=False
        )
        if not texto_full.startswith(texto_prompt):
            divergentes += 1
            continue

        ids_prompt = tok(texto_prompt, add_special_tokens=False)["input_ids"]
        ids_full = tok(texto_full, add_special_tokens=False)["input_ids"]
        if ids_full[: len(ids_prompt)] != ids_prompt:
            divergentes += 1
            continue

        if len(ids_full) > seq:
            truncados += 1
            continue  # descartar, não truncar: alvo cortado ensina DSL inválida

        rotulos = [-100] * len(ids_prompt) + ids_full[len(ids_prompt) :]
        saida.append({"input_ids": ids_full, "labels": rotulos})

    if divergentes:
        raise SystemExit(f"{divergentes} exemplos com template divergente — abortando")
    print(f"  exemplos usados {len(saida)}  descartados por exceder {seq} tokens: {truncados}")
    return saida


def colar(lote: list[dict], pad_id: int) -> dict:
    """Padding dinâmico à direita; rótulo de padding é -100."""
    import torch

    largura = max(len(x["input_ids"]) for x in lote)
    return {
        "input_ids": torch.tensor(
            [x["input_ids"] + [pad_id] * (largura - len(x["input_ids"])) for x in lote]
        ),
        "labels": torch.tensor(
            [x["labels"] + [-100] * (largura - len(x["labels"])) for x in lote]
        ),
        "attention_mask": torch.tensor(
            [[1] * len(x["input_ids"]) + [0] * (largura - len(x["input_ids"])) for x in lote]
        ),
    }


def construir_modelo(base: str, args):
    import torch
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig

    # bf16 onde existe (Ampere+); Turing só tem fp16. Reportado no log para que a
    # execução na nuvem e a local sejam distinguíveis nos resultados.
    bf16 = torch.cuda.is_available() and torch.cuda.get_device_capability(0)[0] >= 8
    dtype = torch.bfloat16 if bf16 else torch.float16
    print(f"  compute dtype {dtype} | bf16={bf16} | attn={'fa2' if bf16 else 'sdpa'}")

    modelo = AutoModelForCausalLM.from_pretrained(
        base,
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=dtype,
        ),
        attn_implementation="sdpa",
        device_map={"": 0},
    )
    modelo = prepare_model_for_kbit_training(modelo, use_gradient_checkpointing=True)
    modelo.config.use_cache = False
    lora = LoraConfig(
        r=args.rank,
        lora_alpha=args.alpha,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules="all-linear",
    )
    modelo = get_peft_model(modelo, lora)
    modelo.print_trainable_parameters()
    return modelo, bf16


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", default=BASE)
    p.add_argument("--dados", default=DADOS)
    p.add_argument("--saida", default=SAIDA)
    p.add_argument("--seq", type=int, default=SEQ)
    p.add_argument("--epocas", type=float, default=3.0)
    p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--rank", type=int, default=16)
    p.add_argument("--alpha", type=int, default=32)
    p.add_argument("--batch", type=int, default=1)
    p.add_argument("--acumulo", type=int, default=8)
    p.add_argument("--smoke", action="store_true", help="20 passos — valida memória e formato")
    args = p.parse_args()

    try:
        import torch
        from transformers import AutoTokenizer, Trainer, TrainingArguments, set_seed
    except ImportError as exc:
        raise SystemExit("requer o extra `training`: uv sync --extra training") from exc

    set_seed(SEED)
    tok = AutoTokenizer.from_pretrained(args.base)
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token

    raiz = Path(args.dados)
    print("treino:")
    treino = montar(tok, carregar(raiz / "train.jsonl"), args.seq)
    print("validação:")
    val = montar(tok, carregar(raiz / "val.jsonl"), args.seq)

    modelo, bf16 = construir_modelo(args.base, args)

    passos_epoca = max(1, len(treino) // (args.batch * args.acumulo))
    ta = TrainingArguments(
        output_dir=args.saida,
        num_train_epochs=args.epocas,
        max_steps=20 if args.smoke else -1,
        per_device_train_batch_size=args.batch,
        per_device_eval_batch_size=args.batch,
        gradient_accumulation_steps=args.acumulo,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        optim="paged_adamw_8bit",
        max_grad_norm=1.0,
        bf16=bf16,
        fp16=not bf16,
        logging_steps=10,
        eval_strategy="no" if args.smoke else "epoch",
        save_strategy="no" if args.smoke else "epoch",
        save_total_limit=2,
        load_best_model_at_end=not args.smoke,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        report_to=[],
        seed=SEED,
        data_seed=SEED,
    )
    print(f"  ~{passos_epoca} passos por época | batch efetivo {args.batch * args.acumulo}")

    treinador = Trainer(
        model=modelo,
        args=ta,
        train_dataset=treino,
        eval_dataset=None if args.smoke else val,
        data_collator=lambda lote: colar(lote, tok.pad_token_id),
    )
    treinador.train()

    if args.smoke:
        pico = torch.cuda.max_memory_allocated() / 1024**3 if torch.cuda.is_available() else 0
        print(f"\nSMOKE OK — pico de VRAM {pico:.2f} GiB. Rode sem --smoke para treinar.")
        return

    modelo.save_pretrained(args.saida)
    tok.save_pretrained(args.saida)
    (Path(args.saida) / "treino.json").write_text(
        json.dumps(
            {
                "base": args.base,
                "seq": args.seq,
                "epocas": args.epocas,
                "lr": args.lr,
                "rank": args.rank,
                "alpha": args.alpha,
                "batch_efetivo": args.batch * args.acumulo,
                "n_treino": len(treino),
                "n_val": len(val),
                "seed": SEED,
                "historico": treinador.state.log_history[-8:],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nadapter salvo em {args.saida}")


if __name__ == "__main__":
    main()
