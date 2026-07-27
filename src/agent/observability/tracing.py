from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

_langfuse = None


def _get_langfuse() -> Any:
    global _langfuse
    if _langfuse is not None:
        return _langfuse
    try:
        from langfuse import Langfuse

        _langfuse = Langfuse()
        _langfuse.auth_check()
        logger.info("Langfuse tracing enabled")
    except Exception:
        logger.info("Langfuse not configured — tracing disabled")
        _langfuse = False  # type: ignore[assignment]
    return _langfuse


def traced_node(name: str) -> Callable:
    """Decorator stamping node name, latency, and model info onto a Langfuse span."""

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(state: dict, **kwargs: Any) -> dict:
            lf = _get_langfuse()
            trace_id = state.get("trace_id", "")
            start = time.perf_counter()

            if lf and lf is not False:
                trace = lf.trace(id=trace_id, name=f"turn-{state.get('turn_id', '')}")
                span = trace.span(name=name)
            else:
                span = None

            try:
                result = await fn(state, **kwargs)
                elapsed = time.perf_counter() - start
                if span:
                    span.end(
                        metadata={"latency_s": round(elapsed, 3), "node": name},
                        level="DEFAULT",
                    )
                return result
            except Exception as exc:
                elapsed = time.perf_counter() - start
                if span:
                    span.end(
                        metadata={"latency_s": round(elapsed, 3), "node": name},
                        level="ERROR",
                        status_message=str(exc),
                    )
                raise

        return wrapper

    return decorator
