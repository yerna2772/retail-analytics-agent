from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

PII_COLUMNS: frozenset[tuple[str, str]] = frozenset(
    {
        ("users", "first_name"),
        ("users", "last_name"),
        ("users", "email"),
        ("users", "street_address"),
        ("users", "postal_code"),
        ("users", "latitude"),
        ("users", "longitude"),
        ("users", "user_geom"),
    }
)

PII_COLUMN_NAMES: frozenset[str] = frozenset(col for _, col in PII_COLUMNS)


def is_pii_column(table: str, column: str) -> bool:
    return (table.lower(), column.lower()) in PII_COLUMNS


def is_pii_column_name(column: str) -> bool:
    return column.lower() in PII_COLUMN_NAMES


_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
_POSTAL_RE = re.compile(r"\b\d{5}(?:-\d{4})?\b")
_STREET_RE = re.compile(
    r"\b\d+\s+(?:[A-Za-z]+\s+){1,3}"
    r"(?:St|Street|Ave|Avenue|Blvd|Boulevard|Dr|Drive|Ln|Lane|Rd|Road|"
    r"Ct|Court|Way|Pl|Place)\b",
    re.IGNORECASE,
)

_REDACTED = "[REDACTED]"


def scrub_output(text: str) -> str:
    original = text
    text = _EMAIL_RE.sub(_REDACTED, text)
    text = _PHONE_RE.sub(_REDACTED, text)
    text = _STREET_RE.sub(_REDACTED, text)
    text = _POSTAL_RE.sub(_REDACTED, text)
    if text != original:
        logger.critical(
            "PII scrubbed from output — this layer should never fire in normal operation"
        )
    return text


def enforce_k_anonymity(
    rows: list[dict[str, Any]],
    count_column: str = "user_count",
    min_k: int = 5,
) -> list[dict[str, Any]]:
    if not rows or count_column not in rows[0]:
        return rows
    return [r for r in rows if int(r[count_column]) >= min_k]
