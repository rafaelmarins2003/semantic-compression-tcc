"""Import PMo dataset descriptions into data/dataset.db.

Each of the 55 .txt files in data/raw/pmo/descriptions/ is a process
description (one sentence per line). Some files start with "Title: <name>".

Inserted as source='pmo', stage='descriptions', split='holdout' — PMo is the
benchmark holdout and must not be used for training.

Usage:
    uv run python -m src.data.ingestion.dataset.import_pmo
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT_DIR = Path(__file__).resolve().parents[4]
_DESCRIPTIONS_DIR = _ROOT_DIR / "data" / "raw" / "pmo" / "descriptions"

# Source origin by file number (from PMo README)
_SOURCE_ORIGINS = {
    range(1, 21): "PMo Benchmark (Kourani et al., 2024)",
    range(21, 25): "BPMN for Research (Camunda, 2015)",
    range(25, 49): "Mangler et al. (2023)",
    range(49, 55): "PET-7 (Klievtsova et al., 2024)",
    range(55, 56): "CCC19 (Munoz-Gama et al., 2019)",
}

_TITLE_RE = re.compile(r"^Title:\s*(.+)$", re.IGNORECASE)


def _origin(n: int) -> str:
    for r, origin in _SOURCE_ORIGINS.items():
        if n in r:
            return origin
    return "unknown"


def load_description(path: Path) -> tuple[str, str]:
    """Parse a PMo description file. Returns (title, text).

    If the first line is 'Title: ...', it's extracted as title and
    the remaining lines form the text. Otherwise title is empty.
    """
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    if not lines:
        return "", ""

    title = ""
    if _TITLE_RE.match(lines[0]):
        title = _TITLE_RE.match(lines[0]).group(1).strip()
        lines = lines[1:]

    # Drop empty lines at the start after title
    while lines and not lines[0].strip():
        lines = lines[1:]

    text = " ".join(line.strip() for line in lines if line.strip())
    return title, text


def run() -> None:
    from src.data.db import Database

    if not _DESCRIPTIONS_DIR.exists():
        print(f"Directory not found: {_DESCRIPTIONS_DIR}")
        sys.exit(1)

    txt_files = sorted(_DESCRIPTIONS_DIR.glob("*.txt"))
    if not txt_files:
        print("No .txt files found")
        sys.exit(1)

    records = []
    for path in txt_files:
        n = int(path.stem)
        title, text = load_description(path)

        if not text:
            print(f"  Warning: empty text in {path.name}, skipping")
            continue

        records.append(
            {
                "id": f"pmo_{n:02d}",
                "split": "holdout",
                "title": title or f"Process {n:02d}",
                "raw_text": text,
                "metadata": {
                    "file": path.name,
                    "process_number": n,
                    "origin": _origin(n),
                    "sentence_count": text.count("."),
                },
            }
        )

    with Database() as db:
        n_inserted = db.insert("pmo", "descriptions", records, replace=True)
        print(f"Inserted {n_inserted}/{len(txt_files)} PMo descriptions")
        print()
        for s in db.sources():
            print(f"  {s['source']}__{s['stage']}: {s['n']} records")


if __name__ == "__main__":
    run()
