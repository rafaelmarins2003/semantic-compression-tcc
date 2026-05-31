"""Validate BPMN 2.0 XML against the official OMG XSD bundle.

The schema set lives in `schemas/` (BPMN20.xsd + its includes/imports). It is
compiled once and cached at module level, since `etree.XMLSchema` construction
is the expensive part and the schema never changes at runtime.

Validation is independent of well-formedness/unique-id checks: this answers
"is it schema-valid BPMN 2.0?", not "is the logic preserved?".
"""

from __future__ import annotations

import functools
from pathlib import Path

from lxml import etree

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "BPMN20.xsd"


@functools.lru_cache(maxsize=1)
def _schema() -> etree.XMLSchema:
    """Compile and cache the BPMN 2.0 XML Schema."""
    return etree.XMLSchema(etree.parse(str(SCHEMA_PATH)))


def validate_bpmn_xsd(xml_text: str) -> list[str]:
    """Return XSD validation errors for `xml_text`; empty list means valid.

    A malformed XML string is reported as a single syntax error rather than
    raising, so callers can treat every failure mode uniformly.
    """
    try:
        doc = etree.fromstring(xml_text.encode("utf-8"))
    except etree.XMLSyntaxError as exc:
        return [f"not well-formed: {exc}"]

    schema = _schema()
    if schema.validate(doc):
        return []
    return [f"line {e.line}: {e.message}" for e in schema.error_log]
