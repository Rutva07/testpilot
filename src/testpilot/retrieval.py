"""Lexical retrieval plus structured PostgreSQL evidence; no external vector DB."""
from __future__ import annotations

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .config import get_settings


def as_document(row: dict) -> str:
    return " ".join([str(row.get("failure_family") or ""),
                     str(row.get("exception_name") or ""),
                     " ".join(row.get("failed_tests") or []),
                     str(row.get("fingerprint") or "")])


def similar_incidents(run: dict, limit: int = 5) -> list[dict]:
    from . import db
    pool = db.candidates(run, get_settings().similarity_candidates)
    if not pool:
        return []
    documents = [as_document(run), *(as_document(row) for row in pool)]
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), token_pattern=r"(?u)\b[\w-]+\b")
    matrix = vectorizer.fit_transform(documents)
    scores = cosine_similarity(matrix[:1], matrix[1:])[0]
    ranked = sorted(zip(pool, scores), key=lambda v: (
        float(v[1]) + (0.2 if v[0]["repository"] == run["repository"] else 0),
        v[0]["fingerprint"] == run["fingerprint"]), reverse=True)
    return [dict(source_id=item["source_id"], repository=item["repository"],
                 failure_family=item["failure_family"],
                 fingerprint_match=item["fingerprint"] == run["fingerprint"],
                 similarity=round(float(score), 4))
            for item, score in ranked[:min(max(1, limit), 20)]]
