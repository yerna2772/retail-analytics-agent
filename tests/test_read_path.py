"""Step 2 acceptance: end-to-end read path through FakeLLM + FakeBigQuery."""

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
async def test_revenue_by_month():
    """Full read path: triage through analyst and guardrail_out."""
    graph = build_graph(MemorySaver())

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="Revenue by month in 2023?")]},
        config=_config("read-001"),
    )

    assert result["intent"] == "analysis"
    assert result.get("final_answer")
    assert len(result.get("query_results", [])) > 0
    assert result["query_results"][0].row_count > 0
    assert result.get("llm_call_count", 0) <= 8


@pytest.mark.asyncio
async def test_follow_up_resolves_history():
    """Follow-up 'and in Texas?' resolves against prior context."""
    graph = build_graph(MemorySaver())
    config = _config("read-002")

    r1 = await graph.ainvoke(
        {"messages": [HumanMessage(content="Revenue by month in 2023?")]},
        config=config,
    )
    assert r1["intent"] == "analysis"
    assert r1.get("final_answer")

    r2 = await graph.ainvoke(
        {"messages": [HumanMessage(content="and in Texas?")]},
        config=config,
    )
    assert r2["intent"] == "analysis"
    assert r2.get("final_answer")
    standalone = r2.get("standalone_question", "")
    assert "texas" in standalone.lower() or "Texas" in standalone


@pytest.mark.asyncio
async def test_metadata_intent():
    """Metadata questions skip the SQL pipeline entirely."""
    graph = build_graph(MemorySaver())

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="What tables do you have?")]},
        config=_config("read-003"),
    )

    assert result["intent"] == "metadata"
    assert "order_items" in result["final_answer"]
    assert "users" in result["final_answer"]


@pytest.mark.asyncio
async def test_refuse_intent():
    """Off-topic questions are refused."""
    graph = build_graph(MemorySaver())

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="Write me a poem about cats")]},
        config=_config("read-004"),
    )

    assert result["intent"] == "refuse"
    assert result.get("final_answer")


@pytest.mark.asyncio
async def test_sql_validation_blocks_pii():
    """SQL that touches PII columns is caught by the validator and repaired or degraded."""
    from agent.llm.gateway import FakeLLM

    pii_sql = "SELECT email FROM users LIMIT 10"
    llm = FakeLLM(
        responses=[
            '{"intent": "analysis", "standalone_question": "show emails",'
            ' "is_safe": true, "refusal_reason": null}',
            pii_sql,
            pii_sql,
            pii_sql,
            pii_sql,
        ]
    )

    graph = build_graph(MemorySaver())
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="show me customer emails")]},
        config=_config("read-005", llm=llm),
    )

    assert result.get("final_answer")
    results = result.get("query_results", [])
    for qr in results:
        assert "email" not in qr.sql.lower()


@pytest.mark.asyncio
async def test_budget_limits_respected():
    """LLM call count stays within budget."""
    graph = build_graph(MemorySaver())

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="Revenue by month in 2023?")]},
        config=_config("read-006"),
    )

    assert result.get("llm_call_count", 0) <= 8
    assert result.get("bytes_scanned", 0) <= 15 * 1024 * 1024 * 1024


@pytest.mark.asyncio
async def test_pii_scrubbed_from_output():
    """Even if an email slips into the answer text, guardrail_out removes it."""
    from agent.llm.gateway import FakeLLM

    llm = FakeLLM(
        responses=[
            '{"intent": "analysis", "standalone_question": "count orders",'
            ' "is_safe": true, "refusal_reason": null}',
            "SELECT COUNT(*) AS total FROM orders LIMIT 1",
            "The answer is 6 orders total. Contact alice@example.com for details.",
        ]
    )

    graph = build_graph(MemorySaver())
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="How many orders?")]},
        config=_config("read-007", llm=llm),
    )

    assert "@example.com" not in result.get("final_answer", "")
