"""Check whether the plan has more steps or needs follow-up queries."""

from __future__ import annotations

import json
import logging

from langchain_core.runnables import RunnableConfig

from agent.config import settings
from agent.llm.gateway import extract_json
from agent.prompts.registry import render_prompt
from agent.state import PlanStep

logger = logging.getLogger(__name__)

MAX_REPLANS = 2


def _format_results(results: list) -> str:
    lines = []
    for qr in results:
        lines.append(f"Step {qr.step_index}: {qr.question}")
        lines.append(f"  SQL: {qr.sql}")
        lines.append(f"  Rows: {qr.row_count}")
        if qr.rows:
            lines.append(f"  Sample: {json.dumps(qr.rows[:5], default=str)}")
        lines.append("")
    return "\n".join(lines)


async def run(state: dict, config: RunnableConfig) -> dict:
    """Advance to next step, or ask the LLM if more queries are needed."""
    plan = state.get("plan", [])
    current = state.get("current_step", 0)

    if current < len(plan) - 1:
        return {"current_step": current + 1}

    replan_count = state.get("replan_count", 0)
    if replan_count >= MAX_REPLANS:
        return {}
    if state.get("llm_call_count", 0) >= settings.max_llm_calls:
        return {}

    llm = config["configurable"]["llm"]
    question = state.get("standalone_question", "")
    results = state.get("query_results", [])

    if not results:
        return {}

    prompt = render_prompt(
        "replan",
        question=question,
        results=_format_results(results),
    )

    try:
        response = await llm.generate(prompt)
        data = json.loads(extract_json(response))
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.warning("Replan parse failed: %s", exc)
        return {"llm_call_count": state.get("llm_call_count", 0) + 1}

    needs_more = data.get("needs_more", False)
    new_steps_data = data.get("steps", [])

    if not needs_more or not new_steps_data:
        return {"llm_call_count": state.get("llm_call_count", 0) + 1}

    next_idx = len(plan)
    new_steps = [
        PlanStep(
            index=next_idx + i,
            question=s.get("question", ""),
            depends_on=s.get("depends_on", []),
        )
        for i, s in enumerate(new_steps_data[:2])
    ]

    return {
        "plan": list(plan) + new_steps,
        "current_step": next_idx,
        "replan_count": replan_count + 1,
        "llm_call_count": state.get("llm_call_count", 0) + 1,
    }


def route(state: dict) -> str:
    plan = state.get("plan", [])
    current = state.get("current_step", 0)

    if state.get("llm_call_count", 0) >= settings.max_llm_calls:
        return "done"
    if state.get("bytes_scanned", 0) >= settings.max_bytes_scanned:
        return "done"

    if current < len(plan) - 1:
        return "more"

    if state.get("replan_count", 0) > 0:
        last_replan = state.get("replan_count", 0)
        if last_replan <= MAX_REPLANS and current < len(plan):
            return "more"

    return "done"
