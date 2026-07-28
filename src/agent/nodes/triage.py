"""Classify intent, resolve follow-ups, and route the turn."""

from __future__ import annotations

import json
import logging

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from agent.llm.gateway import extract_json
from agent.prompts.registry import load_prompt
from agent.state import GuardrailVerdict

logger = logging.getLogger(__name__)


def _format_history(messages: list) -> str:
    lines = []
    for msg in messages:
        role = "User" if isinstance(msg, HumanMessage) else "Assistant"
        lines.append(f"{role}: {msg.content}")
    return "\n".join(lines) if lines else "(no prior messages)"


async def run(state: dict, config: RunnableConfig) -> dict:
    llm = config["configurable"]["llm"]
    messages = state.get("messages", [])

    if not messages:
        return {"intent": "metadata", "standalone_question": "", "guardrail_verdicts": []}

    latest_msg = messages[-1]
    latest = latest_msg.content if hasattr(latest_msg, "content") else str(latest_msg)
    history = _format_history(messages[:-1])

    system_prompt = load_prompt("triage")
    prompt = f"Conversation:\n{history}\n\nLatest message: {latest}"

    try:
        response = await llm.generate(prompt, system=system_prompt)
        data = json.loads(extract_json(response))
        intent = data.get("intent", "metadata")
        standalone = data.get("standalone_question", latest)
        is_safe = data.get("is_safe", True)
        refusal_reason = data.get("refusal_reason")
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.warning("Triage parse failed, defaulting to metadata: %s", exc)
        intent = "metadata"
        standalone = latest
        is_safe = True
        refusal_reason = None

    if not is_safe:
        intent = "refuse"

    verdicts = [
        GuardrailVerdict(
            layer="intent",
            passed=is_safe,
            reason=refusal_reason,
        )
    ]

    return {
        "intent": intent,
        "standalone_question": standalone,
        "guardrail_verdicts": verdicts,
        "llm_call_count": 1,
        "repair_count": 0,
        "replan_count": 0,
        "bytes_scanned": 0,
        "sql_attempts": [],
        "plan": [],
        "current_step": 0,
        "error": None,
        "final_answer": "",
        "degradation_level": 0,
    }
