"""Inferência local do modelo pequeno — braços A3 e A4 (spec 003 §6.2).

Configuração **congelada** e idêntica nos dois braços: 4-bit NF4 com dupla
quantização, computação em `float16` e atenção `sdpa`. Não é preferência — é o
que a placa impõe: Turing (compute capability 7.5) precede o `bfloat16` nativo, e
o FlashAttention-2 corrente não contempla essa arquitetura. Quantização diferente
entre A3 e A4 faria o contraste medir precisão numérica junto com o efeito do
ajuste supervisionado.

**Decodificação gulosa** (`do_sample=False`). Diferente dos braços em nuvem, aqui
a repetição tende a ser determinística: o ADR 0003 vale para a API remota, não
para geração local com semente fixa. As k=3 execuções são mantidas assim mesmo,
porque a dispersão observada (esperada nula) é o contraste que sustenta a
alegação de reprodutibilidade do sistema proposto frente ao baseline.

Requer o extra `training`:

    uv sync --extra training
"""

from __future__ import annotations

from functools import lru_cache

MAX_NEW_TOKENS = 2048
SEED = 42
COMPUTE_DTYPE = "float16"  # Turing não tem bfloat16 nativo
ATTENTION = "sdpa"  # FlashAttention-2 não suporta sm_75


def _require():
    """Importa as dependências pesadas só quando alguém realmente gera.

    O módulo precisa ser importável sem elas: `run_benchmark --dry-run` e a
    suíte de testes não devem exigir 3 GB de torch para planejar um braço.
    """
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    except ImportError as exc:  # pragma: no cover - depende do extra `training`
        raise SystemExit(
            "inferência local requer o extra `training`. Rode: uv sync --extra training"
        ) from exc
    return torch, AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig


@lru_cache(maxsize=2)
def load(model_id: str, adapter: str | None = None):
    """Carrega tokenizador e modelo quantizado, uma vez por processo.

    O cache é essencial, não otimização prematura: carregar 7B em 4 bits leva
    cerca de um minuto, e um braço faz 159 gerações. Sem ele, o custo de carga
    dominaria o experimento inteiro.
    """
    torch, AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig = _require()

    quant = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=getattr(torch, COMPUTE_DTYPE),
    )
    tok = AutoTokenizer.from_pretrained(model_id)
    modelo = AutoModelForCausalLM.from_pretrained(
        model_id,
        quantization_config=quant,
        dtype=getattr(torch, COMPUTE_DTYPE),
        attn_implementation=ATTENTION,
        device_map={"": 0},
    )
    if adapter:
        try:
            from peft import PeftModel
        except ImportError as exc:  # pragma: no cover
            raise SystemExit("adapter LoRA requer `peft`: uv sync --extra training") from exc
        modelo = PeftModel.from_pretrained(modelo, adapter)
    modelo.eval()
    return tok, modelo


def build_inputs(tok, prompt: str):
    """Aplica o chat template do Qwen.

    O prompt inteiro vai como mensagem do usuário: os blocos `<role>` e
    `<modeling_rules>` fazem parte do artefato versionado e hasheado (AC-7), e
    reparti-los entre system e user aqui criaria divergência silenciosa entre o
    que foi hasheado e o que o modelo recebeu.
    """
    texto = tok.apply_chat_template(
        [{"role": "user", "content": prompt}],
        tokenize=False,
        add_generation_prompt=True,
    )
    return tok(texto, return_tensors="pt")


def generate_local(
    prompt: str,
    *,
    model_id: str,
    adapter: str | None = None,
    max_tokens: int = MAX_NEW_TOKENS,
    seed: int = SEED,
) -> tuple[str, bool]:
    """(texto, truncado). Gulosa e sem retry — falha é resultado medido (AC-6)."""
    torch, *_ = _require()
    tok, modelo = load(model_id, adapter)

    torch.manual_seed(seed)
    entradas = build_inputs(tok, prompt).to(modelo.device)
    n_entrada = entradas["input_ids"].shape[-1]

    with torch.inference_mode():
        saida = modelo.generate(
            **entradas,
            max_new_tokens=max_tokens,
            do_sample=False,
            temperature=None,
            top_p=None,
            top_k=None,
            pad_token_id=tok.pad_token_id or tok.eos_token_id,
        )

    novos = saida[0][n_entrada:]
    # Truncamento é atingir o teto sem emitir EOS. A spec §6.2 exige registrá-lo
    # por amostra e reportá-lo separado de erro de modelo.
    truncado = len(novos) >= max_tokens and novos[-1].item() != tok.eos_token_id
    return tok.decode(novos, skip_special_tokens=True).strip(), truncado


def vram_report() -> dict:
    """Diagnóstico de capacidade. Roda antes de um braço para não descobrir
    estouro de memória na amostra 120 de 159."""
    torch, *_ = _require()
    if not torch.cuda.is_available():
        return {"cuda": False}
    livre, total = torch.cuda.mem_get_info()
    return {
        "cuda": True,
        "gpu": torch.cuda.get_device_name(0),
        "capability": ".".join(map(str, torch.cuda.get_device_capability(0))),
        "total_gb": round(total / 1024**3, 2),
        "livre_gb": round(livre / 1024**3, 2),
        "alocado_gb": round(torch.cuda.memory_allocated() / 1024**3, 2),
    }
