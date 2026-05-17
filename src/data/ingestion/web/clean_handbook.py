"""Clean GitLab Handbook markdown and segment into process-rich sections.

Reads filtered_paths.json (from scrape_gitlab_handbook filter),
cleans each markdown file, segments by H2/H3 headers, curates for
procedural quality, and writes seeds directly to data/dataset.db.

Usage:
    # Run full pipeline (clean → curate → split → db insert)
    uv run python -m src.data.ingestion.web.clean_handbook

    # Or run steps individually:
    uv run python -m src.data.ingestion.web.clean_handbook clean [--min-score 40] [--min-words 100]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────

_ROOT_DIR = Path(__file__).resolve().parents[4]
_DATA_DIR = _ROOT_DIR / "data" / "raw" / "gitlab-handbook"
_FILTERED_FILE = _DATA_DIR / "filtered_paths.json"
_MD_DIR = _DATA_DIR / "md"


# ── Cleaning functions (applied in order) ──────────────────────────────────────


def strip_frontmatter(text: str) -> tuple[str, str]:
    """Remove YAML frontmatter, return (title, cleaned_text)."""
    m = re.match(r"^---\n(.*?)\n---\n?", text, re.DOTALL)
    if not m:
        return "", text
    fm = m.group(1)
    title = ""
    tm = re.search(r'title:\s*["\']?(.+?)["\']?\s*$', fm, re.MULTILINE)
    if tm:
        title = tm.group(1).strip().strip("\"'")
    return title, text[m.end() :]


def strip_hugo_shortcodes(text: str) -> str:
    """Remove Hugo shortcodes: {{< >}} inline and {{% %}} block pairs."""
    text = re.sub(r"\{\{%\s*/?\s*\w[\w\s\"'=./-]*%\}\}", "", text)
    text = re.sub(r"\{\{<\s*[\w/][\w\s\"'=./-]*>\}\}", "", text)
    return text


def strip_html(text: str) -> str:
    """Remove HTML tags, comments, and style attributes."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"</?[a-zA-Z][^>]*>", "", text)
    text = re.sub(r"\{[^}]*\}", "", text)
    return text


def strip_images(text: str) -> str:
    """Remove markdown image embeds ![alt](url)."""
    return re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)


def strip_code_blocks(text: str) -> str:
    """Remove fenced code blocks (```...```)."""
    return re.sub(r"```[\w]*\n.*?\n```", "", text, flags=re.DOTALL)


def clean_links(text: str) -> str:
    """Convert [text](url) → text, keeping link text."""
    return re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)


def clean_tables(text: str) -> str:
    """Convert simple markdown tables (2-3 cols) to lists; remove wider ones."""
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^\s*\|", line) and "|" in line[1:]:
            table_lines = []
            while i < len(lines) and re.match(r"^\s*\|", lines[i]):
                table_lines.append(lines[i])
                i += 1
            _convert_table(table_lines, out)
        else:
            out.append(line)
            i += 1
    return "\n".join(out)


def _convert_table(table_lines: list[str], out: list[str]) -> None:
    """Convert a markdown table to list items or discard if too wide."""
    rows: list[list[str]] = []
    for line in table_lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if all(re.match(r"^[-:]+$", c) for c in cells):
            continue
        rows.append(cells)

    if not rows:
        return

    ncols = len(rows[0])
    if ncols > 3:
        return

    header = rows[0] if rows else []
    for row in rows[1:]:
        if ncols == 2 and len(row) >= 2:
            out.append(f"- {header[0]}: {row[0]} — {row[1]}")
        elif ncols == 3 and len(row) >= 3:
            out.append(f"- {row[0]}: {row[1]} — {row[2]}")
        else:
            out.append(f"- {' | '.join(row)}")


def strip_emphasis(text: str) -> str:
    """Remove markdown emphasis: ***bold italic***, **bold**, *italic*."""
    text = re.sub(r"\*{3}(.+?)\*{3}", r"\1", text)
    text = re.sub(r"\*{2}(.+?)\*{2}", r"\1", text)
    text = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"\1", text)
    return text


def strip_slack_refs(text: str) -> str:
    """Remove Slack channel refs, @mentions, and email addresses."""
    text = re.sub(r"`?[\w.-]+@[\w.-]+\.\w+`?", "", text)
    text = re.sub(r"(?<=\s)#[\w-]+(?=[\s,.\)])", "", text)
    text = re.sub(r"(?<=\s)@[\w.-]+", "", text)
    return text


def normalize_whitespace(text: str) -> str:
    """Collapse 3+ newlines to 2, strip trailing whitespace per line."""
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── Full cleaning pipeline ─────────────────────────────────────────────────────


def clean_markdown(text: str) -> tuple[str, str]:
    """Apply all cleaning steps. Returns (title, cleaned_text)."""
    title, text = strip_frontmatter(text)
    text = strip_code_blocks(text)
    text = strip_hugo_shortcodes(text)
    text = strip_html(text)
    text = strip_images(text)
    text = clean_links(text)
    text = clean_tables(text)
    text = strip_emphasis(text)
    text = strip_slack_refs(text)
    text = normalize_whitespace(text)
    return title, text


