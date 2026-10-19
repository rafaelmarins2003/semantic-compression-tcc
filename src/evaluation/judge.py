"""Juiz de fidelidade (P1): nota de 0 a 5 de quão bem um modelo BPMN representa o texto.

A rubrica (`configs/prompts/judge/`) segue o critério das notas de especialista do
Zenodo (Mangler et al., 2023): tarefas e decisões do texto presentes, paralelismo
identificado e modelo bem formado. Assim o juiz pode ser validado contra essas notas
antes de pontuar os braços (T5). O juiz vê o modelo pelo `render` neutro, nunca o XML,
para não saber de que braço ele veio.

A nota é a pontuação primária; as listas de problemas existem para auditoria.
"""

from __future__ import annotations

import hashlib
import json

from src.data.llm.clients import LLMError, generate_meta
from src.data.llm.utils import load_prompt
from src.evaluation.render import render

JUDGE_MODEL = "muse-spark-1.3-contributor"
SYSTEM_PROMPT = "judge/fidelity_system.md"
USER_PROMPT = "judge/fidelity_user.md"
# Inteiros, um por âncora da rubrica. A tentativa 1 usava passos de 0,5 como enum
# de decimais, e o juiz respondeu quase só x,5 (434 de 666 notas em 2,5): a escala
# virou 5 degraus deslocados, e não 11. Ver registro-tecnico, 2026-10-19.
SCORES = list(range(6))
CRITERIA = ["tasks", "decisions", "parallelism", "order_and_flow", "well_formedness"]

# Problemas antes da nota: o juiz justifica primeiro e pontua depois.
SCHEMA = {
    "type": "object",
    "properties": {
        "problems": {
            "type": "object",
            "properties": {c: {"type": "array", "items": {"type": "string"}} for c in CRITERIA},
            "required": CRITERIA,
            "additionalProperties": False,
        },
        "score": {"type": "integer", "enum": SCORES},
    },
    "required": ["problems", "score"],
    "additionalProperties": False,
}


def prompt_sha() -> str:
    """Hash dos dois prompts. Congelado antes da nota."""
    texto = load_prompt(SYSTEM_PROMPT) + "\n" + load_prompt(USER_PROMPT)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def build_user_prompt(description: str, xml_text: str) -> str:
    # replace, não format: descrições podem conter chaves.
    return (
        load_prompt(USER_PROMPT)
        .replace("{description}", description.strip())
        .replace("{model}", render(xml_text))
    )


def parse_verdict(text: str) -> dict:
    """Valida a resposta do juiz; falha alto em vez de aceitar nota fora da escala."""
    try:
        verdict = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError(f"judge returned invalid JSON: {text[:200]}") from exc
    if verdict.get("score") not in SCORES:
        raise LLMError(f"judge score out of scale: {verdict.get('score')!r}")
    if set(verdict.get("problems", {})) != set(CRITERIA):
        raise LLMError(f"judge problems missing criteria: {verdict.get('problems')!r}")
    return verdict


def judge(description: str, xml_text: str, *, api_key: str, seed: int | None = None) -> dict:
    """Nota do juiz para um modelo; inclui uso de tokens e o hash do prompt."""
    text, meta = generate_meta(
        build_user_prompt(description, xml_text),
        api_key=api_key,
        model=JUDGE_MODEL,
        system_prompt=load_prompt(SYSTEM_PROMPT),
        json_schema=SCHEMA,
        seed=seed,
    )
    verdict = parse_verdict(text)
    return {**verdict, **meta, "prompt_sha": prompt_sha()}
