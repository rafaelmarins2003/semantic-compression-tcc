"""Batch-run the deterministic JSON → DSL transpiler over every succeeded LLM JSON.

Reads from `json_bpmn_generations` (status='succeeded'), runs
`json_to_dsl.convert()` followed by `dsl.parser.parse()`, and records the
outcome (success / convert_failed / parse_failed) in `dsl_transpiler_runs`.

Iterate by re-running with the same --transpiler-version after fixing the
transpiler: only rows without a prior `succeeded` run for that version are
re-tried. Bump --transpiler-version to force a full re-run across the dataset.

Examples:
    uv run python -m src.data.deterministic.run_json_to_dsl
    uv run python -m src.data.deterministic.run_json_to_dsl --limit 20
    uv run python -m src.data.deterministic.run_json_to_dsl --retry-failed
    uv run python -m src.data.deterministic.run_json_to_dsl \\
        --transpiler-version json_to_dsl_v2
"""

from __future__ import annotations

import argparse
import json
import signal
import traceback
import warnings
from collections import Counter

from src.data.db import Database
from src.data.deterministic import json_to_dsl
from src.data.llm.run_generate_json import DEFAULT_PROMPT_VERSION as JSON_PROMPT_VERSION
from src.dsl.parser import parse as dsl_parse

DEFAULT_TRANSPILER_VERSION = "json_to_dsl_v10_en"
DEFAULT_TIMEOUT_SECONDS = 30
ERROR_MESSAGE_MAX = 2000


class TranspileTimeout(Exception):
    """Raised when convert+parse exceeds the per-sample wall-clock budget."""


def _alarm_handler(signum, frame):  # noqa: ARG001 (signal-required signature)
    raise TranspileTimeout()


def pending_rows(
    db: Database,
    *,
    transpiler_version: str,
    limit: int,
    retry_failed: bool,
    prompt_version: str | None = None,
) -> list[dict]:
    """Return json_bpmn_generations rows that still need a transpiler run.

    Pending means: no `succeeded` run exists for this transpiler_version.
    If `retry_failed=False` (default), rows with ANY prior run for this version
    are skipped — so re-running picks up only never-seen rows.
    If `retry_failed=True`, rows with only failed runs for this version are
    re-tried (so you can iterate after fixing the transpiler without bumping
    the version).

    `prompt_version` delimita a geração do corpus. Sem ele, uma tag nova
    reprocessaria também as gerações antigas — misturando corpora de idiomas
    diferentes sob o mesmo rótulo (ver ADR 0001).
    """
    if retry_failed:
        skip_clause = """
            AND NOT EXISTS (
                SELECT 1 FROM dsl_transpiler_runs r
                WHERE r.source_generation_id = g.id
                  AND r.transpiler_version = ?
                  AND r.status = 'succeeded'
            )
        """
    else:
        skip_clause = """
            AND NOT EXISTS (
                SELECT 1 FROM dsl_transpiler_runs r
                WHERE r.source_generation_id = g.id
                  AND r.transpiler_version = ?
            )
        """

    sql = f"""
        SELECT g.id AS source_generation_id, g.sample_id, g.output_json
        FROM json_bpmn_generations g
        WHERE g.status = 'succeeded'
          AND g.output_json IS NOT NULL
          AND (? IS NULL OR g.prompt_version = ?)
          {skip_clause}
        ORDER BY g.id
        LIMIT ?
    """
    rows = db.query(sql, (prompt_version, prompt_version, transpiler_version, limit))
    return [dict(r) for r in rows]


def _truncate(text: str | None, limit: int = ERROR_MESSAGE_MAX) -> str | None:
    if text is None:
        return None
    if len(text) <= limit:
        return text
    return text[:limit] + f"... [truncated, full length {len(text)}]"


