"""Batch-run the deterministic DSL -> BPMN XML transpiler.

Reads succeeded rows from `dsl_transpiler_runs`, runs `src.transpiler.transpile()`,
checks that the generated XML is well-formed and has globally unique BPMN ids,
validates it against the BPMN 2.0 XSD (`xsd_ok`/`xsd_error`), and records the
outcome in `xml_transpiler_runs`.

This runner is intentionally audit-oriented: failures are stored with the input
DSL snapshot and traceback so the XML transpiler can be improved iteratively
without rerunning LLM or JSON -> DSL stages.

Examples:
    uv run python -m src.data.manipulation.deterministic.dsl_to_xml
    uv run python -m src.data.manipulation.deterministic.dsl_to_xml --limit 20
    uv run python -m src.data.manipulation.deterministic.dsl_to_xml --retry-failed
"""

from __future__ import annotations

import argparse
import signal
import traceback
import warnings
from collections import Counter

from lxml import etree

from src.data.db import Database
from src.data.migrations.create_xml_transpiler_runs import ensure_schema
from src.transpiler import transpile
from src.transpiler.xsd import validate_bpmn_xsd

DEFAULT_SOURCE_DSL_VERSION = "json_to_dsl_v6"
DEFAULT_XML_TRANSPILER_VERSION = "dsl_to_xml_v3"
DEFAULT_TIMEOUT_SECONDS = 30
ERROR_MESSAGE_MAX = 2000


class XmlTranspileTimeout(Exception):
    """Raised when transpile+XML validation exceeds the sample budget."""


def _alarm_handler(signum, frame):  # noqa: ARG001 (signal-required signature)
    raise XmlTranspileTimeout()


def ensure_xml_transpiler_runs_table(db: Database) -> None:
    """Create the XML transpiler audit table and ensure xsd columns exist."""
    ensure_schema(db._conn)
    db._conn.commit()


def pending_rows(
    db: Database,
    *,
    source_dsl_version: str,
    xml_transpiler_version: str,
    limit: int,
    retry_failed: bool,
) -> list[dict]:
    """Return DSL rows that still need an XML transpiler run."""
    ensure_xml_transpiler_runs_table(db)
    if retry_failed:
        skip_clause = """
            AND NOT EXISTS (
                SELECT 1 FROM xml_transpiler_runs xr
                WHERE xr.source_dsl_run_id = dr.id
                  AND xr.xml_transpiler_version = ?
                  AND xr.status = 'succeeded'
            )
        """
    else:
        skip_clause = """
            AND NOT EXISTS (
                SELECT 1 FROM xml_transpiler_runs xr
                WHERE xr.source_dsl_run_id = dr.id
                  AND xr.xml_transpiler_version = ?
            )
        """

    sql = f"""
        SELECT
            dr.id AS source_dsl_run_id,
            dr.sample_id,
            dr.source_generation_id,
            dr.transpiler_version AS source_dsl_version,
            dr.output_dsl
        FROM dsl_transpiler_runs dr
        WHERE dr.status = 'succeeded'
          AND dr.parse_ok = 1
          AND dr.output_dsl IS NOT NULL
          AND dr.transpiler_version = ?
          {skip_clause}
        ORDER BY dr.id
        LIMIT ?
    """
    rows = db.query(sql, (source_dsl_version, xml_transpiler_version, limit))
    return [dict(r) for r in rows]


def _truncate(text: str | None, limit: int = ERROR_MESSAGE_MAX) -> str | None:
    if text is None:
        return None
    if len(text) <= limit:
        return text
    return text[:limit] + f"... [truncated, full length {len(text)}]"


def _validate_xml(xml_text: str) -> None:
    """Validate well-formed XML and globally unique ids.

    BPMN XML references nodes by id, and XML Schema validation will also expect
    IDs to be unique. We check this now even before adding XSD validation.
    """
    root = etree.fromstring(xml_text.encode("utf-8"))
    ids = [el.get("id") for el in root.iter() if el.get("id")]
    duplicates = sorted({value for value in ids if ids.count(value) > 1})
    if duplicates:
        preview = ", ".join(duplicates[:10])
        raise ValueError(f"duplicate XML id(s): {preview}")


