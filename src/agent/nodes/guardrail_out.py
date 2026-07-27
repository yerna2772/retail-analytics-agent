"""Final output guardrail — scrubs PII from any answer leaving the system."""

from __future__ import annotations

from agent.safety.pii import scrub_output


def run(state: dict) -> dict:
    answer = state.get("final_answer", "")
    if answer:
        answer = scrub_output(answer)
    return {"final_answer": answer}
