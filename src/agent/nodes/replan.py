"""Check whether the plan has more steps or needs a follow-up query."""

from __future__ import annotations


def run(state: dict) -> dict:
    """Stub — no replanning yet. Real implementation in Step 3."""
    return {}


def route(state: dict) -> str:
    """Stub — always done (no more steps)."""
    return "done"
