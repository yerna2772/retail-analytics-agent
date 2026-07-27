"""Step 3 acceptance: multi-step causal queries produce multi-query answers."""

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from agent.data.bigquery import FakeBigQuery
from agent.graph import build_graph
from agent.llm.gateway import FakeLLM


def _config(thread_id: str, llm=None, bq=None):
    return {
        "configurable": {
            "thread_id": thread_id,
            "llm": llm or FakeLLM(),
            "bq": bq or FakeBigQuery(),
        }
    }


@pytest.mark.asyncio
async def test_causal_texas_vs_california():
    """'Why are Texas users underspending vs California?' produces multiple queries."""
    graph = build_graph(MemorySaver())

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content=("Why are Texas users underspending vs California?"))]},
        config=_config("replan-001"),
    )

    assert result["intent"] == "analysis"
    assert result.get("final_answer")

    qr = result.get("query_results", [])
    assert len(qr) >= 2, f"Expected multi-query, got {len(qr)}"

    plan = result.get("plan", [])
    assert len(plan) >= 2, f"Expected multi-step plan, got {len(plan)}"


@pytest.mark.asyncio
async def test_replan_bounded():
    """Replanning is bounded at 2 replans per turn."""
    graph = build_graph(MemorySaver())

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content=("Why are Texas users underspending vs California?"))]},
        config=_config("replan-002"),
    )

    assert result.get("replan_count", 0) <= 2
    assert result.get("llm_call_count", 0) <= 8


@pytest.mark.asyncio
async def test_simple_query_still_works():
    """Simple questions still work with the new planner."""
    graph = build_graph(MemorySaver())

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="Revenue by month in 2023?")]},
        config=_config("replan-003"),
    )

    assert result["intent"] == "analysis"
    assert result.get("final_answer")
    assert len(result.get("query_results", [])) >= 1
