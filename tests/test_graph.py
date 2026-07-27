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
async def test_graph_compiles_and_round_trips():
    """Step 0 acceptance: graph compiles, round-trips through stubs, no network."""
    checkpointer = MemorySaver()
    graph = build_graph(checkpointer)

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="What data do you have?")]},
        config=_config("test-001"),
    )

    assert "final_answer" in result
    assert isinstance(result["final_answer"], str)
    assert len(result["final_answer"]) > 0


@pytest.mark.asyncio
async def test_graph_multi_turn():
    """Multiple turns in the same thread accumulate messages."""
    checkpointer = MemorySaver()
    graph = build_graph(checkpointer)
    config = _config("test-002")

    r1 = await graph.ainvoke(
        {"messages": [HumanMessage(content="Hello")]},
        config=config,
    )
    assert "final_answer" in r1

    r2 = await graph.ainvoke(
        {"messages": [HumanMessage(content="What can you do?")]},
        config=config,
    )
    assert "final_answer" in r2
    assert len(r2["messages"]) > len(r1["messages"])


@pytest.mark.asyncio
async def test_guardrail_out_scrubs_pii():
    """Output guardrail scrubs PII even in stub mode."""
    checkpointer = MemorySaver()
    graph = build_graph(checkpointer)

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="test")]},
        config=_config("test-003"),
    )

    assert "final_answer" in result
    assert "@example.com" not in result["final_answer"]
