"""Validate generated SQL through AST rules before execution."""

from __future__ import annotations

from agent.safety.ast_rules import validate_sql


def run(state: dict) -> dict:
    attempts = state.get("sql_attempts", [])
    if not attempts:
        return {}

    latest = attempts[-1]
    result = validate_sql(latest.sql)

    updated = latest.model_copy(
        update={
            "validator_verdict": "pass" if result.valid else f"fail: {result.reason}",
            "sql": result.sql if result.valid else latest.sql,
        }
    )

    new_attempts = list(attempts)
    new_attempts[-1] = updated
    return {"sql_attempts": new_attempts}


def route(state: dict) -> str:
    attempts = state.get("sql_attempts", [])
    if not attempts:
        return "repair"
    if attempts[-1].validator_verdict.startswith("pass"):
        return "execute"
    return "repair"
