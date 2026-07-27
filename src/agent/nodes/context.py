"""Retrieve trios, schema slice, and metric definitions for the current question."""

from __future__ import annotations

from agent.data.semantic_layer import format_metrics, format_schema


def run(state: dict) -> dict:
    """Load schema and metrics into state for downstream nodes."""
    return {
        "schema_slice": format_schema(),
        "metric_defs": format_metrics(),
        "retrieved_trios": [],
    }
