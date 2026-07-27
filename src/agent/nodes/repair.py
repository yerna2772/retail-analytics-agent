"""Feed dry_run errors back to the generator for a retry, up to the budget cap."""

from __future__ import annotations


def run(state: dict) -> dict:
    """Stub — no repair logic yet. Real implementation in Step 6."""
    return {}


def route(state: dict) -> str:
    """Stub — always give up (no retry in stubs)."""
    return "give_up"
