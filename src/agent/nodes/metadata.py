"""Answer questions about the database schema and agent capabilities."""

from __future__ import annotations


def run(state: dict) -> dict:
    """Stub — canned capability summary. Real implementation in Step 2."""
    return {
        "final_answer": (
            "I'm a retail analytics agent for the thelook_ecommerce dataset. "
            "I can help you analyse customer behaviour, revenue trends, "
            "product performance, and more. "
            "[Demo mode — full analysis available after Step 2.]"
        ),
    }
