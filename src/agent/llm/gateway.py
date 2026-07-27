from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

import httpx

from agent.config import settings
from agent.llm.circuit import CircuitBreaker

logger = logging.getLogger(__name__)


@runtime_checkable
class LLMGateway(Protocol):
    async def generate(self, prompt: str, *, system: str = "") -> str: ...


class GeminiGateway:
    def __init__(self) -> None:
        self._api_key = settings.gemini_api_key
        self._model = "gemini-2.5-flash"
        self._circuit = CircuitBreaker(name="gemini")

    async def generate(self, prompt: str, *, system: str = "") -> str:
        self._circuit.check()
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}"
            f":generateContent?key={self._api_key}"
        )
        contents = []
        if system:
            contents.append({"role": "user", "parts": [{"text": system}]})
            contents.append({"role": "model", "parts": [{"text": "Understood."}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(url, json={"contents": contents})
                resp.raise_for_status()
            self._circuit.record_success()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as exc:
            self._circuit.record_failure()
            raise RuntimeError(f"Gemini call failed: {exc}") from exc


class OpenRouterGateway:
    def __init__(self) -> None:
        self._api_key = settings.openrouter_api_key
        self._model = "google/gemini-2.5-flash"
        self._circuit = CircuitBreaker(name="openrouter")

    async def generate(self, prompt: str, *, system: str = "") -> str:
        self._circuit.check()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={"model": self._model, "messages": messages},
                )
                resp.raise_for_status()
            self._circuit.record_success()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as exc:
            self._circuit.record_failure()
            raise RuntimeError(f"OpenRouter call failed: {exc}") from exc


class FakeLLM:
    """Returns scripted responses. No network calls."""

    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses = list(responses) if responses else []
        self._call_count = 0

    async def generate(self, prompt: str, *, system: str = "") -> str:
        self._call_count += 1
        if self._responses:
            return self._responses.pop(0)
        return f"[FakeLLM] Echo: {prompt[:200]}"


def get_gateway(*, fake: bool = False) -> LLMGateway:
    if fake:
        return FakeLLM()
    if settings.gemini_api_key:
        logger.info("Using Gemini gateway")
        return GeminiGateway()
    if settings.openrouter_api_key:
        logger.info("Using OpenRouter gateway (fallback)")
        return OpenRouterGateway()
    logger.warning("No LLM API keys configured — falling back to FakeLLM")
    return FakeLLM()
