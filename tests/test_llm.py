import pytest

from agent.llm.circuit import CircuitBreaker, CircuitOpenError
from agent.llm.gateway import FakeLLM


@pytest.mark.asyncio
async def test_fake_llm_echoes():
    llm = FakeLLM()
    result = await llm.generate("hello world")
    assert "hello world" in result


@pytest.mark.asyncio
async def test_fake_llm_scripted():
    llm = FakeLLM(responses=["answer1", "answer2"])
    assert await llm.generate("q1") == "answer1"
    assert await llm.generate("q2") == "answer2"
    result = await llm.generate("q3")
    assert "q3" in result


def test_circuit_breaker_opens_after_threshold():
    cb = CircuitBreaker(threshold=3, window_s=60)
    for _ in range(3):
        cb.record_failure()
    assert cb.state == "open"
    with pytest.raises(CircuitOpenError):
        cb.check()


def test_circuit_breaker_stays_closed_below_threshold():
    cb = CircuitBreaker(threshold=5, window_s=60)
    for _ in range(4):
        cb.record_failure()
    assert cb.state == "closed"
    cb.check()


def test_circuit_breaker_resets_on_success():
    cb = CircuitBreaker(threshold=3, window_s=60)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    cb.record_failure()
    cb.record_failure()
    assert cb.state == "closed"
