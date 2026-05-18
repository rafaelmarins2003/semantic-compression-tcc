from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.data.db import Database
from src.data.manipulation.llm.clients import (
    OLLAMA_CLOUD_MAX_CONCURRENT,
    RateLimiter,
    env_key,
    load_dotenv,
)
from src.data.manipulation.llm.utils import (
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_MODELS,
    DEFAULT_RPM,
    DEFAULT_TIMEOUT,
    append_input,
    load_prompt,
    parse_models,
    try_models,
)

DEFAULT_PROMPT_VERSION = "bpmn_json_generator_v1"
DEFAULT_STAGE = "json_bpmn"
DEFAULT_PREPROCESS_STAGE = "preprocess"
DEFAULT_THINK = True
DEFAULT_JSON_BPMN_TIMEOUT = 900
DEFAULT_ERROR_PREVIEW_CHARS = 4000
PROMPT_TEMPLATE = load_prompt("BPMN_JSON_generator.md")


def build_prompt(preprocess_text: str) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for preprocessed process text."""
    return "", append_input(
        PROMPT_TEMPLATE,
        preprocess_text,
        placeholder="{preprocess_text}",
        tag="input_preprocess",
    )


def pending_preprocess_outputs(
    db: Database,
    *,
    stage: str,
    preprocess_stage: str,
    prompt_version: str,
    limit: int,
    source: str | None = None,
    split: str | None = None,
) -> list[dict]:
    """Return samples whose latest successful preprocess output still needs JSON BPMN."""
    sql = """
        WITH latest_preprocess AS (
            SELECT pg.*
            FROM preprocessing_generations pg
            JOIN (
                SELECT sample_id, max(id) AS id
                FROM preprocessing_generations
                WHERE stage = ?
                  AND status = 'succeeded'
                  AND output_text IS NOT NULL
                  AND length(trim(output_text)) > 0
                GROUP BY sample_id
            ) latest ON latest.id = pg.id
        )
        SELECT s.*, latest_preprocess.output_text AS input_preprocess
        FROM samples s
        JOIN latest_preprocess ON latest_preprocess.sample_id = s.id
        WHERE (? IS NULL OR s.source = ?)
          AND (? IS NULL OR s.split = ?)
          AND (
              EXISTS (
                  SELECT 1
                  FROM json_bpmn_generations retry
                  WHERE retry.sample_id = s.id
                    AND retry.stage = ?
                    AND retry.prompt_version = ?
                    AND retry.output_json IS NULL
              )
              OR NOT EXISTS (
                  SELECT 1
                  FROM json_bpmn_generations done
                  WHERE done.sample_id = s.id
                    AND done.stage = ?
                    AND done.prompt_version = ?
                    AND done.status = 'succeeded'
              )
          )
        ORDER BY s.source, s.stage, s.id
        LIMIT ?
    """
    rows = db.query(
        sql,
        (
            preprocess_stage,
            source,
            source,
            split,
            split,
            stage,
            prompt_version,
            stage,
            prompt_version,
            limit,
        ),
    )
    return [dict(row) for row in rows]


def _extract_json_object(output: str) -> str:
    """Extract and normalize the first JSON object from a model response."""
    start = output.find("{")
    if start < 0:
        raise ValueError("response does not contain a JSON object")

    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(output[start:])
    return json.dumps(obj, ensure_ascii=False)


def _json_extraction_note(output: str) -> str:
    """Return a short diagnostic note about non-JSON text around the extracted object."""
    start = output.find("{")
    if start < 0:
        return "no_json"

    decoder = json.JSONDecoder()
    _, end = decoder.raw_decode(output[start:])
    before = output[:start].strip()
    after = output[start + end :].strip()
    if before and after:
        return "stripped_before_after"
    if before:
        return "stripped_before"
    if after:
        return "stripped_after"
    return "clean"


def _compact_preview(text: str, max_chars: int) -> str:
    """Return a compact preview preserving start/end of long model outputs."""
    compact = text.replace("\r", "\\r")
    if max_chars < 1 or len(compact) <= max_chars:
        return compact

    head_len = max_chars // 2
    tail_len = max_chars - head_len
    return (
        compact[:head_len]
        + f"\n...[truncated {len(compact) - max_chars} chars]...\n"
        + compact[-tail_len:]
    )


def _format_output_error(reason: str, output: str, *, max_chars: int) -> str:
    """Build a useful persisted error message for invalid model JSON output."""
    return (
        f"{reason}\n"
        f"output_chars={len(output)}\n"
        f"output_preview_chars={max_chars}\n"
        f"output_preview:\n{_compact_preview(output, max_chars)}"
    )


def _prune_duplicate_json_generations(db: Database, *, stage: str) -> int:
    """Keep only the latest non-failed JSON generation per sample/stage/prompt version."""
    count_sql = """
        WITH duplicate_groups AS (
            SELECT sample_id, prompt_version
            FROM json_bpmn_generations
            WHERE stage = ?
            GROUP BY sample_id, prompt_version
            HAVING count(*) > 1
        ),
        keep AS (
            SELECT sample_id, prompt_version, max(id) AS id
            FROM json_bpmn_generations
            WHERE stage = ?
              AND status != 'failed'
              AND EXISTS (
                  SELECT 1
                  FROM duplicate_groups dg
                  WHERE dg.sample_id = json_bpmn_generations.sample_id
                    AND dg.prompt_version IS json_bpmn_generations.prompt_version
              )
            GROUP BY sample_id, prompt_version
        )
        SELECT count(*) AS n
        FROM json_bpmn_generations jg
        WHERE jg.stage = ?
          AND EXISTS (
              SELECT 1
              FROM keep
              WHERE keep.sample_id = jg.sample_id
                AND keep.prompt_version IS jg.prompt_version
          )
          AND jg.id NOT IN (SELECT id FROM keep)
    """
    delete_sql = """
        WITH duplicate_groups AS (
            SELECT sample_id, prompt_version
            FROM json_bpmn_generations
            WHERE stage = ?
            GROUP BY sample_id, prompt_version
            HAVING count(*) > 1
        ),
        keep AS (
            SELECT sample_id, prompt_version, max(id) AS id
            FROM json_bpmn_generations
            WHERE stage = ?
              AND status != 'failed'
              AND EXISTS (
                  SELECT 1
                  FROM duplicate_groups dg
                  WHERE dg.sample_id = json_bpmn_generations.sample_id
                    AND dg.prompt_version IS json_bpmn_generations.prompt_version
              )
            GROUP BY sample_id, prompt_version
        )
        DELETE FROM json_bpmn_generations
        WHERE stage = ?
          AND EXISTS (
              SELECT 1
              FROM keep
              WHERE keep.sample_id = json_bpmn_generations.sample_id
                AND keep.prompt_version IS json_bpmn_generations.prompt_version
          )
          AND id NOT IN (SELECT id FROM keep)
    """
    deleted = int(db.query(count_sql, (stage, stage, stage))[0]["n"])
    if deleted:
        db.execute(delete_sql, (stage, stage, stage))
    return deleted


def run_json_bpmn_generation(
    *,
    models: list[str],
    limit: int,
    rpm: int,
    max_workers: int,
    max_attempts: int,
    execute: bool,
    stage: str,
    preprocess_stage: str,
    prompt_version: str,
    source: str | None,
    split: str | None,
    think: bool,
    timeout: int = DEFAULT_JSON_BPMN_TIMEOUT,
    error_preview_chars: int = DEFAULT_ERROR_PREVIEW_CHARS,
) -> int:
    load_dotenv()
    limiter = RateLimiter(rpm)
    api_key = env_key("OLLAMA_API_KEY") if execute else ""

    with Database() as db:
        rows = pending_preprocess_outputs(
            db,
            stage=stage,
            preprocess_stage=preprocess_stage,
            prompt_version=prompt_version,
            limit=limit,
            source=source,
            split=split,
        )
        if not rows:
            if execute:
                deleted = _prune_duplicate_json_generations(db, stage=stage)
                if deleted:
                    print(f"[cleanup] deleted {deleted} duplicate json generation rows")
            print("[info] no pending preprocess outputs")
            return 0

        contexts = [(row, *build_prompt(row["input_preprocess"])) for row in rows]

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
                    try_models,
                    system_prompt,
                    user_prompt,
                    models,
                    api_key=api_key,
                    limiter=limiter,
                    think=think,
                    timeout=timeout,
                    max_attempts=max_attempts,
                ): row
                for row, system_prompt, user_prompt in contexts
            }
            for future in as_completed(future_to_ctx):
                row = future_to_ctx[future]
                processed += 1
                prefix = f"[{processed}/{total}]"
                try:
                    result = future.result()
                except Exception as exc:
                    gid = db.create_json_bpmn_generation(
                        row["id"],
                        stage,
                        model=models[0],
                        prompt_version=prompt_version,
                        status="failed",
                        input_preprocess=row["input_preprocess"],
                        error=str(exc),
                    )
                    print(f"{prefix} [error] {row['id']} generation_id={gid}: {exc}")
                    continue

                for attempt in result:
                    status = attempt["status"]
                    output_json = None
                    error = attempt.get("error")
                    if status == "succeeded":
                        try:
                            output_json = _extract_json_object(attempt["output"])
                        except ValueError as exc:
                            status = "failed"
                            error = _format_output_error(
                                str(exc),
                                attempt["output"],
                                max_chars=error_preview_chars,
                            )

                    gid = db.create_json_bpmn_generation(
                        row["id"],
                        stage,
                        model=attempt["model"],
                        prompt_version=prompt_version,
                        status=status,
                        input_preprocess=row["input_preprocess"],
                        output_json=output_json,
                        error=error,
                    )
                    tag = "ok" if status == "succeeded" else "failed"
                    detail = "" if status == "succeeded" else f": {error}"
                    note = ""
                    if status == "succeeded":
                        note = f" json={_json_extraction_note(attempt['output'])}"
                    elif attempt.get("output"):
                        note = f" output_chars={len(attempt['output'])}"
                    print(
                        f"{prefix} [{tag}] {row['id']} generation_id={gid} "
                        f"attempt={attempt['attempt']} model={attempt['model']}"
                        f" think={think} timeout={timeout}{note}{detail}"
                    )

        deleted = _prune_duplicate_json_generations(db, stage=stage)
        if deleted:
            print(f"[cleanup] deleted {deleted} duplicate json generation rows")

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
    parser.add_argument("--preprocess-stage", default=DEFAULT_PREPROCESS_STAGE)
    parser.add_argument("--prompt-version", default=DEFAULT_PROMPT_VERSION)
    parser.add_argument("--source", help="Filter samples by source.")
    parser.add_argument("--split", help="Filter samples by split, e.g. sft or grpo.")
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_JSON_BPMN_TIMEOUT,
        help=(
            "Provider request timeout in seconds. "
            f"Default {DEFAULT_JSON_BPMN_TIMEOUT} for thinking JSON generation."
        ),
    )
    parser.add_argument(
        "--error-preview-chars",
        type=int,
        default=DEFAULT_ERROR_PREVIEW_CHARS,
        help=(
            "Number of raw model-output characters to persist in error when JSON "
            f"parsing fails. Default {DEFAULT_ERROR_PREVIEW_CHARS}."
        ),
    )
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
    thinking = parser.add_mutually_exclusive_group()
    thinking.add_argument(
        "--think",
        dest="think",
        action="store_true",
        default=DEFAULT_THINK,
        help="Enable Ollama thinking mode for supported models. Default for this script.",
    )
    thinking.add_argument(
        "--no-think",
        dest="think",
        action="store_false",
        help="Disable Ollama thinking mode for supported models.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    defaults = {
        "models": DEFAULT_MODELS,
        "rpm": DEFAULT_RPM,
        "max_workers": OLLAMA_CLOUD_MAX_CONCURRENT,
        "max_attempts": DEFAULT_MAX_ATTEMPTS,
        "stage": DEFAULT_STAGE,
        "preprocess_stage": DEFAULT_PREPROCESS_STAGE,
        "prompt_version": DEFAULT_PROMPT_VERSION,
        "think": DEFAULT_THINK,
        "timeout": DEFAULT_JSON_BPMN_TIMEOUT,
        "base_timeout": DEFAULT_TIMEOUT,
        "error_preview_chars": DEFAULT_ERROR_PREVIEW_CHARS,
    }
    if args.print_defaults:
        print(json.dumps(defaults, indent=2, ensure_ascii=False))
        return

    models = parse_models(args.model) or DEFAULT_MODELS
    run_json_bpmn_generation(
        models=models,
        limit=args.limit,
        rpm=args.rpm,
        max_workers=args.max_workers,
        max_attempts=args.max_attempts,
        execute=args.execute,
        stage=args.stage,
        preprocess_stage=args.preprocess_stage,
        prompt_version=args.prompt_version,
        source=args.source,
        split=args.split,
        think=args.think,
        timeout=args.timeout,
        error_preview_chars=args.error_preview_chars,
    )


if __name__ == "__main__":
    main()
