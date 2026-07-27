"""Produce a gracefully degraded response when the agent cannot fully answer."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

DEGRADATION_MESSAGES = {
    1: "I encountered an issue but was able to provide a partial answer.",
    2: "I couldn't run the analysis but can describe what I'd look for.",
    3: "The query failed after retries. Here's what I know so far.",
    4: "I'm unable to process this request right now.",
    5: "Service unavailable. Please try again later.",
}


def _assess_level(state: dict) -> int:
    """Five-level degradation ladder based on what went wrong."""
    error = state.get("error", "")
    repair_count = state.get("repair_count", 0)
    results = state.get("query_results", [])

    if "budget" in str(error).lower() or "exhausted" in str(error).lower():
        return 4

    if repair_count >= 3:
        if results:
            return 3
        return 4

    if results:
        return 1

    if error:
        return 3

    return 2


def run(state: dict) -> dict:
    level = _assess_level(state)
    msg = DEGRADATION_MESSAGES.get(level, DEGRADATION_MESSAGES[4])

    results = state.get("query_results", [])
    if results:
        partial = []
        for qr in results:
            if qr.rows:
                partial.append(f"  {qr.question}: {qr.row_count} rows returned")
        if partial:
            msg += "\n\nPartial results:\n" + "\n".join(partial)

    error = state.get("error")
    if error:
        msg += f"\n\nDetails: {error}"

    return {"final_answer": msg, "degradation_level": level}
