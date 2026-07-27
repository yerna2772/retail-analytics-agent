"""Produce a gracefully degraded response when the agent cannot fully answer."""

from __future__ import annotations


def run(state: dict) -> dict:
    """Stub — no degradation logic yet. Real implementation in Step 6."""
    return {"final_answer": "I was unable to complete this analysis.", "degradation_level": 1}
