"""Step 8 acceptance: persona hot-reload via TTL-based cache."""

import time

from agent.prompts.registry import (
    _TTL_SECONDS,
    _timestamps,
    get_prompt_owner,
    invalidate,
    load_prompt,
)


def test_persona_loads():
    """Persona prompt loads from YAML."""
    invalidate("persona")
    text = load_prompt("persona")
    assert "retail analyst" in text.lower()


def test_persona_is_business_owned():
    """Persona prompt is owned by business, not dev."""
    invalidate("persona")
    assert get_prompt_owner("persona") == "business"


def test_sql_generator_is_dev_owned():
    """SQL generator prompt is dev-owned."""
    invalidate("sql_generator")
    assert get_prompt_owner("sql_generator") == "dev"


def test_cache_serves_within_ttl():
    """Prompt is served from cache within TTL window."""
    invalidate("persona")
    t1 = load_prompt("persona")
    t2 = load_prompt("persona")
    assert t1 == t2


def test_cache_expires_after_ttl(monkeypatch):
    """Cache entry expires after TTL, triggering reload."""
    invalidate("persona")
    load_prompt("persona")

    _timestamps["persona"] = time.monotonic() - _TTL_SECONDS - 1

    text = load_prompt("persona")
    assert "retail analyst" in text.lower()


def test_bad_yaml_falls_back(tmp_path, monkeypatch):
    """Bad YAML serves last-known-good instead of crashing."""
    invalidate("persona")
    load_prompt("persona")

    bad_path = tmp_path / "persona.yaml"
    bad_path.write_text("{{invalid yaml: [")

    import agent.prompts.registry as reg

    orig_dir = reg._PROMPTS_DIR
    monkeypatch.setattr(reg, "_PROMPTS_DIR", tmp_path)

    _timestamps["persona"] = 0

    text = load_prompt("persona")
    assert "retail analyst" in text.lower()

    monkeypatch.setattr(reg, "_PROMPTS_DIR", orig_dir)
    invalidate("persona")
