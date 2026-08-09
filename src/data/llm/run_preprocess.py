from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.data.db import Database
from src.data.llm.clients import (
    OLLAMA_CLOUD_MAX_CONCURRENT,
    RateLimiter,
    env_key,
    load_dotenv,
)
from src.data.llm.utils import (
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_MODELS,
    DEFAULT_RPM,
    append_input,
    load_prompt,
)
from src.data.llm.utils import (
    parse_models as _parse_models,
)
from src.data.llm.utils import (
    try_models as _try_models,
)

DEFAULT_PROMPT_VERSION = "preprocess_process_v2_en"
DEFAULT_STAGE = "preprocess"

SYSTEM_PROMPT = load_prompt("preprocess_system.md")
USER_TEMPLATE = load_prompt("user.md")


def build_prompt(raw_text: str) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for a sample's raw text."""
    return SYSTEM_PROMPT, append_input(
        USER_TEMPLATE,
        raw_text,
        placeholder="{raw_text}",
        tag="input",
    )


def pending_samples(
    db: Database,
    *,
    stage: str,
    prompt_version: str,
    limit: int,
    source: str | None = None,
    split: str | None = None,
) -> list[dict]:
    """Return samples that need a generation attempt for a stage/prompt version.

    A retomada é filtrada por `prompt_version` além de `stage`: sem isso, trocar
    o prompt faria o runner pular tudo como "já concluído" e a regeração
    falharia em silêncio (ver spec 005, E4).
    """
    sql = """
        SELECT s.*
        FROM samples s
        WHERE s.raw_text IS NOT NULL
          AND length(trim(s.raw_text)) > 0
          AND (? IS NULL OR s.source = ?)
          AND (? IS NULL OR s.split = ?)
          AND (
              EXISTS (
                  SELECT 1
                  FROM preprocessing_generations g_retry
                  WHERE g_retry.sample_id = s.id
                    AND g_retry.stage = ?
                    AND g_retry.prompt_version = ?
                    AND g_retry.output_text IS NULL
              )
              OR NOT EXISTS (
                  SELECT 1
                  FROM preprocessing_generations g
                  WHERE g.sample_id = s.id
                    AND g.stage = ?
                    AND g.prompt_version = ?
                    AND g.status = 'succeeded'
              )
          )
        ORDER BY s.source, s.stage, s.id
        LIMIT ?
    """
    params = (source, source, split, split, stage, prompt_version, stage, prompt_version, limit)
    rows = db.query(sql, params)
    return [dict(row) for row in rows]


def _prune_duplicate_generations(db: Database, *, stage: str) -> int:
    """Keep only the latest non-failed generation per sample/stage/prompt version."""
    count_sql = """
        WITH duplicate_groups AS (
            SELECT sample_id, prompt_version
            FROM preprocessing_generations
            WHERE stage = ?
            GROUP BY sample_id, prompt_version
            HAVING count(*) > 1
        ),
        keep AS (
            SELECT sample_id, prompt_version, max(id) AS id
            FROM preprocessing_generations
            WHERE stage = ?
              AND status != 'failed'
              AND EXISTS (
                  SELECT 1
                  FROM duplicate_groups dg
                  WHERE dg.sample_id = preprocessing_generations.sample_id
                    AND dg.prompt_version IS preprocessing_generations.prompt_version
              )
            GROUP BY sample_id, prompt_version
        )
        SELECT count(*) AS n
        FROM preprocessing_generations pg
        WHERE pg.stage = ?
          AND EXISTS (
              SELECT 1
              FROM keep
              WHERE keep.sample_id = pg.sample_id
                AND keep.prompt_version IS pg.prompt_version
          )
          AND pg.id NOT IN (SELECT id FROM keep)
    """
    delete_sql = """
        WITH duplicate_groups AS (
            SELECT sample_id, prompt_version
            FROM preprocessing_generations
            WHERE stage = ?
            GROUP BY sample_id, prompt_version
            HAVING count(*) > 1
        ),
        keep AS (
            SELECT sample_id, prompt_version, max(id) AS id
            FROM preprocessing_generations
            WHERE stage = ?
              AND status != 'failed'
              AND EXISTS (
                  SELECT 1
                  FROM duplicate_groups dg
                  WHERE dg.sample_id = preprocessing_generations.sample_id
                    AND dg.prompt_version IS preprocessing_generations.prompt_version
              )
            GROUP BY sample_id, prompt_version
        )
        DELETE FROM preprocessing_generations
        WHERE stage = ?
          AND EXISTS (
              SELECT 1
              FROM keep
              WHERE keep.sample_id = preprocessing_generations.sample_id
                AND keep.prompt_version IS preprocessing_generations.prompt_version
          )
          AND id NOT IN (SELECT id FROM keep)
    """
    deleted = int(db.query(count_sql, (stage, stage, stage))[0]["n"])
    if deleted:
        db.execute(delete_sql, (stage, stage, stage))
    return deleted


