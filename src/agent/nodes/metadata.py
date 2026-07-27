"""Answer questions about the database schema and agent capabilities."""

from __future__ import annotations

from agent.data.semantic_layer import format_metrics, get_safe_schema


def run(state: dict) -> dict:
    """Build a capability summary from the semantic layer — no LLM call."""
    schema = get_safe_schema()

    table_descs = {
        "users": "Customer demographics (age, gender, state, city, traffic source)",
        "orders": "Order headers (status, timestamps, item count)",
        "order_items": "Line items with sale prices and fulfillment status",
        "products": "Product catalog (name, brand, category, cost, retail price)",
    }

    lines = ["I have access to the **thelook_ecommerce** dataset with these tables:\n"]
    for table in sorted(schema):
        cols = sorted(schema[table].keys())
        desc = table_descs.get(table, "")
        lines.append(f"  **{table}** — {desc}")
        lines.append(f"    Columns: {', '.join(cols)}\n")

    lines.append("I can help you with:")
    lines.append("  - Revenue, AOV, return rate, and other metrics over time")
    lines.append("  - Customer behaviour: top spenders, cohort analysis")
    lines.append("  - Product and category comparisons")
    lines.append("  - Multi-step causal questions (e.g. why did churn spike)")
    lines.append("  - Creating reports with action items")

    metrics = format_metrics()
    if metrics:
        lines.append(f"\nDefined metrics:\n{metrics}")

    return {"final_answer": "\n".join(lines)}
