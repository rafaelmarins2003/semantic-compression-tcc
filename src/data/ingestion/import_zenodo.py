"""Import Zenodo BPMN dataset descriptions into data/dataset.db.

The 24 .txt files in data/raw/zenodo/bpmn/ are the original (unprocessed)
Mangler et al. (2023) process descriptions. Each file may start with
"Category: ..." and "Title: ..." metadata lines, followed by prose text.

Note: these overlap with PMo pairs 25-48 (same source, different preprocessing).
Zenodo versions are the raw originals; PMo versions are sentence-split and cleaned.
Because of that overlap, zenodo must stay out of training: with PMo as the
evaluation holdout, zenodo in SFT would contaminate 24 of PMo's 55 items.

Inserted as source='zenodo', stage='descriptions', split='holdout'.

Usage:
    uv run python -m src.data.ingestion.import_zenodo
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT_DIR = Path(__file__).resolve().parents[3]
_BPMN_DIR = _ROOT_DIR / "data" / "raw" / "zenodo" / "bpmn"
_CATEGORY_RE = re.compile(r"^Category:\s*(.+)$", re.IGNORECASE)
_TITLE_RE = re.compile(r"^Title:\s*(.+)$", re.IGNORECASE)


def load_description(path: Path) -> tuple[str, str, str]:
    """Parse a Zenodo description file. Returns (category, title, text).

    Strips Category/Title header lines; joins remaining lines into prose.
    """
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    category, title = "", ""

    # Extract optional Category and Title from the top
    while lines:
        m_cat = _CATEGORY_RE.match(lines[0])
        m_title = _TITLE_RE.match(lines[0])
        if m_cat:
            category = m_cat.group(1).strip()
            lines = lines[1:]
        elif m_title:
            title = m_title.group(1).strip()
            lines = lines[1:]
        elif not lines[0].strip():
            lines = lines[1:]
        else:
            break

    text = " ".join(line.strip() for line in lines if line.strip())
    return category, title, text


def run() -> None:
    from src.data.db import Database

    txt_files = sorted(_BPMN_DIR.glob("*.txt"))
    if not txt_files:
        print(f"No .txt files found in {_BPMN_DIR}")
        sys.exit(1)

    records = []
    for path in txt_files:
        category, title, text = load_description(path)

        if not text:
            print(f"  Warning: empty text in {path.name}, skipping")
            continue

        records.append(
            {
                "id": f"zenodo_{path.stem}",
                "split": "holdout",
                "title": title or path.stem,
                "raw_text": text,
                "metadata": {
                    "file": path.name,
                    "category": category,
                    "original_id": path.stem,
                },
            }
        )

    with Database() as db:
        n = db.insert("zenodo", "descriptions", records, replace=True)
        print(f"Inserted {n}/{len(txt_files)} Zenodo descriptions")
        print()
        for s in db.sources():
            print(f"  {s['source']}__{s['stage']}: {s['n']} records")


if __name__ == "__main__":
    run()
