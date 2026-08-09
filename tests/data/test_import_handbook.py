"""Tests for GitLab Handbook markdown cleaning pipeline."""

from __future__ import annotations

from src.data.ingestion.import_handbook import (
    classify_bpmn,
    clean_links,
    clean_markdown,
    clean_tables,
    normalize_whitespace,
    score_procedural,
    segment_sections,
    strip_code_blocks,
    strip_emphasis,
    strip_frontmatter,
    strip_html,
    strip_hugo_shortcodes,
    strip_images,
    strip_slack_refs,
)

# ── strip_frontmatter ─────────────────────────────────────────────────────────


class TestStripFrontmatter:
    def test_basic(self):
        text = '---\ntitle: "My Page"\n---\nHello world'
        title, body = strip_frontmatter(text)
        assert title == "My Page"
        assert body == "Hello world"

    def test_no_frontmatter(self):
        text = "No frontmatter here"
        title, body = strip_frontmatter(text)
        assert title == ""
        assert body == text

    def test_unquoted_title(self):
        text = "---\ntitle: My Page Title\n---\nBody"
        title, body = strip_frontmatter(text)
        assert title == "My Page Title"

    def test_extra_fields(self):
        text = '---\ntitle: "Page"\ndescription: "Desc"\nstatus: accepted\n---\nContent'
        title, body = strip_frontmatter(text)
        assert title == "Page"
        assert body == "Content"


# ── strip_hugo_shortcodes ──────────────────────────────────────────────────────


class TestStripHugoShortcodes:
    def test_inline(self):
        assert strip_hugo_shortcodes('{{< youtube "abc123" >}}') == ""

    def test_block_open_close(self):
        text = '{{% alert color="warning" %}}Warning text{{% /alert %}}'
        result = strip_hugo_shortcodes(text)
        assert "{{" not in result
        assert "Warning text" in result

    def test_include(self):
        text = '{{% include "includes/file.md" %}}'
        assert strip_hugo_shortcodes(text) == ""

    def test_preserves_normal_text(self):
        text = "This is normal text with no shortcodes."
        assert strip_hugo_shortcodes(text) == text


# ── strip_html ─────────────────────────────────────────────────────────────────


class TestStripHtml:
    def test_tags(self):
        assert strip_html("<b>bold</b>") == "bold"
        assert strip_html('<a href="url">link</a>') == "link"

    def test_comment(self):
        assert strip_html("before <!-- comment --> after") == "before  after"

    def test_multiline_comment(self):
        text = "start\n<!-- multi\nline\ncomment -->\nend"
        result = strip_html(text)
        assert "multi" not in result
        assert "start" in result
        assert "end" in result

    def test_style_attr(self):
        text = 'Image text\n{style="max-width: 50%;"}'
        result = strip_html(text)
        assert "style" not in result

    def test_font_awesome(self):
        text = '<i class="fas fa-map-marked-alt"></i>Quick Links'
        result = strip_html(text)
        assert "Quick Links" in result
        assert "<i" not in result

    def test_self_closing(self):
        assert strip_html("text <br/> more") == "text  more"


# ── strip_images ───────────────────────────────────────────────────────────────


class TestStripImages:
    def test_basic(self):
        assert strip_images("![alt text](/images/foo.png)") == ""

    def test_inline(self):
        text = "See ![diagram](/img/d.png) for details"
        result = strip_images(text)
        assert result == "See  for details"

    def test_preserves_links(self):
        text = "[not an image](url)"
        assert strip_images(text) == text


# ── strip_code_blocks ──────────────────────────────────────────────────────────


class TestStripCodeBlocks:
    def test_basic(self):
        text = "before\n```python\nprint('hello')\n```\nafter"
        result = strip_code_blocks(text)
        assert "print" not in result
        assert "before" in result
        assert "after" in result

    def test_mermaid(self):
        text = "text\n```mermaid\ngraph TD;\nA-->B;\n```\nmore"
        result = strip_code_blocks(text)
        assert "graph TD" not in result
        assert "text" in result

    def test_no_language(self):
        text = "a\n```\ncode\n```\nb"
        result = strip_code_blocks(text)
        assert "code" not in result


