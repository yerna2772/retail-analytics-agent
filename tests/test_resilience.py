"""Step 6 acceptance: injected failures produce sane responses."""

import json

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from agent.data.bigquery import FakeBigQuery
from agent.graph import build_graph
from agent.llm.gateway import FakeLLM


def _config(thread_id, llm=None, bq=None):
    return {
        "configurable": {
            "thread_id": thread_id,
            "llm": llm or FakeLLM(),
            "bq": bq or FakeBigQuery(),
        }
    }


@pytest.mark.asyncio
async def test_syntax_error_repaired():
    """A syntax error in generated SQL triggers repair and eventual answer."""
    triage = json.dumps(
        {
            "intent": "analysis",
            "standalone_question": "count orders",
            "is_safe": True,
            "refusal_reason": None,
        }
    )
    plan = json.dumps([{"index": 0, "question": "count orders", "depends_on": []}])
    bad_sql = "SELEC COUNT(*) FROM orders"
    good_sql = "SELECT COUNT(*) AS total FROM orders LIMIT 1"
    replan = json.dumps({"needs_more": False, "steps": [], "reason": "done"})

    llm = FakeLLM(
        responses=[
            triage,
            plan,
            bad_sql,
            good_sql,
            replan,
            "The total number of orders is 6.",
        ]
    )

    graph = build_graph(MemorySaver())
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="How many orders?")]},
        config=_config("resil-001", llm=llm),
    )

    assert result.get("final_answer")
    assert result.get("repair_count", 0) >= 1


@pytest.mark.asyncio
async def test_persistent_failure_degrades():
    """3 consecutive validation failures → degrade, not crash."""
    triage = json.dumps(
        {
            "intent": "analysis",
            "standalone_question": "show data",
            "is_safe": True,
            "refusal_reason": None,
        }
    )
    plan = json.dumps([{"index": 0, "question": "show data", "depends_on": []}])
    bad = "SELECT * FROM orders"

    llm = FakeLLM(responses=[triage, plan, bad, bad, bad, bad])

    graph = build_graph(MemorySaver())
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="Show me data")]},
        config=_config("resil-002", llm=llm),
    )

    assert result.get("final_answer")
    assert result.get("degradation_level", 0) >= 1


@pytest.mark.asyncio
async def test_budget_exhaustion_degrades():
    """Hitting the LLM call budget produces a degraded answer, not a crash."""
    triage = json.dumps(
        {
            "intent": "analysis",
            "standalone_question": "data",
            "is_safe": True,
            "refusal_reason": None,
        }
    )
    plan = json.dumps([{"index": 0, "question": "data", "depends_on": []}])

    responses = [triage, plan]
    for _ in range(10):
        responses.append("SELECT COUNT(*) AS total FROM orders LIMIT 1")
    llm = FakeLLM(responses=responses)

    graph = build_graph(MemorySaver())
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="Lots of data")]},
        config=_config("resil-003", llm=llm),
    )

    assert result.get("final_answer")
    assert result.get("llm_call_count", 0) <= 8


@pytest.mark.asyncio
async def test_cli_never_crashes():
    """Invariant 8: every path produces a final_answer, never an exception."""
    graph = build_graph(MemorySaver())

    for msg in [
        "Revenue by month",
        "Write me a poem",
        "What tables do you have?",
        "Delete all reports",
    ]:
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=msg)]},
            config=_config(f"crash-{msg[:5]}"),
        )
        assert "final_answer" in result
        assert isinstance(result["final_answer"], str)
