"""Retrieve trios, schema slice, and metric definitions for the current question."""

from __future__ import annotations

from agent.data.golden_bucket import retrieve
from agent.data.semantic_layer import format_metrics, format_schema


def run(state: dict) -> dict:
    """Load schema, metrics, and relevant trios into state."""
    question = state.get("standalone_question", "")
    trios = retrieve(question, top_k=3) if question else []

    return {
        "schema_slice": format_schema(),
        "metric_defs": format_metrics(),
        "retrieved_trios": trios,
    }