# ── clean_links ────────────────────────────────────────────────────────────────


class TestCleanLinks:
    def test_basic(self):
        assert clean_links("[click here](https://example.com)") == "click here"

    def test_internal(self):
        text = "See [the docs](/handbook/engineering/) for more"
        assert clean_links(text) == "See the docs for more"

    def test_multiple(self):
        text = "[a](url1) and [b](url2)"
        assert clean_links(text) == "a and b"

    def test_nested_parens(self):
        # Edge case: link text with special chars
        text = "[Section 1.2](/path#section)"
        assert clean_links(text) == "Section 1.2"


# ── clean_tables ───────────────────────────────────────────────────────────────


class TestCleanTables:
    def test_two_column(self):
        text = (
            "| Role | Responsibility |\n"
            "| --- | --- |\n"
            "| Manager | Approves requests |\n"
            "| Analyst | Reviews data |"
        )
        result = clean_tables(text)
        assert "- Role: Manager" in result
        assert "- Role: Analyst" in result

    def test_wide_table_removed(self):
        text = "| A | B | C | D |\n| - | - | - | - |\n| 1 | 2 | 3 | 4 |"
        result = clean_tables(text)
        assert "1" not in result

    def test_preserves_non_table(self):
        text = "Normal paragraph\nwith no tables"
        assert clean_tables(text) == text

    def test_three_column(self):
        text = "| Name | Type | Desc |\n| --- | --- | --- |\n| Foo | Bar | Baz |"
        result = clean_tables(text)
        assert "Foo" in result
        assert "Bar" in result


# ── strip_emphasis ─────────────────────────────────────────────────────────────


class TestStripEmphasis:
    def test_bold(self):
        assert strip_emphasis("**bold text**") == "bold text"

    def test_italic(self):
        assert strip_emphasis("*italic text*") == "italic text"

    def test_bold_italic(self):
        assert strip_emphasis("***both***") == "both"

    def test_mid_sentence(self):
        text = "The **manager** should *review* the request"
        result = strip_emphasis(text)
        assert result == "The manager should review the request"


# ── strip_slack_refs ───────────────────────────────────────────────────────────


class TestStripSlackRefs:
    def test_email(self):
        result = strip_slack_refs("Contact payroll@gitlab.com for help")
        assert "payroll@gitlab.com" not in result

    def test_backtick_email(self):
        result = strip_slack_refs("Send to `admin@gitlab.com` please")
        assert "admin@gitlab.com" not in result

    def test_channel(self):
        result = strip_slack_refs("Post in #procurement channel")
        assert "#procurement" not in result

    def test_mention(self):
        result = strip_slack_refs("Tag @security-team for review")
        assert "@security-team" not in result

    def test_preserves_headers(self):
        # # at start of line is a markdown header, not a channel
        text = "# Header\n## Sub Header"
        assert strip_slack_refs(text) == text


# ── normalize_whitespace ───────────────────────────────────────────────────────


class TestNormalizeWhitespace:
    def test_collapse_newlines(self):
        text = "a\n\n\n\nb"
        assert normalize_whitespace(text) == "a\n\nb"

    def test_strip_trailing(self):
        text = "line with spaces   \nnext line"
        result = normalize_whitespace(text)
        assert "line with spaces\n" in result

    def test_strip_outer(self):
        assert normalize_whitespace("\n\n  text  \n\n") == "text"


# ── clean_markdown (full pipeline) ────────────────────────────────────────────


