"""Dry-run and execute validated SQL against BigQuery."""

from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig

from agent.config import settings
from agent.state import QueryResult

logger = logging.getLogger(__name__)


async def run(state: dict, config: RunnableConfig) -> dict:
    bq = config["configurable"]["bq"]
    attempts = state.get("sql_attempts", [])
    if not attempts:
        return {}

    latest = attempts[-1]

    dry = await bq.dry_run(latest.sql)
    estimated = dry.get("estimated_bytes", 0)

    if not dry.get("ok", True):
        updated = latest.model_copy(update={"dry_run_error": dry.get("error", "dry_run failed")})
        new_attempts = list(attempts)
        new_attempts[-1] = updated
        return {"sql_attempts": new_attempts}

    remaining = settings.max_bytes_scanned - state.get("bytes_scanned", 0)
    if estimated > remaining:
        msg = f"Estimated {estimated:,}B exceeds budget {remaining:,}B"
        updated = latest.model_copy(
            update={
                "estimated_bytes": estimated,
                "dry_run_error": msg,
            }
        )
        new_attempts = list(attempts)
        new_attempts[-1] = updated
        return {"sql_attempts": new_attempts, "error": "Query over byte budget"}

    result = await bq.execute(latest.sql)

    plan = state.get("plan", [])
    current = state.get("current_step", 0)
    question = plan[current].question if current < len(plan) else ""

    qr = QueryResult(
        step_index=current,
        question=question,
        sql=latest.sql,
        columns=result.get("columns", []),
        rows=result.get("rows", []),
        row_count=result.get("row_count", 0),
        bytes_scanned=result.get("bytes_scanned", 0),
    )

    return {
        "query_results": list(state.get("query_results", [])) + [qr],
        "bytes_scanned": state.get("bytes_scanned", 0) + qr.bytes_scanned,
    }


def route(state: dict) -> str:
    if state.get("error"):
        return "degrade"

    attempts = state.get("sql_attempts", [])
    if attempts and attempts[-1].dry_run_error:
        return "repair"

    results = state.get("query_results", [])
    if results and results[-1].row_count == 0:
        return "replan"

    return "replan"