def run_one(output_json_text: str, *, timeout_seconds: int) -> dict:
    """Run convert + parse on one JSON string, capturing all outcomes.

    Returns a dict ready to be inserted into dsl_transpiler_runs.
    Pure function — does no I/O beyond the work itself.

    `timeout_seconds` arms a SIGALRM so a pathological input cannot stall
    the whole batch. Unix-only (SIGALRM does not exist on Windows).
    """
    result: dict = {
        "status": None,
        "parse_ok": None,
        "output_dsl": None,
        "warnings": None,
        "error_stage": None,
        "error_type": None,
        "error_message": None,
        "error_traceback": None,
    }

    try:
        data = json.loads(output_json_text)
    except Exception as exc:
        result["status"] = "convert_failed"
        result["error_stage"] = "convert"
        result["error_type"] = type(exc).__name__
        result["error_message"] = _truncate(f"input JSON not parseable: {exc}")
        result["error_traceback"] = _truncate(traceback.format_exc())
        return result

    captured_warnings: list[str] = []
    previous_handler = signal.signal(signal.SIGALRM, _alarm_handler)
    signal.alarm(timeout_seconds)
    try:
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                dsl_text = json_to_dsl.convert(data)
                captured_warnings = [str(w.message) for w in caught]
        except TranspileTimeout:
            result["status"] = "convert_timeout"
            result["error_stage"] = "convert"
            result["error_type"] = "TranspileTimeout"
            result["error_message"] = _truncate(
                f"convert() exceeded {timeout_seconds}s wall-clock budget"
            )
            return result
        except Exception as exc:
            result["status"] = "convert_failed"
            result["error_stage"] = "convert"
            result["error_type"] = type(exc).__name__
            result["error_message"] = _truncate(str(exc))
            result["error_traceback"] = _truncate(traceback.format_exc())
            return result

        result["output_dsl"] = dsl_text
        if captured_warnings:
            result["warnings"] = " | ".join(captured_warnings)

        try:
            dsl_parse(dsl_text)
            result["status"] = "succeeded"
            result["parse_ok"] = 1
        except TranspileTimeout:
            result["status"] = "convert_timeout"
            result["error_stage"] = "parse"
            result["error_type"] = "TranspileTimeout"
            result["error_message"] = _truncate(
                f"parse() exceeded {timeout_seconds}s wall-clock budget"
            )
        except Exception as exc:
            result["status"] = "parse_failed"
            result["parse_ok"] = 0
            result["error_stage"] = "parse"
            result["error_type"] = type(exc).__name__
            result["error_message"] = _truncate(str(exc))
            result["error_traceback"] = _truncate(traceback.format_exc())
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)

    return result