def run_preprocessing(
    *,
    models: list[str],
    limit: int,
    rpm: int,
    max_workers: int,
    max_attempts: int,
    execute: bool,
    stage: str,
    prompt_version: str,
    source: str | None,
    split: str | None,
) -> int:
    load_dotenv()
    limiter = RateLimiter(rpm)
    api_key = env_key("OLLAMA_API_KEY") if execute else ""

    with Database() as db:
        rows = pending_samples(
            db,
            stage=stage,
            prompt_version=prompt_version,
            limit=limit,
            source=source,
            split=split,
        )
        if not rows:
            if execute:
                deleted = _prune_duplicate_generations(db, stage=stage)
                if deleted:
                    print(f"[cleanup] deleted {deleted} duplicate generation rows")
            print("[info] no pending samples")
            return 0

        contexts = [(row, *build_prompt(row["raw_text"])) for row in rows]

        if not execute:
            for row, system_prompt, user_prompt in contexts:
                print(
                    f"[dry-run] {row['id']} models={','.join(models)} "
                    f"system_chars={len(system_prompt)} user_chars={len(user_prompt)}"
                )
            return len(contexts)

        total = len(contexts)
        processed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_to_ctx = {
                pool.submit(
                    _try_models,
                    system_prompt,
                    user_prompt,
                    models,
                    api_key=api_key,
                    limiter=limiter,
                    think=False,
                    max_attempts=max_attempts,
                ): (row, user_prompt)
                for row, system_prompt, user_prompt in contexts
            }
            for future in as_completed(future_to_ctx):
                row, user_prompt = future_to_ctx[future]
                processed += 1
                prefix = f"[{processed}/{total}]"
                try:
                    result = future.result()
                except Exception as exc:  # safety net; _try_models swallows LLMError
                    gid = db.create_generation(
                        row["id"],
                        stage,
                        model=models[0],
                        prompt_version=prompt_version,
                        status="failed",
                        input_text=user_prompt,
                        error=str(exc),
                    )
                    print(f"{prefix} [error] {row['id']} generation_id={gid}: {exc}")
                    continue

                for attempt in result:
                    gid = db.create_generation(
                        row["id"],
                        stage,
                        model=attempt["model"],
                        prompt_version=prompt_version,
                        status=attempt["status"],
                        input_text=user_prompt,
                        output_text=attempt.get("output"),
                        error=attempt.get("error"),
                    )
                    tag = "ok" if attempt["status"] == "succeeded" else "failed"
                    detail = "" if attempt["status"] == "succeeded" else f": {attempt['error']}"
                    print(
                        f"{prefix} [{tag}] {row['id']} generation_id={gid} "
                        f"attempt={attempt['attempt']} model={attempt['model']}{detail}"
                    )

        deleted = _prune_duplicate_generations(db, stage=stage)
        if deleted:
            print(f"[cleanup] deleted {deleted} duplicate generation rows")

    return processed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        action="append",
        help=(
            "Ollama Cloud model id. Repeat or comma-separate for fallback chain. "
            f"Default: {','.join(DEFAULT_MODELS)}."
        ),
    )
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument(
        "--rpm",
        type=int,
        default=DEFAULT_RPM,
        help="Requests-per-minute floor across all workers (politeness throttle).",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=OLLAMA_CLOUD_MAX_CONCURRENT,
        help=(
            f"Max concurrent in-flight requests. "
            f"Default {OLLAMA_CLOUD_MAX_CONCURRENT} (Ollama Cloud cap)."
        ),
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=DEFAULT_MAX_ATTEMPTS,
        help=(
            f"Full passes over the model chain before giving up on a sample. "
            f"Default {DEFAULT_MAX_ATTEMPTS}. Exponential backoff between passes."
        ),
    )
    parser.add_argument("--stage", default=DEFAULT_STAGE)
    parser.add_argument("--prompt-version", default=DEFAULT_PROMPT_VERSION)
    parser.add_argument("--source", help="Filter samples by source.")
    parser.add_argument("--split", help="Filter samples by split, e.g. sft or grpo.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually call the provider. Without this flag, only prints selected rows.",
    )
    parser.add_argument(
        "--print-defaults",
        action="store_true",
        help="Print default model/rate choices as JSON and exit.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    defaults = {
        "models": DEFAULT_MODELS,
        "rpm": DEFAULT_RPM,
        "max_workers": OLLAMA_CLOUD_MAX_CONCURRENT,
        "max_attempts": DEFAULT_MAX_ATTEMPTS,
    }
    if args.print_defaults:
        print(json.dumps(defaults, indent=2, ensure_ascii=False))
        return

    models = _parse_models(args.model) or DEFAULT_MODELS
    run_preprocessing(
        models=models,
        limit=args.limit,
        rpm=args.rpm,
        max_workers=args.max_workers,
        max_attempts=args.max_attempts,
        execute=args.execute,
        stage=args.stage,
        prompt_version=args.prompt_version,
        source=args.source,
        split=args.split,
    )


if __name__ == "__main__":
    main()
