"""Final output guardrail — scrubs PII from any answer leaving the system."""

from __future__ import annotations

from agent.safety.pii import scrub_output


def run(state: dict) -> dict:
    answer = state.get("final_answer", "")
    error = state.get("error")

    if error and not answer:
        answer = f"I wasn't able to complete that request. {error}"

    if state.get("intent") == "refuse":
        reason = ""
        verdicts = state.get("guardrail_verdicts", [])
        for v in verdicts:
            if not v.passed and v.reason:
                reason = v.reason
                break
        answer = reason or "I can only help with retail analytics questions."

    if answer:
        answer = scrub_output(answer)

    return {"final_answer": answer}
