from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TypeVar

from dotenv import load_dotenv

load_dotenv()

OLLAMA_CLOUD_URL = "https://ollama.com/api/chat"
OLLAMA_CLOUD_MAX_CONCURRENT = 3


class LLMError(RuntimeError):
    """Raised when an LLM provider returns an unusable response."""


def env_key(*names: str) -> str:
    """Return the first configured environment variable from a list of names."""
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    joined = " or ".join(names)
    raise LLMError(f"Missing API key: set {joined} in .env or environment")


class RateLimiter:
    """Thread-safe request-per-minute limiter."""

    def __init__(self, rpm: int):
        if rpm < 1:
            raise ValueError("rpm must be >= 1")
        self.interval = 60.0 / rpm
        self._last_call = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            elapsed = time.monotonic() - self._last_call
            if elapsed < self.interval:
                time.sleep(self.interval - elapsed)
            self._last_call = time.monotonic()


def generate_ollama_cloud(
    user_prompt: str,
    *,
    api_key: str,
    model: str,
    system_prompt: str | None = None,
    temperature: float = 0.1,
    timeout: int = 300,
    think: bool = False,
    num_predict: int = 32768,
) -> str:
    """Call Ollama Cloud chat API and return the message content.

    `think=False` disables reasoning-mode for thinking models (kimi, deepseek-r1, etc.).
    Reasoning eats the output token budget and leaves `message.content` empty when
    `done_reason="length"`; disabling it is both cheaper and avoids that failure mode
    for reformatting/structuring tasks.
    """
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "think": think,
        "options": {"temperature": temperature, "num_predict": num_predict},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = _post_json(OLLAMA_CLOUD_URL, payload, headers=headers, timeout=timeout)

    text = data.get("message", {}).get("content", "")
    if not text:
        done_reason = data.get("done_reason", "?")
        raise LLMError(f"Ollama Cloud returned no text (done_reason={done_reason}): {data}")
    return text.strip()


T = TypeVar("T")


def run_parallel(
    tasks: list[Callable[[], T]],
    *,
    max_workers: int = OLLAMA_CLOUD_MAX_CONCURRENT,
) -> list[T | Exception]:
    """Execute callable tasks with bounded concurrency.

    Returns results in input order. Exceptions raised by a task are captured
    and returned in place of the result, so the caller can inspect partial
    outcomes without one failure killing the batch.
    """
    if not tasks:
        return []

    results: list[T | Exception] = [None] * len(tasks)  # type: ignore[assignment]
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(task): idx for idx, task in enumerate(tasks)}
        for future in as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = future.result()
            except Exception as exc:
                results[idx] = exc
    return results


def _post_json(url: str, payload: dict, *, headers: dict[str, str], timeout: int) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise LLMError(f"HTTP {exc.code}: {error_body}") from exc
    except urllib.error.URLError as exc:
        raise LLMError(f"Network error: {exc.reason}") from exc
