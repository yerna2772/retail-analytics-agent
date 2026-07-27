"""Probe empty results to distinguish filter-too-narrow from no-such-data."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def run(state: dict) -> dict:
    """Check the latest result and set context for the next sql_generator call.

    If results were empty, note why so the generator can adjust.
    """
    results = state.get("query_results", [])
    if not results:
        return {}

    latest = results[-1]
    if latest.row_count == 0:
        return {
            "error": (
                "The query returned no results. "
                "The filter may be too narrow or the data may not exist."
            ),
        }

    return {}
