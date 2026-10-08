"""Operations CLI for a real CI-log archive."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import db
from .dataset import fetch_repository, ingest_dataset, inspect_dataset
from .evaluate import evaluate
from .graph import analyze_run

app = typer.Typer(help="TestPilot CI failure triage", no_args_is_help=True)
console = Console()


def show(data):
    console.print_json(data=json.dumps(data, default=str))


@app.command("init-db")
def init_db():
    """Create the PostgreSQL schema."""
    db.init_database()
    console.print("PostgreSQL schema is ready.")


@app.command()
def fetch(path: Path = typer.Option(Path("data/bugswarm"), help="Local clone destination")):
    """Clone the public real-world BugSwarm log dataset."""
    fetch_repository(path)
    show(inspect_dataset(path))


@app.command("inspect")
def inspect_cmd(path: Path = typer.Option(Path("data/bugswarm"))):
    """Identify real labeled CI logs before ingestion."""
    show(inspect_dataset(path))


@app.command()
def ingest(path: Path = typer.Option(Path("data/bugswarm")),
           limit: Optional[int] = typer.Option(None, min=1)):
    """Parse and import authentic failed/passed logs into PostgreSQL."""
    show(ingest_dataset(path, limit=limit))


@app.command()
def stats():
    """Actual database counts."""
    show(db.counts())


@app.command("list")
def list_cmd(limit: int = typer.Option(20, min=1, max=1000),
             status: Optional[str] = typer.Option(None)):
    """Display IDs that can be passed to the analyze command."""
    table = Table("Source ID", "Repo", "Status", "Failure Family")
    for row in db.list_runs(limit=limit, status=status):
        table.add_row(row["source_id"], row["repository"], row["status"], row["failure_family"])
    console.print(table)


@app.command()
def analyze(source_id: str, output: Optional[Path] = None):
    """Run all LangGraph roles on one imported CI run."""
    result = analyze_run(source_id)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        console.print(f"Saved report: {output}")
    show(result)


@app.command("evaluate")
def evaluate_cmd(limit: int = typer.Option(100, min=1, max=1000),
                 baseline_csv: Optional[Path] = None,
                 labeled_csv: Optional[Path] = None,
                 output: Path = Path("reports/evaluation.json")):
    """Evaluate detection and runtime; optionally use real human labels and timings."""
    show(evaluate(limit=limit, baseline_csv=baseline_csv,
                  labeled_csv=labeled_csv, destination=output))


if __name__ == "__main__":
    app()
