"""Resolve deletion targets by ownership filter and risk tier.

Invariant 4: IDs are resolved HERE, before the confirmation pause.
Invariant 6: ownership filter applied in code, never by model.
"""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from agent.state import ReportRef


def _risk_tier(matches: list, question: str) -> str:
    """Deterministic risk tiering — no LLM involvement."""
    if len(matches) > 10:
        return "high"
    if len(matches) > 1:
        return "medium"
    return "low"


async def run(state: dict, config: RunnableConfig) -> dict:
    """Find reports matching the deletion request, filtered by owner."""
    report_store = config["configurable"].get("report_store")
    if not report_store:
        return {"delete_targets": [], "delete_risk_tier": "low"}

    owner_id = state.get("user_id", "default")
    all_reports = await report_store.list_reports(owner_id)

    question = state.get("standalone_question", "").lower()

    matches = []
    for r in all_reports:
        title_lower = r.title.lower()
        if any(word in title_lower for word in question.split() if len(word) > 3):
            matches.append(r)

    if not matches and all_reports:
        matches = all_reports

    targets = [
        ReportRef(
            id=r.id,
            title=r.title,
            created_at=r.created_at,
            thread_id=r.thread_id,
        )
        for r in matches
    ]

    tier = _risk_tier(matches, question)

    return {"delete_targets": targets, "delete_risk_tier": tier}
