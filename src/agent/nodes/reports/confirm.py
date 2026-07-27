"""Pause for user confirmation before destructive operations.

Invariant 4: The targets were already resolved; this node only
asks for permission. It does NOT re-query or re-filter.
"""

from __future__ import annotations


def run(state: dict) -> dict:
    """In demo mode, auto-confirm for low tier, decline for others.

    In production, this uses LangGraph interrupt() to pause the graph
    and wait for user input. The interrupt() flow is wired in Step 9.
    """
    targets = state.get("delete_targets", [])
    tier = state.get("delete_risk_tier", "low")

    if not targets:
        return {"delete_confirmed": False}

    if tier == "low" and len(targets) == 1:
        return {"delete_confirmed": True}

    return {"delete_confirmed": False}