# ── Segmentation ───────────────────────────────────────────────────────────────

_HEADER_RE = re.compile(r"^(#{2,3})\s+(.+)$", re.MULTILINE)


def _slugify(text: str) -> str:
    """Convert text to a simple slug for IDs."""
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[\s-]+", "_", slug.strip())
    return slug[:60]


def segment_sections(title: str, text: str, min_words: int = 100) -> list[dict]:
    """Split cleaned text by H2/H3 headers into sections.

    Returns list of dicts with keys: section_title, text, words.
    Sections shorter than min_words are merged into the previous section.
    """
    splits = _HEADER_RE.split(text)
    sections: list[dict] = []
    intro = splits[0].strip()

    if len(intro.split()) >= min_words:
        sections.append(
            {
                "section_title": title or "Introduction",
                "text": intro,
                "words": len(intro.split()),
            }
        )

    i = 1
    while i + 2 <= len(splits):
        # splits[i] is the header level ("##" or "###"), not needed
        sec_title = splits[i + 1].strip()
        content = splits[i + 2].strip() if i + 2 < len(splits) else ""
        i += 3

        words = len(content.split())
        if words < min_words:
            if sections:
                prev = sections[-1]
                prev["text"] += f"\n\n{sec_title}\n\n{content}"
                prev["words"] = len(prev["text"].split())
            continue

        sections.append({"section_title": sec_title, "text": content, "words": words})

    return sections


# ── Curation — section-level procedural quality scoring ────────────────────────

_PROC_KW = re.compile(
    r"\b(steps?|procedure|workflow|process|runbook|playbook|handoff|handover"
    r"|onboarding|offboarding|lifecycle|pipeline)\b",
    re.I,
)
_ACTION_VERBS = re.compile(
    r"\b(open|create|submit|review|approve|assign|notify|validate|escalate"
    r"|click|navigate|select|ensure|verify|complete|request|send|receive"
    r"|confirm|update|check|schedule|initiate|close|resolve|forward"
    r"|upload|download|configure|provision|revoke|terminate|cancel)\b",
    re.I,
)
_ACTORS = re.compile(
    r"\b(user|manager|team\s+member|owner|requester|reviewer|engineer"
    r"|analyst|coordinator|specialist|approver|admin|lead|director"
    r"|stakeholder|DRI|on-call)\b",
    re.I,
)
_CONDITIONALS = re.compile(
    r"\b(if\s+the|if\s+a|if\s+you|when\s+the|when\s+a|unless|otherwise"
    r"|depending\s+on|in\s+case|in\s+the\s+event)\b",
    re.I,
)
_NUMBERED_STEPS = re.compile(r"^\s*\d+\.\s+", re.MULTILINE)
_LEGAL_TITLE = re.compile(
    r"\b(CONFIDENTIALITY|LIMITATION\s+OF\s+LIABILITY|INDEMNIFI\w*|INTELLECTUAL\s+PROPERTY"
    r"|FORCE\s+MAJEURE|MISCELLANEOUS|U\.?S\.?\s+GOVERNMENT|GOVERNING\s+LAW"
    r"|DISPUTE\s+RESOLUTION|SEVERABILITY|ENTIRE\s+AGREEMENT|WAIVER"
    r"|REPRESENTATIONS?\s+AND\s+WARRANTIES|DEFINITIONS?\b|APPENDIX)\b",
    re.I,
)


def score_procedural(text: str, title: str) -> int:
    """Score a section's procedural richness (0-10+).

    Higher = more likely to describe an actionable process.
    Negative penalties for legal boilerplate.
    """
    score = 0
    score += min(len(_PROC_KW.findall(text)), 2)

    verb_hits = len(_ACTION_VERBS.findall(text))
    if verb_hits >= 8:
        score += 3
    elif verb_hits >= 5:
        score += 2
    elif verb_hits >= 3:
        score += 1

    score += min(len(_ACTORS.findall(text)), 2)

    if _CONDITIONALS.search(text):
        score += 1

    step_hits = len(_NUMBERED_STEPS.findall(text))
    if step_hits >= 3:
        score += 2
    elif step_hits >= 1:
        score += 1

    if _LEGAL_TITLE.search(title):
        score -= 5

    return score


# ── BPMN-convertibility classification ────────────────────────────────────────

_MULTI_ACTOR = re.compile(
    r"\b(manager|team\s+member|engineer|reviewer|approver|analyst"
    r"|coordinator|specialist|lead|director|admin|stakeholder|DRI|on-call)\b",
    re.I,
)


