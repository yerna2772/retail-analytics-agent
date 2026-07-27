"""Golden Bucket: seed trios with keyword-based retrieval.

At this corpus size (12-15 trios), cosine similarity over TF-IDF
is sufficient. No pgvector, no embedding model, no reranking.
"""

from __future__ import annotations

import json
import logging
import math
from collections import Counter
from pathlib import Path

from agent.state import Trio

logger = logging.getLogger(__name__)

_TRIOS_DIR = Path(__file__).parents[3] / "golden" / "trios"
_cache: list[Trio] | None = None


def _load_trios() -> list[Trio]:
    global _cache
    if _cache is not None:
        return _cache

    trios = []
    if not _TRIOS_DIR.exists():
        logger.warning("Golden trios directory not found: %s", _TRIOS_DIR)
        return trios

    for path in sorted(_TRIOS_DIR.glob("*.json")):
        try:
            with open(path) as f:
                data = json.load(f)
            trios.append(Trio(**data))
        except Exception as exc:
            logger.warning("Failed to load trio %s: %s", path.name, exc)

    logger.debug("Loaded %d seed trios", len(trios))
    _cache = trios
    return trios


def _tokenize(text: str) -> list[str]:
    return [w.lower().strip("?.,!") for w in text.split() if len(w) > 2]


def _tf(tokens: list[str]) -> dict[str, float]:
    counts = Counter(tokens)
    total = len(tokens)
    return {t: c / total for t, c in counts.items()} if total else {}


def _idf(corpus_tokens: list[list[str]]) -> dict[str, float]:
    n = len(corpus_tokens)
    df: Counter[str] = Counter()
    for doc in corpus_tokens:
        df.update(set(doc))
    return {t: math.log((n + 1) / (count + 1)) + 1 for t, count in df.items()}


def _cosine_sim(a: dict[str, float], b: dict[str, float]) -> float:
    common = set(a) & set(b)
    if not common:
        return 0.0
    dot = sum(a[k] * b[k] for k in common)
    mag_a = math.sqrt(sum(v * v for v in a.values()))
    mag_b = math.sqrt(sum(v * v for v in b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def retrieve(question: str, top_k: int = 3) -> list[Trio]:
    """Find the top_k most relevant trios for a question."""
    trios = _load_trios()
    if not trios:
        return []

    q_tokens = _tokenize(question)

    corpus_tokens = []
    for trio in trios:
        all_text = " ".join(trio.question_variants) + " " + trio.report
        corpus_tokens.append(_tokenize(all_text))

    idf = _idf(corpus_tokens + [q_tokens])

    q_tf = _tf(q_tokens)
    q_tfidf = {t: q_tf[t] * idf.get(t, 1.0) for t in q_tf}

    scored = []
    for i, trio in enumerate(trios):
        doc_tf = _tf(corpus_tokens[i])
        doc_tfidf = {t: doc_tf[t] * idf.get(t, 1.0) for t in doc_tf}
        sim = _cosine_sim(q_tfidf, doc_tfidf)
        if sim > 0:
            scored.append((sim, trio))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for score, trio in scored[:top_k]:
        results.append(trio.model_copy(update={"retrieval_score": round(score, 4)}))
    return results


def invalidate_cache() -> None:
    global _cache
    _cache = None
