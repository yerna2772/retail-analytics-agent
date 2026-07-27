from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parents[3] / "prompts"

_cache: dict[str, dict[str, Any]] = {}


def load_prompt(name: str) -> str:
    """Load a prompt template from prompts/{name}.yaml and return the template string."""
    if name in _cache:
        return _cache[name]["template"]

    path = _PROMPTS_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")

    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        if name in _cache:
            logger.error("Bad YAML in %s, serving last-known-good: %s", path, exc)
            return _cache[name]["template"]
        raise

    _cache[name] = data
    return data["template"]


def get_prompt_version(name: str) -> str:
    """Return the version string for a loaded prompt, or 'unknown'."""
    if name not in _cache:
        load_prompt(name)
    return _cache.get(name, {}).get("version", "unknown")


def invalidate(name: str | None = None) -> None:
    """Clear cache for one prompt or all prompts."""
    if name:
        _cache.pop(name, None)
    else:
        _cache.clear()