class TestCleanMarkdown:
    def test_full_pipeline(self):
        raw = """---
title: "Test Process"
description: "A test"
---
<!-- lint disable -->

## Overview

The **process** starts when a [team member](/handbook/people/) submits a request.

![diagram](/images/flow.png)

{{% alert color="info" %}}This is important{{% /alert %}}

```bash
echo "hello"
```

| Step | Action |
| --- | --- |
| 1 | Submit form |
| 2 | Review |

Contact payroll@gitlab.com or tag @manager in #requests channel.
"""
        title, text = clean_markdown(raw)
        assert title == "Test Process"
        # No artifacts remain
        assert "<!--" not in text
        assert "{{" not in text
        assert "![" not in text
        assert "```" not in text
        assert "@gitlab.com" not in text
        # Content preserved
        assert "process" in text
        assert "team member" in text
        assert "Submit form" in text

    def test_empty_input(self):
        title, text = clean_markdown("")
        assert title == ""


# ── segment_sections ──────────────────────────────────────────────────────────


class TestSegmentSections:
    def _long_text(self, n=120):
        return " ".join(["word"] * n)

    def test_basic_segmentation(self):
        text = f"## Section A\n\n{self._long_text()}\n\n## Section B\n\n{self._long_text()}"
        sections = segment_sections("Page", text, min_words=50)
        assert len(sections) == 2
        assert sections[0]["section_title"] == "Section A"
        assert sections[1]["section_title"] == "Section B"

    def test_short_section_merged(self):
        text = f"## Long Section\n\n{self._long_text()}\n\n## Short\n\nfew words only"
        sections = segment_sections("Page", text, min_words=50)
        # Short section merged into previous
        assert len(sections) == 1
        assert "few words" in sections[0]["text"]

    def test_intro_included_if_long(self):
        intro = self._long_text(200)
        text = f"{intro}\n\n## Section\n\n{self._long_text()}"
        sections = segment_sections("Page Title", text, min_words=50)
        assert sections[0]["section_title"] == "Page Title"

    def test_intro_skipped_if_short(self):
        text = f"Short intro.\n\n## Section\n\n{self._long_text()}"
        sections = segment_sections("Page", text, min_words=50)
        assert sections[0]["section_title"] == "Section"

    def test_h3_also_splits(self):
        text = f"## Parent\n\n{self._long_text()}\n\n### Child\n\n{self._long_text()}"
        sections = segment_sections("Page", text, min_words=50)
        assert len(sections) == 2

    def test_empty_text(self):
        sections = segment_sections("Page", "", min_words=50)
        assert sections == []

    def test_word_count_accurate(self):
        text = f"## Section\n\n{self._long_text(150)}"
        sections = segment_sections("Page", text, min_words=50)
        assert sections[0]["words"] == 150


# ── score_procedural ──────────────────────────────────────────────────────────