def run_one(input_dsl: str, *, timeout_seconds: int) -> dict:
    """Run DSL -> XML on one DSL string and capture success/failure details."""
    result: dict = {
        "status": None,
        "xml_ok": None,
        "xsd_ok": None,
        "xsd_error": None,
        "output_xml": None,
        "warnings": None,
        "error_stage": None,
        "error_type": None,
        "error_message": None,
        "error_traceback": None,
    }

    captured_warnings: list[str] = []
    previous_handler = signal.signal(signal.SIGALRM, _alarm_handler)
    signal.alarm(timeout_seconds)
    try:
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                xml_text = transpile(input_dsl)
                captured_warnings = [str(w.message) for w in caught]
        except XmlTranspileTimeout:
            result["status"] = "transpile_timeout"
            result["error_stage"] = "transpile"
            result["error_type"] = "XmlTranspileTimeout"
            result["error_message"] = _truncate(
                f"transpile() exceeded {timeout_seconds}s wall-clock budget"
            )
            return result
        except Exception as exc:
            result["status"] = "transpile_failed"
            result["error_stage"] = "transpile"
            result["error_type"] = type(exc).__name__
            result["error_message"] = _truncate(str(exc))
            result["error_traceback"] = _truncate(traceback.format_exc())
            return result

        result["output_xml"] = xml_text
        if captured_warnings:
            result["warnings"] = " | ".join(captured_warnings)

        try:
            _validate_xml(xml_text)
            result["status"] = "succeeded"
            result["xml_ok"] = 1
            xsd_errors = validate_bpmn_xsd(xml_text)
            result["xsd_ok"] = 0 if xsd_errors else 1
            if xsd_errors:
                result["xsd_error"] = _truncate(" | ".join(xsd_errors))
        except XmlTranspileTimeout:
            result["status"] = "transpile_timeout"
            result["error_stage"] = "xml_validate"
            result["error_type"] = "XmlTranspileTimeout"
            result["error_message"] = _truncate(
                f"XML validation exceeded {timeout_seconds}s wall-clock budget"
            )
        except Exception as exc:
            result["status"] = "xml_failed"
            result["xml_ok"] = 0
            result["error_stage"] = "xml_validate"
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
    source_generation_id: int | None,
    source_dsl_run_id: int,
    source_dsl_version: str,
    xml_transpiler_version: str,
    input_dsl: str,
    result: dict,
) -> int:
    ensure_xml_transpiler_runs_table(db)
    cur = db._conn.execute(
        """
        INSERT INTO xml_transpiler_runs
            (sample_id, source_generation_id, source_dsl_run_id,
             source_dsl_version, xml_transpiler_version, status, xml_ok, xsd_ok,
             input_dsl, output_xml, warnings,
             error_stage, error_type, error_message, error_traceback, xsd_error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sample_id,
            source_generation_id,
            source_dsl_run_id,
            source_dsl_version,
            xml_transpiler_version,
            result["status"],
            result["xml_ok"],
            result["xsd_ok"],
            input_dsl,
            result["output_xml"],
            result["warnings"],
            result["error_stage"],
            result["error_type"],
            result["error_message"],
            result["error_traceback"],
            result["xsd_error"],
        ),
    )
    db._conn.commit()
    return int(cur.lastrowid)


def run_batch(
    *,
    source_dsl_version: str,
    xml_transpiler_version: str,
    limit: int,
    retry_failed: bool,
    quiet: bool,
    timeout_seconds: int,
) -> dict:
    summary = {
        "succeeded": 0,
        "transpile_failed": 0,
        "xml_failed": 0,
        "transpile_timeout": 0,
        "xsd_ok": 0,
        "xsd_failed": 0,
        "error_types": Counter(),
    }

    with Database() as db:
        rows = pending_rows(
            db,
            source_dsl_version=source_dsl_version,
            xml_transpiler_version=xml_transpiler_version,
            limit=limit,
            retry_failed=retry_failed,
        )
        total = len(rows)
        if total == 0:
            print(
                "[info] no pending rows for "
                f"source_dsl_version={source_dsl_version!r}, "
                f"xml_transpiler_version={xml_transpiler_version!r} "
                f"(retry_failed={retry_failed})"
            )
            return summary

        print(
            f"[info] processing {total} row(s) at "
            f"source_dsl_version={source_dsl_version!r}, "
            f"xml_transpiler_version={xml_transpiler_version!r} "
            f"(timeout={timeout_seconds}s/sample)"
        )

        for idx, row in enumerate(rows, start=1):
            result = run_one(row["output_dsl"], timeout_seconds=timeout_seconds)
            insert_run(
                db,
                sample_id=row["sample_id"],
                source_generation_id=row["source_generation_id"],
                source_dsl_run_id=row["source_dsl_run_id"],
                source_dsl_version=row["source_dsl_version"],
                xml_transpiler_version=xml_transpiler_version,
                input_dsl=row["output_dsl"],
                result=result,
            )
            summary[result["status"]] += 1
            if result["xsd_ok"] == 1:
                summary["xsd_ok"] += 1
            elif result["xsd_ok"] == 0:
                summary["xsd_failed"] += 1
            if result["error_type"]:
                summary["error_types"][result["error_type"]] += 1

            if not quiet or result["status"] != "succeeded":
                tag = result["status"]
                extra = ""
                if result["status"] != "succeeded":
                    extra = f" [{result['error_type']}] {result['error_message']!s:.180}"
                print(f"[{idx}/{total}] {tag} sample={row['sample_id']}{extra}")

    return summary


def print_summary(summary: dict, xml_transpiler_version: str) -> None:
    print()
    print("=" * 60)
    print(f"Summary (xml_transpiler_version={xml_transpiler_version})")
    print("=" * 60)
    total = (
        summary["succeeded"]
        + summary["transpile_failed"]
        + summary["xml_failed"]
        + summary["transpile_timeout"]
    )
    if total == 0:
        return
    print(f"  succeeded          {summary['succeeded']:5} ({summary['succeeded']/total:.1%})")
    print(f"  transpile_failed   {summary['transpile_failed']:5}")
    print(f"  xml_failed         {summary['xml_failed']:5}")
    print(f"  transpile_timeout  {summary['transpile_timeout']:5}")
    print(f"  xsd_ok             {summary['xsd_ok']:5}")
    print(f"  xsd_failed         {summary['xsd_failed']:5}")
    if summary["error_types"]:
        print()
        print("  Error types (this run):")
        for err_type, n in summary["error_types"].most_common():
            print(f"    [{n:4}] {err_type}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--source-dsl-version",
        default=DEFAULT_SOURCE_DSL_VERSION,
        help=f"DSL source version to read (default {DEFAULT_SOURCE_DSL_VERSION}).",
    )
    p.add_argument(
        "--xml-transpiler-version",
        default=DEFAULT_XML_TRANSPILER_VERSION,
        help=f"Tag for this XML batch (default {DEFAULT_XML_TRANSPILER_VERSION}).",
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
        help="Re-process rows that have only failed XML runs at this version.",
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
            f"Per-sample wall-clock budget in seconds (default {DEFAULT_TIMEOUT_SECONDS})."
        ),
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    summary = run_batch(
        source_dsl_version=args.source_dsl_version,
        xml_transpiler_version=args.xml_transpiler_version,
        limit=args.limit,
        retry_failed=args.retry_failed,
        quiet=args.quiet,
        timeout_seconds=args.timeout,
    )
    print_summary(summary, args.xml_transpiler_version)


if __name__ == "__main__":
    main()
