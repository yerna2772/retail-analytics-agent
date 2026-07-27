"""Compose a structured report with title, findings, and action items."""

from __future__ import annotations

import json
import logging

from langchain_core.runnables import RunnableConfig

from agent.config import settings
from agent.llm.gateway import extract_json
from agent.prompts.registry import render_prompt

logger = logging.getLogger(__name__)


def _format_results(results: list) -> str:
    if not results:
        return "(no data)"
    lines = []
    for qr in results:
        lines.append(f"Question: {qr.question}")
        lines.append(f"SQL: {qr.sql}")
        lines.append(f"Rows: {qr.row_count}")
        if qr.rows:
            lines.append(json.dumps(qr.rows[:20], indent=2, default=str))
        lines.append("")
    return "\n".join(lines)


async def run(state: dict, config: RunnableConfig) -> dict:
    """Compose a report from analysis results."""
    llm = config["configurable"]["llm"]

    if state.get("llm_call_count", 0) >= settings.max_llm_calls:
        return {"draft_report": "Budget exhausted.", "action_items": []}

    question = state.get("standalone_question", "")
    results = state.get("query_results", [])
    final_answer = state.get("final_answer", "")

    results_text = _format_results(results)
    if final_answer:
        results_text += f"\nAnalysis summary:\n{final_answer}"

    prompt = render_prompt(
        "compose_report",
        question=question,
        results=results_text,
    )

    try:
        response = await llm.generate(prompt)
        data = json.loads(extract_json(response))
        title = data.get("title", "Untitled Report")
        period = data.get("period", "")
        findings = data.get("findings", [])
        action_items = data.get("action_items", [])
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.warning("Report compose parse failed: %s", exc)
        title = "Analysis Report"
        period = ""
        findings = [final_answer] if final_answer else []
        action_items = []

    body_parts = [f"# {title}"]
    if period:
        body_parts.append(f"\n**Period:** {period}")
    if findings:
        body_parts.append("\n## Findings")
        for i, f in enumerate(findings, 1):
            body_parts.append(f"  {i}. {f}")
    if action_items:
        body_parts.append("\n## Action Items")
        for i, a in enumerate(action_items, 1):
            body_parts.append(f"  {i}. {a}")

    return {
        "draft_report": "\n".join(body_parts),
        "action_items": action_items,
        "final_answer": "\n".join(body_parts),
        "llm_call_count": state.get("llm_call_count", 0) + 1,
    }
