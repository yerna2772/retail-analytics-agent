from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from agent.safety.ast_rules import TABLE_SCHEMA
from agent.safety.pii import PII_COLUMNS

_METRICS_PATH = Path(__file__).parents[3] / "semantic" / "metrics.yaml"
_metrics_cache: dict[str, Any] | None = None


def get_safe_schema() -> dict[str, dict[str, str]]:
    """Table schema with PII columns stripped — safe to show the LLM."""
    safe: dict[str, dict[str, str]] = {}
    for table, columns in TABLE_SCHEMA.items():
        safe[table] = {
            col: dtype
            for col, dtype in columns.items()
            if (table.lower(), col.lower()) not in PII_COLUMNS
        }
    return safe


def format_schema(schema: dict[str, dict[str, str]] | None = None) -> str:
    if schema is None:
        schema = get_safe_schema()
    lines = []
    for table in sorted(schema):
        cols = ", ".join(f"{c} ({t})" for c, t in sorted(schema[table].items()))
        lines.append(f"  {table}: {cols}")
    return "\n".join(lines)


def load_metrics() -> dict[str, Any]:
    global _metrics_cache
    if _metrics_cache is not None:
        return _metrics_cache
    if not _METRICS_PATH.exists():
        return {}
    with open(_METRICS_PATH) as f:
        _metrics_cache = yaml.safe_load(f) or {}
    return _metrics_cache


def format_metrics(metrics: dict[str, Any] | None = None) -> str:
    if metrics is None:
        metrics = load_metrics()
    lines = []
    for name in sorted(metrics):
        defn = metrics[name]
        expr = defn.get("sql", "")
        filt = defn.get("filter", "")
        line = f"  {name}: {expr}"
        if filt:
            line += f"  (WHERE {filt})"
        lines.append(line)
    return "\n".join(lines)
