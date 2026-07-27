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


async def run(state: dict, config: RunnableConfig) -> dict:
    llm = config["configurable"]["llm"]

    if state.get("llm_call_count", 0) >= settings.max_llm_calls:
        return {"final_answer": "Budget exhausted before analysis could complete."}

    results = state.get("query_results", [])
    question = state.get("standalone_question", "")

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
