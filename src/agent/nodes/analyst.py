"""Interpret query results and format the answer for the user."""

from __future__ import annotations

import json
import logging

from langchain_core.runnables import RunnableConfig

from agent.config import settings
from agent.prompts.registry import render_prompt

logger = logging.getLogger(__name__)


def _format_results(results: list) -> str:
    if not results:
        return "(no data returned)"
    lines = []
    for qr in results:
        lines.append(f"Question: {qr.question}")
        lines.append(f"SQL: {qr.sql}")
        lines.append(f"Rows returned: {qr.row_count}")
        if qr.rows:
            lines.append("Data:")
            lines.append(json.dumps(qr.rows[:50], indent=2, default=str))
        lines.append("")
    return "\n".join(lines)


def _fallback_answer(results: list) -> str:
    """Format raw query results when the LLM budget is exhausted."""
    lines = ["Here are the results:\n"]
    for qr in results:
        if qr.rows:
            cols = list(qr.rows[0].keys())
            lines.append(" | ".join(cols))
            lines.append("-" * (len(" | ".join(cols))))
            for row in qr.rows[:20]:
                lines.append(" | ".join(str(row.get(c, "")) for c in cols))
            if qr.row_count > 20:
                lines.append(f"... and {qr.row_count - 20} more rows")
        lines.append("")
    return "\n".join(lines)


async def run(state: dict, config: RunnableConfig) -> dict:
    llm = config["configurable"]["llm"]
    results = state.get("query_results", [])
    question = state.get("standalone_question", "")

    if state.get("llm_call_count", 0) >= settings.max_llm_calls:
        if results:
            return {"final_answer": _fallback_answer(results)}
        return {"final_answer": "Budget exhausted before analysis could complete."}

    prompt = render_prompt(
        "analyst",
        question=question,
        results=_format_results(results),
    )

    response = await llm.generate(prompt)

    return {
        "final_answer": response,
        "llm_call_count": state.get("llm_call_count", 0) + 1,
    }


def route(state: dict) -> str:
    if state.get("intent") == "report_create":
        return "report"
    return "chat"
