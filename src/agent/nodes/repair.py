"""Feed dry_run/validator errors back to the generator for a retry."""

from __future__ import annotations

import logging

from agent.config import settings

logger = logging.getLogger(__name__)


def run(state: dict) -> dict:
    """Increment repair count. Error context is already in sql_attempts
    for sql_generator to reference on the retry.
    """
    return {"repair_count": state.get("repair_count", 0) + 1}


def route(state: dict) -> str:
    if state.get("repair_count", 0) >= settings.max_repair_attempts:
        return "give_up"
    return "retry"
