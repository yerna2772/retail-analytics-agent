from __future__ import annotations

import random
import time
from enum import Enum


class _State(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    pass


class CircuitBreaker:
    """Open after `threshold` failures in `window_s`. Half-open probe every `probe_s`."""

    def __init__(
        self,
        name: str = "default",
        threshold: int = 5,
        window_s: float = 60.0,
        probe_s: float = 30.0,
        base_backoff_s: float = 1.0,
        max_backoff_s: float = 30.0,
    ) -> None:
        self.name = name
        self._threshold = threshold
        self._window_s = window_s
        self._probe_s = probe_s
        self._base_backoff_s = base_backoff_s
        self._max_backoff_s = max_backoff_s

        self._state = _State.CLOSED
        self._failures: list[float] = []
        self._opened_at: float = 0.0
        self._consecutive_failures: int = 0

    @property
    def state(self) -> str:
        return self._state.value

    def check(self) -> None:
        if self._state == _State.CLOSED:
            return
        if self._state == _State.OPEN:
            if time.monotonic() - self._opened_at >= self._probe_s:
                self._state = _State.HALF_OPEN
                return
            raise CircuitOpenError(f"Circuit '{self.name}' is open")
        # HALF_OPEN — allow one probe call through

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._failures.clear()
        if self._state in (_State.HALF_OPEN, _State.OPEN):
            self._state = _State.CLOSED

    def record_failure(self) -> None:
        now = time.monotonic()
        self._consecutive_failures += 1
        self._failures = [t for t in self._failures if now - t < self._window_s]
        self._failures.append(now)
        if len(self._failures) >= self._threshold:
            self._state = _State.OPEN
            self._opened_at = now

    def backoff_delay(self) -> float:
        delay = self._base_backoff_s * (2 ** (self._consecutive_failures - 1))
        delay = min(delay, self._max_backoff_s)
        return delay * (0.5 + random.random() * 0.5)  # noqa: S311
