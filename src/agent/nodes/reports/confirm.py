"""Pause for user confirmation before destructive operations."""

from __future__ import annotations


def run(state: dict) -> dict:
    """Stub — always declines. Real implementation with interrupt() in Step 5."""
    return {"delete_confirmed": False}