def insert_run(
    db: Database,
    *,
    sample_id: str,
    source_generation_id: int,
    transpiler_version: str,
    input_json: str,
    result: dict,
) -> int:
    cur = db._conn.execute(
        """
        INSERT INTO dsl_transpiler_runs
            (sample_id, source_generation_id, transpiler_version, status, parse_ok,
             input_json, output_dsl, warnings,
             error_stage, error_type, error_message, error_traceback)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sample_id,
            source_generation_id,
            transpiler_version,
            result["status"],
            result["parse_ok"],
            input_json,
            result["output_dsl"],
            result["warnings"],
            result["error_stage"],
            result["error_type"],
            result["error_message"],
            result["error_traceback"],
        ),
    )
    db._conn.commit()
    return int(cur.lastrowid)


def run_batch(
    *,
    transpiler_version: str,
    limit: int,
    retry_failed: bool,
    quiet: bool,
    timeout_seconds: int,
    prompt_version: str | None = None,
) -> dict:
    summary = {
        "succeeded": 0,
        "convert_failed": 0,
        "parse_failed": 0,
        "convert_timeout": 0,
        "error_types": Counter(),
    }

    with Database() as db:
        rows = pending_rows(
            db,
            transpiler_version=transpiler_version,
            limit=limit,
            retry_failed=retry_failed,
            prompt_version=prompt_version,
        )
        total = len(rows)
        if total == 0:
            print(
                "[info] no pending rows for transpiler_version="
                f"{transpiler_version!r} (retry_failed={retry_failed})"
            )
            return summary

        print(
            f"[info] processing {total} row(s) at transpiler_version={transpiler_version!r} "
            f"(timeout={timeout_seconds}s/sample)"
        )

        for idx, row in enumerate(rows, start=1):
            result = run_one(row["output_json"], timeout_seconds=timeout_seconds)
            insert_run(
                db,
                sample_id=row["sample_id"],
                source_generation_id=row["source_generation_id"],
                transpiler_version=transpiler_version,
                input_json=row["output_json"],
                result=result,
            )
            summary[result["status"]] += 1
            if result["error_type"]:
                summary["error_types"][result["error_type"]] += 1

            if not quiet or result["status"] != "succeeded":
                tag = result["status"]
                extra = ""
                if result["status"] != "succeeded":
                    extra = f" [{result['error_type']}] {result['error_message']!s:.180}"
                print(f"[{idx}/{total}] {tag} sample={row['sample_id']}{extra}")

    return summary


def print_summary(summary: dict, transpiler_version: str) -> None:
    print()
    print("=" * 60)
    print(f"Summary (transpiler_version={transpiler_version})")
    print("=" * 60)
    total = (
        summary["succeeded"]
        + summary["convert_failed"]
        + summary["parse_failed"]
        + summary["convert_timeout"]
    )
    if total == 0:
        return
    print(f"  succeeded         {summary['succeeded']:5} ({summary['succeeded'] / total:.1%})")
    print(f"  convert_failed    {summary['convert_failed']:5}")
    print(f"  parse_failed      {summary['parse_failed']:5}")
    print(f"  convert_timeout   {summary['convert_timeout']:5}")
    if summary["error_types"]:
        print()
        print("  Error types (this run):")
        for err_type, n in summary["error_types"].most_common():
            print(f"    [{n:4}] {err_type}")
    print()
    print("Inspect grouped errors across the whole table:")
    print(
        '  uv run python -c "from src.data.db import Database; db=Database(); '
        "print(db.query('SELECT status, error_type, count(*) n FROM dsl_transpiler_runs "
        f'WHERE transpiler_version=\\"{transpiler_version}\\" '
        "GROUP BY status, error_type ORDER BY n DESC')[:])\""
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--transpiler-version",
        default=DEFAULT_TRANSPILER_VERSION,
        help=f"Tag for this batch (default {DEFAULT_TRANSPILER_VERSION}). "
        "Bump to force a full re-run across all samples.",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=10_000,
        help="Max number of rows to process. Default 10000 (covers full dataset).",
    )
    p.add_argument(
        "--retry-failed",
        action="store_true",
        help="Re-process rows that have only failed runs at this version. "
        "Default behaviour skips any row that already has any run at this version.",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Print per-row line only for failures (default prints all).",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=(
            f"Per-sample wall-clock budget in seconds (default {DEFAULT_TIMEOUT_SECONDS}). "
            "Stalled samples are marked convert_timeout and the batch continues."
        ),
    )
    p.add_argument(
        "--prompt-version",
        default=JSON_PROMPT_VERSION,
        help=(
            f"Só converte gerações desta prompt_version (default {JSON_PROMPT_VERSION}). "
            "Use --all-prompt-versions para desligar o filtro — sem ele, uma tag nova "
            "reprocessa corpora antigos e mistura idiomas (ADR 0001)."
        ),
    )
    p.add_argument(
        "--all-prompt-versions",
        action="store_true",
        help="Desliga o filtro de prompt_version. Só para inspeção do histórico.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    summary = run_batch(
        transpiler_version=args.transpiler_version,
        limit=args.limit,
        retry_failed=args.retry_failed,
        quiet=args.quiet,
        timeout_seconds=args.timeout,
        prompt_version=None if args.all_prompt_versions else args.prompt_version,
    )
    print_summary(summary, args.transpiler_version)


if __name__ == "__main__":
    main()
