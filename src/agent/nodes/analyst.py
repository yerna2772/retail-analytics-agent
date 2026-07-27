"""Interpret query results and format the answer for the user."""

from __future__ import annotations


def run(state: dict) -> dict:
    """Stub — no analysis yet. Real implementation in Step 2."""
    return {"final_answer": ""}


def route(state: dict) -> str:
    """Stub — always route to chat (no report creation)."""
    return "chat"
