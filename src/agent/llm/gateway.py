from __future__ import annotations

import json
import logging
import re
from typing import Protocol, runtime_checkable

import httpx

from agent.config import settings
from agent.llm.circuit import CircuitBreaker

logger = logging.getLogger(__name__)


@runtime_checkable
class LLMGateway(Protocol):
    async def generate(self, prompt: str, *, system: str = "") -> str: ...


# ---------------------------------------------------------------------------
# JSON extraction helper
# ---------------------------------------------------------------------------


def extract_json(text: str) -> str:
    """Pull a JSON object or array out of an LLM response."""
    text = text.strip()
    if text.startswith("{") or text.startswith("["):
        return text
    m = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r"[\[{].*[\]}]", text, re.DOTALL)
    if m:
        return m.group(0)
    return text


def clean_sql(text: str) -> str:
    """Strip markdown code fences from an LLM SQL response."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


# ---------------------------------------------------------------------------
# Real gateways
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# FakeLLM — scripted responses for tests, keyword-aware for demo
# ---------------------------------------------------------------------------


class FakeLLM:
    """Scripted or keyword-aware responses. No network calls."""

    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses = list(responses) if responses else []
        self._call_count = 0

    @property
    def call_count(self) -> int:
        return self._call_count

    async def generate(self, prompt: str, *, system: str = "") -> str:
        self._call_count += 1
        if self._responses:
            return self._responses.pop(0)
        return self._demo_response(prompt, system)

    # -- demo-mode helpers --------------------------------------------------

    def _demo_response(self, prompt: str, system: str) -> str:
        combined = (system + " " + prompt).lower()
        if "intent" in combined and ("classif" in combined or "triage" in combined):
            return self._fake_triage(prompt)
        if "break this into" in combined and "sql steps" in combined:
            return self._fake_plan(prompt)
        if "sql" in combined and (
            "generate" in combined or "expert" in combined or "query" in combined
        ):
            return self._fake_sql(prompt)
        if "needs_more" in combined or "need additional queries" in combined:
            return self._fake_replan(prompt)
        if "analyst" in combined or "findings" in combined or "interpret" in combined:
            return self._fake_analysis(prompt)
        return f"[FakeLLM] Echo: {prompt[:200]}"

    def _fake_triage(self, prompt: str) -> str:
        prompt_lower = prompt.lower()
        latest = prompt
        for marker in ["latest message:", "latest:"]:
            if marker in prompt_lower:
                idx = prompt_lower.index(marker)
                latest = prompt[idx + len(marker) :].strip()
                break

        ll = latest.lower()
        if any(
            kw in ll for kw in ["what data", "what kind", "what can", "schema", "tables", "help"]
        ):
            intent = "metadata"
        elif any(kw in ll for kw in ["delete", "remove"]):
            intent = "report_delete"
        elif any(
            kw in ll
            for kw in ["create a report", "save a report", "turn that into", "generate a report"]
        ):
            intent = "report_create"
        elif any(
            kw in ll for kw in ["poem", "recipe", "weather", "joke", "opinion", "system prompt"]
        ):
            return json.dumps(
                {
                    "intent": "refuse",
                    "standalone_question": latest,
                    "is_safe": False,
                    "refusal_reason": "This request is outside the scope of retail analytics.",
                }
            )
        else:
            intent = "analysis"

        return json.dumps(
            {
                "intent": intent,
                "standalone_question": latest,
                "is_safe": True,
                "refusal_reason": None,
            }
        )

    def _fake_plan(self, prompt: str) -> str:
        p = prompt.lower()
        if "why" in p and "vs" in p or ("why" in p and "compared" in p):
            states = []
            for s in [
                "texas",
                "california",
                "new york",
                "florida",
            ]:
                if s in p:
                    states.append(s.title())
            if len(states) < 2:
                states = ["Texas", "California"]
            return json.dumps(
                [
                    {
                        "index": 0,
                        "question": (f"Average spend per user in {states[0]}"),
                        "depends_on": [],
                    },
                    {
                        "index": 1,
                        "question": (f"Average spend per user in {states[1]}"),
                        "depends_on": [],
                    },
                    {
                        "index": 2,
                        "question": (f"Category breakdown of spend in {states[0]} vs {states[1]}"),
                        "depends_on": [0, 1],
                    },
                ]
            )
        if "why" in p and ("spike" in p or "increase" in p or "change" in p):
            return json.dumps(
                [
                    {
                        "index": 0,
                        "question": "Monthly trend of the metric",
                        "depends_on": [],
                    },
                    {
                        "index": 1,
                        "question": "Breakdown by category for peak period",
                        "depends_on": [0],
                    },
                ]
            )
        return json.dumps(
            [
                {
                    "index": 0,
                    "question": prompt.split("Question:")[-1].strip()
                    if "Question:" in prompt
                    else prompt[-200:],
                    "depends_on": [],
                }
            ]
        )

    def _fake_replan(self, prompt: str) -> str:
        p = prompt.lower()
        if "category" not in p and ("vs" in p or "compared" in p or "why" in p):
            return json.dumps(
                {
                    "needs_more": True,
                    "steps": [
                        {
                            "index": 99,
                            "question": "Category breakdown of spend",
                            "depends_on": [],
                        }
                    ],
                    "reason": "Need category detail to identify driver",
                }
            )
        return json.dumps(
            {
                "needs_more": False,
                "steps": [],
                "reason": "Sufficient data to answer",
            }
        )

    def _fake_sql(self, prompt: str) -> str:
        p = prompt.lower()
        if "average spend" in p and "texas" in p:
            return (
                "SELECT AVG(oi.sale_price) AS avg_spend "
                "FROM order_items oi "
                "JOIN users u ON oi.user_id = u.id "
                "WHERE u.state = 'Texas' "
                "AND oi.status NOT IN ('Cancelled', 'Returned') LIMIT 1"
            )
        if "average spend" in p and "california" in p:
            return (
                "SELECT AVG(oi.sale_price) AS avg_spend "
                "FROM order_items oi "
                "JOIN users u ON oi.user_id = u.id "
                "WHERE u.state = 'California' "
                "AND oi.status NOT IN ('Cancelled', 'Returned') LIMIT 1"
            )
        if "category" in p and "breakdown" in p:
            return (
                "SELECT p.category, u.state, "
                "SUM(oi.sale_price) AS revenue "
                "FROM order_items oi "
                "JOIN users u ON oi.user_id = u.id "
                "JOIN products p ON oi.product_id = p.id "
                "WHERE oi.status NOT IN ('Cancelled', 'Returned') "
                "GROUP BY p.category, u.state "
                "ORDER BY revenue DESC LIMIT 20"
            )
        if "revenue" in p and "month" in p:
            return (
                "SELECT DATE_TRUNC(oi.created_at, MONTH) AS month, "
                "SUM(oi.sale_price) AS revenue "
                "FROM order_items oi "
                "WHERE oi.status NOT IN ('Cancelled', 'Returned') "
                "GROUP BY month ORDER BY month LIMIT 36"
            )
        if "top" in p and "customer" in p:
            return (
                "SELECT oi.user_id, SUM(oi.sale_price) AS total_spend "
                "FROM order_items oi GROUP BY oi.user_id "
                "ORDER BY total_spend DESC LIMIT 10"
            )
        if "category" in p and ("revenue" in p or "sales" in p):
            return (
                "SELECT p.category, SUM(oi.sale_price) AS revenue "
                "FROM products p JOIN order_items oi ON p.id = oi.product_id "
                "GROUP BY p.category ORDER BY revenue DESC LIMIT 20"
            )
        if "status" in p:
            return "SELECT status, COUNT(*) AS cnt FROM orders GROUP BY status LIMIT 20"
        return "SELECT COUNT(*) AS total FROM orders LIMIT 1"

    def _fake_analysis(self, prompt: str) -> str:
        return (
            "Based on the data provided, here are the key findings:\n\n"
            "The results show the requested metrics across the analysed period. "
            "[Demo mode — connect a real LLM for detailed analysis.]"
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


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
