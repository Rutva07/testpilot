"""IsolationForest on real historical run-level numeric diagnostics."""
from __future__ import annotations

import numpy as np
from sklearn.ensemble import IsolationForest



def vector(row: dict) -> list[float]:
    family = row.get("failure_family", "unknown")
    return [
        np.log1p(max(0, int(row.get("line_count", 0)))),
        np.log1p(max(0, int(row.get("failed_test_count", len(row.get("failed_tests") or []))))),
        float(bool(row.get("exception_name"))),
        float(row.get("status") == "failed"),
        float(family == "dependency"), float(family == "compilation"),
        float(family == "timeout"), float(family == "infrastructure"),
        float(family == "assertion"), float(family == "runtime"),
        float(family == "test_failure"),
    ]


def score_run(run: dict) -> dict:
    from . import db
    history = [r for r in db.fetch_features() if r["id"] != run["id"]]
    # A minimum prevents very small corpora from producing misleading percentiles.
    if len(history) < 30:
        return {"available": False, "reason": "fewer than 30 real historical logs", "history_size": len(history)}
    model = IsolationForest(n_estimators=100, contamination="auto", random_state=42, n_jobs=1)
    features = np.array([vector(r) for r in history], dtype=np.float64)
    model.fit(features)
    point = np.array([vector(run)])
    point_score = -float(model.score_samples(point)[0])
    distribution = -model.score_samples(features)
    percentile = round(100 * float(np.mean(distribution <= point_score)), 2)
    return {"available": True, "score": round(point_score, 5),
            "anomaly_percentile": percentile, "history_size": len(history),
            "interpretation": "Higher percentile means more unusual numeric log features"}
