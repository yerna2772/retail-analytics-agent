"""Feed dry_run errors back to the generator for a retry, up to the budget cap."""

from __future__ import annotations

from agent.config import settings


def run(state: dict) -> dict:
    """Increment repair count. Real error-feedback prompt in Step 6."""
    return {"repair_count": state.get("repair_count", 0) + 1}


def route(state: dict) -> str:
    if state.get("repair_count", 0) >= settings.max_repair_attempts:
        return "give_up"
    return "retry"
