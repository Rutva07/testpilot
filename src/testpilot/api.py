"""Local REST API. Defaults to loopback; place authentication before public deployment."""
from fastapi import FastAPI, HTTPException, Query

from . import db
from .graph import analyze_run

api = FastAPI(title="TestPilot", version="1.0.0", docs_url="/docs")


@api.get("/health")
def health():
    try:
        db.counts()
        return {"status": "ok", "database": "connected"}
    except Exception:
        raise HTTPException(status_code=503, detail="PostgreSQL not ready") from None


@api.get("/stats")
def stats():
    return db.counts()


@api.get("/runs")
def runs(limit: int = Query(20, ge=1, le=1000), status: str | None = None):
    if status not in (None, "passed", "failed"):
        raise HTTPException(status_code=422, detail="status must be passed or failed")
    return db.list_runs(limit=limit, status=status)


@api.post("/analyze/{source_id:path}")
def analyze(source_id: str):
    try:
        return analyze_run(source_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Run not found") from None


@api.get("/reports/{report_id}")
def report(report_id: int):
    item = db.get_report(report_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return item