class TestScoreProcedural:
    def test_strong_process(self):
        """Numbered steps + actors + verbs + conditions → high score."""
        text = (
            "The manager should review the request.\n"
            "1. Submit the form to the team member.\n"
            "2. The reviewer will approve or escalate.\n"
            "3. If the request is urgent, notify the lead.\n"
            "4. Complete the process by closing the ticket.\n"
            "Otherwise, schedule a follow-up."
        )
        score = score_procedural(text, "Onboarding Workflow")
        assert score >= 7

    def test_weak_conceptual(self):
        """Conceptual text with no steps, actors, or verbs → low score."""
        text = (
            "The architecture of our data platform is based on a "
            "modern lakehouse pattern. We use Snowflake as the warehouse "
            "and dbt for transformations. The overall strategy focuses on "
            "self-service analytics and data democratization across teams."
        )
        score = score_procedural(text, "Data Platform Architecture")
        assert score <= 2

    def test_legal_boilerplate_penalized(self):
        """Legal contract language gets negative penalty from title."""
        text = (
            "Neither party shall be liable for any indirect, incidental, "
            "special or consequential damages arising out of this agreement."
        )
        score = score_procedural(text, "11. LIMITATION OF LIABILITY")
        assert score < 0

    def test_medium_process(self):
        """Some verbs and actors but no numbered steps → medium score."""
        text = (
            "The team member should create a new issue and assign it "
            "to the manager for review. The engineer will verify the "
            "configuration before the request is approved."
        )
        score = score_procedural(text, "Access Request")
        assert 3 <= score <= 6

    def test_numbered_steps_boost(self):
        """Numbered steps alone add significant signal."""
        text = (
            "1. Open the dashboard.\n"
            "2. Click the settings icon.\n"
            "3. Select the target environment.\n"
            "4. Save changes."
        )
        score = score_procedural(text, "Configuration Steps")
        assert score >= 3  # steps(2) + verbs(1) = 3 minimum

    def test_legal_title_various(self):
        """Multiple legal title patterns are caught — all get penalty."""
        base = "Some generic text about agreements and terms."
        normal_score = score_procedural(base, "Process")
        for legal_title in ["CONFIDENTIALITY", "INDEMNIFICATION", "FORCE MAJEURE", "APPENDIX"]:
            legal_score = score_procedural(base, legal_title)
            assert legal_score < normal_score or legal_score < 0, (
                f"{legal_title} should score lower than normal"
            )

    def test_actors_capped(self):
        """Actor score is capped at 2 even with many actors."""
        text = (
            "The manager, engineer, analyst, coordinator, specialist, "
            "reviewer, approver, and lead all participate."
        )
        # Score from actors alone should be capped
        s1 = score_procedural(text, "Team")
        text2 = "The manager and engineer participate."
        s2 = score_procedural(text2, "Team")
        assert s1 == s2  # both capped at 2 for actors

    def test_verbs_tiered(self):
        """Verb scoring has tiers: 3+, 5+, 8+."""
        few = "Please submit the form and review it."
        mid = "Submit the form, review it, approve it, assign the task, and notify the team."
        many = "Submit, review, approve, assign, notify, validate, escalate, confirm, and close."
        s_few = score_procedural(few, "T")
        s_mid = score_procedural(mid, "T")
        s_many = score_procedural(many, "T")
        assert s_few < s_mid <= s_many


# ── classify_bpmn ─────────────────────────────────────────────────────────────


class TestClassifyBpmn:
    def test_ideal(self):
        """Steps + decisions + multiple actors → ideal."""
        text = (
            "1. The manager submits the request.\n"
            "2. The engineer reviews and validates it.\n"
            "3. If the request is approved, the coordinator schedules it.\n"
            "4. Otherwise, the manager revises and resubmits."
        )
        assert classify_bpmn(text) == "ideal"

    def test_good_steps_and_decisions(self):
        """Steps + decisions but single actor type → good."""
        text = (
            "1. Submit the form.\n"
            "2. Wait for processing.\n"
            "3. If approved, proceed to next phase.\n"
            "4. Otherwise, retry."
        )
        assert classify_bpmn(text) == "good"

    def test_good_steps_and_actors(self):
        """Steps + multiple actors but no decisions → good."""
        text = (
            "1. The manager creates the ticket.\n"
            "2. The engineer picks it up.\n"
            "3. The reviewer approves the change."
        )
        assert classify_bpmn(text) == "good"

    def test_linear(self):
        """Steps only, no decisions or multiple actors → linear."""
        text = "1. Open the page.\n2. Click the button.\n3. Save the result."
        assert classify_bpmn(text) == "linear"

    def test_marginal(self):
        """No numbered steps → marginal regardless of other signals."""
        text = (
            "The manager should review all pending items. "
            "If urgent, the engineer escalates to the director. "
            "Otherwise the analyst handles it."
        )
        assert classify_bpmn(text) == "marginal"

    def test_few_steps_is_marginal(self):
        """Fewer than 3 numbered steps → marginal."""
        text = "1. Do the first thing.\n2. Do the second thing.\nThe rest is flexible."
        assert classify_bpmn(text) == "marginal"
