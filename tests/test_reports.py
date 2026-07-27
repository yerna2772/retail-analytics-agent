"""Step 4 acceptance: report creation with findings and action items."""

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from agent.data.bigquery import FakeBigQuery
from agent.graph import build_graph
from agent.llm.gateway import FakeLLM
from agent.store.reports import FakeReportStore


def _config(thread_id, llm=None, bq=None, report_store=None):
    return {
        "configurable": {
            "thread_id": thread_id,
            "llm": llm or FakeLLM(),
            "bq": bq or FakeBigQuery(),
            "report_store": report_store or FakeReportStore(),
        }
    }


@pytest.mark.asyncio
async def test_report_create_from_fresh_analysis():
    """'Create a report' after analysis produces a saved report."""
    graph = build_graph(MemorySaver())
    store = FakeReportStore()
    config = _config("report-001", report_store=store)

    r1 = await graph.ainvoke(
        {"messages": [HumanMessage(content="Revenue by month in 2023?")]},
        config=config,
    )
    assert r1.get("final_answer")

    r2 = await graph.ainvoke(
        {"messages": [HumanMessage(content="Create a Q1 report with action items")]},
        config=config,
    )
    assert r2.get("intent") == "report_create"
    assert r2.get("saved_report_id")
    assert r2.get("final_answer")


@pytest.mark.asyncio
async def test_report_has_action_items():
    """Report contains action items — a required field."""
    graph = build_graph(MemorySaver())
    store = FakeReportStore()
    config = _config("report-002", report_store=store)

    await graph.ainvoke(
        {"messages": [HumanMessage(content="Revenue by month in 2023?")]},
        config=config,
    )

    r2 = await graph.ainvoke(
        {"messages": [HumanMessage(content="Generate a report with insights and action items")]},
        config=config,
    )
    assert r2.get("action_items")
    assert len(r2["action_items"]) >= 1


@pytest.mark.asyncio
async def test_report_store_integration():
    """FakeReportStore saves and lists reports."""
    store = FakeReportStore()
    graph = build_graph(MemorySaver())
    config = _config("report-003", report_store=store)

    await graph.ainvoke(
        {"messages": [HumanMessage(content="Revenue by month in 2023?")]},
        config=config,
    )

    await graph.ainvoke(
        {"messages": [HumanMessage(content="Save a report from that analysis")]},
        config=config,
    )

    reports = await store.list_reports("default")
    assert len(reports) >= 1
    assert reports[0].body
    assert reports[0].title
