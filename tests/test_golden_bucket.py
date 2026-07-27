"""Step 7 acceptance: golden bucket retrieval improves SQL generation."""

import pytest

from agent.data.golden_bucket import invalidate_cache, retrieve


@pytest.fixture(autouse=True)
def _clear_cache():
    invalidate_cache()
    yield
    invalidate_cache()


def test_retrieves_revenue_trio():
    """'Monthly revenue' question retrieves the revenue trio."""
    results = retrieve("What is the monthly revenue?")
    assert len(results) >= 1
    ids = [t.id for t in results]
    assert "trio-revenue-monthly" in ids


def test_retrieves_top_customers():
    """'Top spenders' retrieves the top customers trio."""
    results = retrieve("Who are the top spenders?")
    assert len(results) >= 1
    ids = [t.id for t in results]
    assert "trio-top-customers" in ids


def test_retrieves_category_trio():
    """'Category revenue' retrieves the category trio."""
    results = retrieve("Revenue by product category")
    assert len(results) >= 1
    ids = [t.id for t in results]
    assert "trio-category-revenue" in ids


def test_top_k_limit():
    """Retrieval returns at most top_k results."""
    results = retrieve("revenue", top_k=2)
    assert len(results) <= 2


def test_retrieval_score_set():
    """Retrieved trios have a retrieval_score."""
    results = retrieve("monthly revenue")
    for t in results:
        assert t.retrieval_score is not None
        assert t.retrieval_score > 0


def test_irrelevant_query_low_scores():
    """A query unrelated to any trio gets low or no matches."""
    results = retrieve("asdfghjkl random nonsense")
    assert len(results) == 0 or all(t.retrieval_score < 0.1 for t in results)


def test_all_trios_load():
    """All seed trios load without error."""
    from agent.data.golden_bucket import _load_trios

    trios = _load_trios()
    assert len(trios) >= 10
