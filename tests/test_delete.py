"""Step 5 acceptance: destructive ops with confirmation and audit."""

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from agent.data.bigquery import FakeBigQuery
from agent.graph import build_graph
from agent.llm.gateway import FakeLLM
from agent.store.audit import FakeAuditStore
from agent.store.reports import FakeReportStore, Report


def _config(thread_id, llm=None, bq=None, report_store=None, audit_store=None):
    return {
        "configurable": {
            "thread_id": thread_id,
            "llm": llm or FakeLLM(),
            "bq": bq or FakeBigQuery(),
            "report_store": report_store or FakeReportStore(),
            "audit_store": audit_store or FakeAuditStore(),
        }
    }


async def _seed_report(store, title="Test Report"):
    report = Report(
        id="rpt-001",
        owner_id="default",
        thread_id="seed-thread",
        title=title,
        body="Report body",
        action_items=["Action 1"],
        created_at="2023-01-01T00:00:00Z",
    )
    await store.save(report)
    return report


@pytest.mark.asyncio
async def test_resolve_filters_by_owner():
    """Resolve applies ownership filter in code, not by model."""
    store = FakeReportStore()
    await _seed_report(store, "Revenue Report")

    other_report = Report(
        id="rpt-other",
        owner_id="other-user",
        thread_id="other",
        title="Other Report",
        body="Body",
        action_items=[],
        created_at="2023-01-01T00:00:00Z",
    )
    await store.save(other_report)

    graph = build_graph(MemorySaver())
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="Delete the revenue report")]},
        config=_config("del-001", report_store=store),
    )

    targets = result.get("delete_targets", [])
    for t in targets:
        assert t.id != "rpt-other"


@pytest.mark.asyncio
async def test_soft_delete_with_audit():
    """Deletion sets deleted_at and writes an audit entry."""
    store = FakeReportStore()
    audit = FakeAuditStore()
    await _seed_report(store)

    graph = build_graph(MemorySaver())
    await graph.ainvoke(
        {"messages": [HumanMessage(content="Delete the test report")]},
        config=_config("del-002", report_store=store, audit_store=audit),
    )

    remaining = await store.list_reports("default")
    assert len(remaining) == 0

    raw = store._reports.get("rpt-001")
    assert raw is not None
    assert raw.deleted_at is not None

    assert len(audit.entries) >= 1
    assert "rpt-001" in audit.entries[0].target_ids


@pytest.mark.asyncio
async def test_ids_resolved_before_confirmation():
    """Invariant 4: IDs are resolved before confirmation, not re-filtered."""
    store = FakeReportStore()
    await _seed_report(store)

    graph = build_graph(MemorySaver())
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="Delete the test report")]},
        config=_config("del-003", report_store=store),
    )

    targets = result.get("delete_targets", [])
    assert len(targets) >= 1
    assert targets[0].id == "rpt-001"


@pytest.mark.asyncio
async def test_risk_tier_medium_for_multiple():
    """Multiple matches yield medium risk tier."""
    store = FakeReportStore()
    for i in range(3):
        r = Report(
            id=f"rpt-{i}",
            owner_id="default",
            thread_id="seed",
            title=f"Revenue Report {i}",
            body="Body",
            action_items=[],
            created_at="2023-01-01T00:00:00Z",
        )
        await store.save(r)

    graph = build_graph(MemorySaver())
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="Delete revenue reports")]},
        config=_config("del-004", report_store=store),
    )

    assert result.get("delete_risk_tier") in ("medium", "high")