def classify_bpmn(text: str) -> str:
    """Classify a section's BPMN-convertibility.

    Returns: 'ideal', 'good', 'linear', or 'marginal'.
    - ideal:    3+ numbered steps AND decisions AND 2+ distinct actors
    - good:     3+ numbered steps AND (decisions OR 2+ actors)
    - linear:   3+ numbered steps only
    - marginal: fewer than 3 numbered steps
    """
    has_steps = len(_NUMBERED_STEPS.findall(text)) >= 3
    has_dec = bool(_CONDITIONALS.search(text))
    actors = set(a.lower() for a in _MULTI_ACTOR.findall(text))
    has_multi_actor = len(actors) >= 2

    if not has_steps:
        return "marginal"
    if has_dec and has_multi_actor:
        return "ideal"
    if has_dec or has_multi_actor:
        return "good"
    return "linear"


# ── Pipeline ───────────────────────────────────────────────────────────────────


def run(min_score: int = 40, min_words: int = 100, min_proc_score: int = 4) -> None:
    """Full pipeline: clean → curate → classify → insert into database.

    Reads raw markdown from data/raw/gitlab-handbook/md/,
    writes seeds directly to data/dataset.db.
    """
    import json
    from collections import Counter

    from src.data.db import Database

    if not _FILTERED_FILE.exists():
        print("Run 'scrape_gitlab_handbook filter' first")
        sys.exit(1)

    entries = json.loads(_FILTERED_FILE.read_text(encoding="utf-8"))
    entries = [e for e in entries if e["score"] >= min_score]
    print(f"Processing {len(entries)} pages (min_score={min_score})...")

    all_sections: list[dict] = []

    for entry in entries:
        md_path = _MD_DIR / entry["path"]
        if not md_path.exists():
            continue

        raw = md_path.read_text(encoding="utf-8")
        title, cleaned = clean_markdown(raw)
        sections = segment_sections(title, cleaned, min_words=min_words)

        source_slug = _slugify(str(Path(entry["path"]).with_suffix("")))
        for j, sec in enumerate(sections):
            sec_slug = _slugify(sec["section_title"])
            base_id = f"{source_slug}__{sec_slug}" if sec_slug else f"{source_slug}__{j}"
            all_sections.append(
                {
                    "id": f"{base_id}_{j}",
                    "source_file": entry["path"],
                    "title": sec["section_title"],
                    "text": sec["text"],
                    "words": sec["words"],
                    "page_score": entry["score"],
                }
            )

    print(f"Segmented: {len(all_sections)} sections")

    # Curate
    curated = []
    score_dist: Counter = Counter()
    for sec in all_sections:
        ps = score_procedural(sec["text"], sec["title"])
        bucket = (
            "8+"
            if ps >= 8
            else ("6-7" if ps >= 6 else ("4-5" if ps >= 4 else ("2-3" if ps >= 2 else "0-1")))
        )
        score_dist[bucket] += 1
        if ps >= min_proc_score:
            sec["proc_score"] = ps
            curated.append(sec)

    print(f"Curated: {len(curated)}/{len(all_sections)} sections (min_proc_score={min_proc_score})")
    print("Proc score distribution:", dict(score_dist))

    # Classify and split
    counts: Counter = Counter()
    records = []
    for sec in curated:
        bpmn_class = classify_bpmn(sec["text"])
        counts[bpmn_class] += 1
        if bpmn_class == "marginal":
            continue

        split = "sft" if bpmn_class in ("ideal", "good") else "grpo"
        records.append(
            {
                "id": sec["id"],
                "split": split,
                "title": sec["title"],
                "raw_text": sec["text"],
                "metadata": {
                    "source_file": sec["source_file"],
                    "page_score": sec["page_score"],
                    "proc_score": sec["proc_score"],
                    "bpmn_class": bpmn_class,
                    "words": sec["words"],
                },
            }
        )

    print(f"Classification: {dict(counts)}")
    n_sft = sum(1 for r in records if r["split"] == "sft")
    n_grpo = sum(1 for r in records if r["split"] == "grpo")
    print(f"  sft: {n_sft}, grpo: {n_grpo}")

    # Write to database
    with Database() as db:
        n = db.insert("gitlab_handbook", "curated", records, replace=True)
        print(f"\nInserted {n} records into gitlab_handbook__curated")
        for s in db.sources():
            print(f"  {s['source']}__{s['stage']}: {s['n']} records")


def main():
    args = sys.argv[1:]
    if not args:
        run()
        return

    cmd = args[0]
    opts = args[1:]

    if cmd == "clean":
        min_score, min_words, min_proc_score = 40, 100, 4
        i = 0
        while i < len(opts):
            if opts[i] == "--min-score" and i + 1 < len(opts):
                min_score = int(opts[i + 1])
                i += 2
            elif opts[i] == "--min-words" and i + 1 < len(opts):
                min_words = int(opts[i + 1])
                i += 2
            elif opts[i] == "--min-proc-score" and i + 1 < len(opts):
                min_proc_score = int(opts[i + 1])
                i += 2
            else:
                print(f"Unknown arg: {opts[i]}")
                sys.exit(1)
        run(min_score=min_score, min_words=min_words, min_proc_score=min_proc_score)
    else:
        print(
            "Usage: python -m src.data.ingestion.web.clean_handbook "
            "[clean [--min-score N] [--min-words N] [--min-proc-score N]]"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
