from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parents[3] / "prompts"

_cache: dict[str, dict[str, Any]] = {}


def _load(name: str) -> dict[str, Any]:
    if name in _cache:
        return _cache[name]

    path = _PROMPTS_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")

    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        if name in _cache:
            logger.error("Bad YAML in %s, serving last-known-good: %s", path, exc)
            return _cache[name]
        raise

    _cache[name] = data
    return data


def load_prompt(name: str) -> str:
    """Load a prompt template string from prompts/{name}.yaml."""
    return _load(name)["template"]


def render_prompt(name: str, **kwargs: str) -> str:
    """Load prompt and substitute {key} placeholders."""
    template = load_prompt(name)
    for key, value in kwargs.items():
        template = template.replace(f"{{{key}}}", str(value))
    return template


def get_prompt_version(name: str) -> str:
    return _load(name).get("version", "unknown")


def invalidate(name: str | None = None) -> None:
    if name:
        _cache.pop(name, None)
    else:
        _cache.clear()
