"""Decompose the question into a multi-step SQL plan."""

from __future__ import annotations

from agent.state import PlanStep


def run(state: dict) -> dict:
    """Single-step plan for Step 2. Multi-step replanning comes in Step 3."""
    question = state.get("standalone_question", "")
    intent = state.get("intent", "analysis")

    if intent == "report_create" and state.get("query_results"):
        return {"plan": [], "current_step": 0, "replan_count": 0}

    step = PlanStep(index=0, question=question)
    return {"plan": [step], "current_step": 0, "replan_count": 0}


def route(state: dict) -> str:
    plan = state.get("plan", [])
    if not plan and state.get("intent") == "report_create":
        return "compose_from_history"
    return "query"
