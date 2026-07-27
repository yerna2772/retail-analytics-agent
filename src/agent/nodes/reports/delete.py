"""Soft-delete reports by pre-resolved IDs and write an audit row.

Invariant 4: Deletes by IDs resolved BEFORE confirmation, not re-filtered.
Invariant 5: Soft delete (deleted_at tombstone) + audit, in one operation.
"""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from agent.store.audit import create_audit_entry


async def run(state: dict, config: RunnableConfig) -> dict:
    """Delete pre-resolved targets and write audit entries."""
    report_store = config["configurable"].get("report_store")
    audit_store = config["configurable"].get("audit_store")
    targets = state.get("delete_targets", [])

    if not targets or not report_store:
        return {"final_answer": "No reports to delete."}

    deleted_ids = []
    for target in targets:
        ok = await report_store.soft_delete(target.id)
        if ok:
            deleted_ids.append(target.id)

    if audit_store:
        entry = create_audit_entry(
            actor=state.get("user_id", "default"),
            action="soft_delete",
            target_ids=deleted_ids,
            filter_text=state.get("standalone_question", ""),
            risk_tier=state.get("delete_risk_tier", "low"),
            trace_id=state.get("trace_id", ""),
        )
        await audit_store.append(entry)

    titles = [t.title for t in targets if t.id in deleted_ids]
    msg = f"Deleted {len(deleted_ids)} report(s): {', '.join(titles)}"
    return {"final_answer": msg}
