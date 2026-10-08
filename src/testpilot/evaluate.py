"""Real-log metrics; no fabricated diagnosis labels or invented baselines."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from statistics import median

import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

from . import db
from .graph import analyze_run


def evaluate(limit: int = 100, *, baseline_csv: Path | None = None,
             labeled_csv: Path | None = None, destination: Path | None = None) -> dict:
    rows = db.list_runs(limit=limit)
    if not rows:
        raise ValueError("Database has no real CI runs; fetch and ingest BugSwarm logs first.")
    reports = [analyze_run(row["source_id"], save=False) for row in rows]
    truth = [row["status"] == "failed" for row in rows]
    prediction = [report["predicted_status"] == "failed" for report in reports]
    result = {
        "dataset": "TQRG/BugSwarm (real CI logs)", "evaluated_runs": len(rows),
        "ground_truth_distribution": dict(Counter(row["status"] for row in rows)),
        "failure_detection": {
            "accuracy": round(accuracy_score(truth, prediction), 4),
            "precision": round(precision_score(truth, prediction, zero_division=0), 4),
            "recall": round(recall_score(truth, prediction, zero_division=0), 4),
            "f1": round(f1_score(truth, prediction, zero_division=0), 4),
        },
        "latency_ms": {
            "mean": round(sum(r["analysis_ms"] for r in reports) / len(reports), 2),
            "median": round(median(r["analysis_ms"] for r in reports), 2),
            "min": round(min(r["analysis_ms"] for r in reports), 2),
            "max": round(max(r["analysis_ms"] for r in reports), 2),
        },
        "cause_family_counts": dict(Counter(r["failure_family"] for r in reports)),
        "manual_root_cause_accuracy": "XX (requires verified human ground truth)",
        "diagnosis_time_reduction_pct": "XX (requires measured comparable human baseline)",
    }
    if labeled_csv:
        with labeled_csv.open(newline="", encoding="utf-8") as handle:
            labels = {row["source_id"]: row["root_cause_family"].strip().lower()
                      for row in csv.DictReader(handle) if row.get("root_cause_family")}
        labeled = [(r, labels[r["source_id"]]) for r in reports if r["source_id"] in labels]
        result["manual_root_cause_accuracy"] = (round(sum(r["failure_family"] == y for r, y in labeled) / len(labeled), 4)
                                                 if labeled else "XX (no matching labels)")
        result["manually_labeled_runs"] = len(labeled)
    if baseline_csv:
        with baseline_csv.open(newline="", encoding="utf-8") as handle:
            humans = {row["source_id"]: float(row["human_seconds"])
                      for row in csv.DictReader(handle) if row.get("human_seconds")}
        # Pandas inner join ensures the exact same real CI source IDs are timed in both cohorts.
        automated = pd.DataFrame([{"source_id": r["source_id"], "automated_seconds": r["analysis_ms"] / 1000}
                                  for r in reports])
        manual = pd.DataFrame([{"source_id": sid, "human_seconds": seconds}
                               for sid, seconds in humans.items() if seconds > 0])
        if not manual.empty:
            matched = automated.merge(manual, on="source_id", how="inner", validate="one_to_one")
            if not matched.empty:
                human_total = float(matched["human_seconds"].sum())
                machine_total = float(matched["automated_seconds"].sum())
                result["diagnosis_time_reduction_pct"] = round(100 * (human_total - machine_total) / human_total, 2)
                result["baseline_matched_cases"] = len(matched)
            result["baseline_definition"] = "Human and TestPilot time measured for identical source IDs; does not validate diagnosis quality"
    if destination:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
