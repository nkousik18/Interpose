"""Regex-based PII redaction (docs/INTERPOSE_SCOPING.md Section 9.8, P3), applied to
response payloads only (Stage 8) -- see `schema.PiiRedactionEffect`'s docstring for
why never request arguments. Regex matching for PII is inherently imprecise (a
16-digit account number and a credit card number look alike); these patterns are a
reasonable MVP net, not a claim of perfect detection.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

REDACTED_PLACEHOLDER = "[REDACTED]"

PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    # Anchored to start and end on a digit (not an optional separator) -- a naive
    # `(?:\d[ -]?){13,16}` can greedily absorb a trailing space/dash into the match,
    # which this module's own tests caught (a redacted card number was swallowing
    # the space before the next word).
    "credit_card": re.compile(r"\b\d(?:[ -]?\d){12,15}\b"),
    # US bank routing number (9 digits) immediately followed by an account number
    # (4-17 digits) -- "a full routing/account combination," per Section 9.8, not a
    # bare routing number alone (routing numbers are public per-bank identifiers,
    # not sensitive on their own).
    "bank_account": re.compile(r"\b\d{9}[ -]?\d{4,17}\b"),
}


def redact_text(text: str, pattern_names: list[str]) -> str:
    for name in pattern_names:
        pattern = PII_PATTERNS.get(name)
        if pattern is None:
            logger.warning("policy.pii_redaction.unknown_pattern name=%s", name)
            continue
        text = pattern.sub(REDACTED_PLACEHOLDER, text)
    return text


def redact_json_value(value: Any, pattern_names: list[str]) -> Any:
    """Walks an arbitrary parsed-JSON value (the shape of a tool's `content`/
    `structuredContent`), redacting every string leaf -- deliberately generic rather
    than schema-aware, since a redaction policy shouldn't need to know each upstream
    server's specific response models."""
    if isinstance(value, str):
        return redact_text(value, pattern_names)
    if isinstance(value, list):
        return [redact_json_value(item, pattern_names) for item in value]
    if isinstance(value, dict):
        return {key: redact_json_value(item, pattern_names) for key, item in value.items()}
    return value
