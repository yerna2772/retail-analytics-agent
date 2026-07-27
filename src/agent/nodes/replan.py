"""Check whether the plan has more steps or needs a follow-up query."""

from __future__ import annotations

from agent.config import settings


def run(state: dict) -> dict:
    """Advance to next plan step if one exists."""
    plan = state.get("plan", [])
    current = state.get("current_step", 0)

    if current < len(plan) - 1:
        return {"current_step": current + 1}
    return {}


def route(state: dict) -> str:
    plan = state.get("plan", [])
    current = state.get("current_step", 0)

    if state.get("llm_call_count", 0) >= settings.max_llm_calls:
        return "done"
    if state.get("bytes_scanned", 0) >= settings.max_bytes_scanned:
        return "done"

    if current < len(plan) - 1:
        return "more"
    return "done"
