"""Import PET dataset into data/dataset.db.

The PET parquet file has one row per document. Each row contains a flat
list of tokens for the full document. Tokens are joined into a readable
text string (no space before punctuation).

Inserted as source='pet', stage='descriptions', split='sft'.

Usage:
    uv run python -m src.data.ingestion.import_pet
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT_DIR = Path(__file__).resolve().parents[3]
_PARQUET_GLOB = _ROOT_DIR / "data" / "raw" / "pet" / "data" / "*.parquet"
# Suppress space BEFORE these tokens: .,;:!? and closing brackets/punctuation
_ATTACH_RIGHT = re.compile(r"^[.,;:!?)\]}\-/]$")
# Suppress space AFTER these tokens: opening brackets and hyphens/slashes
_ATTACH_LEFT = re.compile(r"^[(\[{\-/]$")


def join_tokens(tokens: list[str]) -> str:
    """Join tokens into prose, suppressing spaces before/after punctuation."""
    if not tokens:
        return ""
    result = tokens[0]
    prev = tokens[0]
    for token in tokens[1:]:
        if _ATTACH_RIGHT.match(token) or _ATTACH_LEFT.match(prev):
            result += token
        else:
            result += " " + token
        prev = token
    return result


def run() -> None:
    import pyarrow.parquet as pq

    from src.data.db import Database

    parquet_files = sorted(_ROOT_DIR.glob(str(_PARQUET_GLOB.relative_to(_ROOT_DIR))))
    if not parquet_files:
        print(f"No parquet files found at {_PARQUET_GLOB}")
        sys.exit(1)

    rows: list[dict] = []
    for path in parquet_files:
        rows.extend(pq.read_table(str(path)).to_pylist())

    print(f"Loaded {len(rows)} rows from {len(parquet_files)} parquet file(s)")

    records = []
    for row in rows:
        doc_name = row["document name"]
        tokens = row["tokens"]
        text = join_tokens(tokens)

        if not text:
            print(f"  Warning: empty text for {doc_name}, skipping")
            continue

        records.append(
            {
                "id": f"pet_{doc_name.replace('.', '_')}",
                "split": "sft",
                "title": doc_name,
                "raw_text": text,
                "metadata": {
                    "document_name": doc_name,
                    "token_count": len(tokens),
                },
            }
        )

    with Database() as db:
        n = db.insert("pet", "descriptions", records, replace=True)
        print(f"Inserted {n}/{len(rows)} PET descriptions")
        print()
        for s in db.sources():
            print(f"  {s['source']}__{s['stage']}: {s['n']} records")


if __name__ == "__main__":
    run()
