"""Persist a composed report to the report store."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from langchain_core.runnables import RunnableConfig

from agent.store.reports import Report


async def run(state: dict, config: RunnableConfig) -> dict:
    """Save the draft report to the store."""
    report_store = config["configurable"].get("report_store")
    if not report_store:
        report_id = uuid.uuid4().hex[:12]
        return {
            "saved_report_id": report_id,
            "final_answer": (
                state.get("draft_report", "") + f"\n\n*Report saved (id: {report_id})*"
            ),
        }

    report = Report(
        id=uuid.uuid4().hex[:12],
        owner_id=state.get("user_id", "default"),
        thread_id=state.get("thread_id", ""),
        title=state.get("draft_report", "").split("\n")[0].lstrip("# "),
        body=state.get("draft_report", ""),
        action_items=state.get("action_items", []),
        created_at=datetime.now(UTC).isoformat(),
    )

    report_id = await report_store.save(report)

    return {
        "saved_report_id": report_id,
        "final_answer": (state.get("draft_report", "") + f"\n\n*Report saved (id: {report_id})*"),
    }
