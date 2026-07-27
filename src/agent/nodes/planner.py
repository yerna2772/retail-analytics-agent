"""Decompose the question into a multi-step SQL plan."""

from __future__ import annotations


def run(state: dict) -> dict:
    """Stub — empty plan. Real planning in Step 2."""
    return {"plan": [], "current_step": 0, "replan_count": 0}


def route(state: dict) -> str:
    """Stub — always route to SQL generation."""
    return "query"
