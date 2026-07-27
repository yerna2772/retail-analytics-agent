"""Generate a SQL query for the current plan step."""

from __future__ import annotations

import json
import logging

from langchain_core.runnables import RunnableConfig

from agent.config import settings
from agent.llm.gateway import clean_sql
from agent.prompts.registry import render_prompt
from agent.state import SQLAttempt

logger = logging.getLogger(__name__)


def _prior_results_context(state: dict, step) -> str:
    """Format prior step results for dependent steps."""
    if not step.depends_on:
        return ""
    results = state.get("query_results", [])
    lines = []
    for dep_idx in step.depends_on:
        for qr in results:
            if qr.step_index == dep_idx:
                lines.append(f"Prior step {dep_idx}: {qr.question}")
                lines.append(f"  Rows: {qr.row_count}")
                if qr.rows:
                    lines.append(f"  Data: {json.dumps(qr.rows[:10], default=str)}")
    if not lines:
        return ""
    return "\nPrior results:\n" + "\n".join(lines) + "\n"


async def run(state: dict, config: RunnableConfig) -> dict:
    llm = config["configurable"]["llm"]

    if state.get("llm_call_count", 0) >= settings.max_llm_calls:
        return {"error": "LLM call budget exhausted"}

    plan = state.get("plan", [])
    current = state.get("current_step", 0)
    if current >= len(plan):
        return {}

    step = plan[current]
    schema = state.get("schema_slice", "")
    metrics = state.get("metric_defs", "")

    trios = state.get("retrieved_trios", [])
    examples = ""
    if trios:
        lines = []
        for t in trios[:3]:
            lines.append(f"Example — Q: {t.question_variants[0]}\nSQL: {t.sql}")
        examples = "\nExamples:\n" + "\n\n".join(lines) + "\n"

    prior_ctx = _prior_results_context(state, step)

    prompt = render_prompt(
        "sql_generator",
        schema=schema,
        metrics=metrics,
        examples=examples + prior_ctx,
        question=step.question,
    )

    response = await llm.generate(prompt)
    sql = clean_sql(response)

    existing = state.get("sql_attempts", [])
    step_attempts = [a for a in existing if a.step_index == current]
    attempt_num = len(step_attempts) + 1

    attempt = SQLAttempt(
        step_index=current,
        attempt=attempt_num,
        sql=sql,
        validator_verdict="pending",
    )

    return {
        "sql_attempts": list(existing) + [attempt],
        "llm_call_count": state.get("llm_call_count", 0) + 1,
    }
