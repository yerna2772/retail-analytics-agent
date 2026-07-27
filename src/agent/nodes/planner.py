"""Decompose the question into a multi-step SQL plan."""

from __future__ import annotations

import json
import logging

from langchain_core.runnables import RunnableConfig

from agent.config import settings
from agent.llm.gateway import extract_json
from agent.prompts.registry import render_prompt
from agent.state import PlanStep

logger = logging.getLogger(__name__)


async def run(state: dict, config: RunnableConfig) -> dict:
    """Create a plan from the standalone question.

    For causal/comparison questions the LLM decomposes into
    multiple steps; simple questions become a single step.
    """
    llm = config["configurable"]["llm"]
    question = state.get("standalone_question", "")
    intent = state.get("intent", "analysis")

    if intent == "report_create" and state.get("query_results"):
        return {"plan": [], "current_step": 0, "replan_count": 0}

    if state.get("llm_call_count", 0) >= settings.max_llm_calls:
        step = PlanStep(index=0, question=question)
        return {"plan": [step], "current_step": 0, "replan_count": 0}

    prompt = render_prompt(
        "planner",
        schema=state.get("schema_slice", ""),
        metrics=state.get("metric_defs", ""),
        question=question,
    )

    try:
        response = await llm.generate(prompt)
        raw = extract_json(response)
        steps_data = json.loads(raw)

        if isinstance(steps_data, list) and steps_data:
            plan = [
                PlanStep(
                    index=s.get("index", i),
                    question=s.get("question", question),
                    depends_on=s.get("depends_on", []),
                )
                for i, s in enumerate(steps_data)
            ]
        else:
            plan = [PlanStep(index=0, question=question)]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.warning("Plan parse failed, single step: %s", exc)
        plan = [PlanStep(index=0, question=question)]

    return {
        "plan": plan,
        "current_step": 0,
        "replan_count": 0,
        "llm_call_count": state.get("llm_call_count", 0) + 1,
    }


def route(state: dict) -> str:
    plan = state.get("plan", [])
    if not plan and state.get("intent") == "report_create":
        return "compose_from_history"
    return "query"
