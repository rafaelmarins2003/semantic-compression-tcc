from __future__ import annotations

import random
import time
from pathlib import Path

from src.data.manipulation.llm.clients import (
    LLMError,
    RateLimiter,
    generate_ollama_cloud,
)

DEFAULT_MODELS = ["kimi-k2.6:cloud", "deepseek-v4-pro:cloud"]
DEFAULT_RPM = 60
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_BASE = 2.0
ROOT_DIR = Path(__file__).resolve().parents[4]
PROMPTS_DIR = ROOT_DIR / "configs" / "prompts"


def load_prompt(name: str) -> str:
    """Load a prompt file from configs/prompts."""
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def append_input(template: str, input_text: str, *, placeholder: str, tag: str) -> str:
    """Fill a prompt template placeholder or append the input inside XML-like tags."""
    stripped = input_text.strip()
    if placeholder in template:
        return template.replace(placeholder, stripped)
    return f"{template}\n\n<{tag}>\n{stripped}\n</{tag}>"


def try_models(
    system_prompt: str,
    user_prompt: str,
    models: list[str],
    *,
    api_key: str,
    limiter: RateLimiter,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff_base: float = DEFAULT_BACKOFF_BASE,
) -> list[dict]:
    """Try the model chain up to `max_attempts` full passes.

    Each pass walks every model in `models`; the first success returns.
    Between passes, sleeps for exponential backoff with jitter to avoid
    hammering the provider on transient failures (timeouts, 5xx, 429).
    Returns one attempt dict per API call made.
    """
    attempts = []
    for attempt_idx in range(1, max_attempts + 1):
        for model in models:
            try:
                limiter.wait()
                output = generate_ollama_cloud(
                    user_prompt,
                    api_key=api_key,
                    model=model,
                    system_prompt=system_prompt,
                )
                attempts.append(
                    {
                        "attempt": attempt_idx,
                        "model": model,
                        "status": "succeeded",
                        "output": output,
                    }
                )
                return attempts
            except LLMError as exc:
                attempts.append(
                    {
                        "attempt": attempt_idx,
                        "model": model,
                        "status": "failed",
                        "error": str(exc),
                    }
                )
        if attempt_idx < max_attempts:
            sleep_for = backoff_base * (2 ** (attempt_idx - 1)) + random.uniform(0, 0.5)
            time.sleep(sleep_for)
    return attempts


def parse_models(values: list[str] | None) -> list[str]:
    """Parse repeated or comma-separated --model values."""
    if not values:
        return []

    models = []
    for value in values:
        models.extend(part.strip() for part in value.split(",") if part.strip())
    return models
