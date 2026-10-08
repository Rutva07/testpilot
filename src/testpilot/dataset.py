"""Import actual BugSwarm CI logs. Never fabricates or augments records."""
from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .extract import summarize_log

SOURCE = "https://github.com/TQRG/BugSwarm.git"
MAX_LOG_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class DiscoveredLog:
    path: Path
    artifact_key: str
    repository: str
    status: str


def fetch_repository(destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"{destination} already exists. Use it with 'testpilot ingest'.")
    # Shallow clone the public *real* log archive. No GitHub authentication required.
    subprocess.run(["git", "clone", "--depth", "1", "--branch", "master", SOURCE, str(destination)], check=True)


def detect_status(path: Path) -> str | None:
    # Classify by path components first, avoiding substring hits on project names.
    parts = [part.lower() for part in path.parts]
    stem = path.stem.lower()
    failed_tokens = {"failed", "failing", "buggy", "broken", "failure", "fail", "failed-job", "failed_job"}
    passed_tokens = {"passed", "passing", "fixed", "successful", "success", "pass", "passed-job", "passed_job"}
    parts_to_check = parts[-5:]
    if any(p in failed_tokens for p in parts_to_check) or re.search(r"(?:^|[-_.])(?:failed|fail|buggy|failing|broken)(?:[-_.]|$)", stem):
        return "failed"
    if any(p in passed_tokens for p in parts_to_check) or re.search(r"(?:^|[-_.])(?:passed|pass|fixed|passing|success)(?:[-_.]|$)", stem):
        return "passed"
    return None


def is_log(path: Path) -> bool:
    if path.suffix.lower() in {".log", ".out", ".trace"}:
        return True
    name = path.name.lower()
    return (path.suffix.lower() in {".txt", ".text"} and
            ("log" in name or any("log" in p.lower() for p in path.parts[-4:-1])))


def discover_logs(root: Path) -> Iterator[DiscoveredLog]:
    if not root.is_dir():
        raise NotADirectoryError(f"No dataset directory: {root}")
    seen: set[Path] = set()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.parts or not is_log(path):
            continue
        if path.stat().st_size == 0 or path.stat().st_size > MAX_LOG_BYTES:
            continue
        status = detect_status(path.relative_to(root))
        if status is None:
            continue  # Never guess the ground-truth status of unlabeled logs.
        rel = path.relative_to(root)
        artifact = rel.parts[1] if len(rel.parts) >= 3 and rel.parts[0].lower() == "bugswarm" else rel.parts[0]
        # The archive's per-artifact folder names typically carry the original repository slug.
        # Use an artifact-specific stable repository key when exact slug is unavailable.
        repo = artifact.rsplit("-", 1)[0].replace("_", "/") if "-" in artifact else artifact
        if path not in seen:
            seen.add(path)
            yield DiscoveredLog(path=path, artifact_key=artifact, repository=repo, status=status)


def inspect_dataset(root: Path) -> dict[str, object]:
    logs = list(discover_logs(root))
    return {"source": SOURCE, "root": str(root), "logs": len(logs),
            "failed": sum(r.status == "failed" for r in logs),
            "passed": sum(r.status == "passed" for r in logs),
            "artifacts": len({r.artifact_key for r in logs}),
            "examples": [str(v.path.relative_to(root)) for v in logs[:8]]}


def ingest_dataset(root: Path, *, limit: int | None = None) -> dict[str, int]:
    from . import db
    added = failed = passed = lines = 0
    for entry in discover_logs(root):
        if limit is not None and added >= limit:
            break
        payload = entry.path.read_bytes()
        text = payload.decode("utf-8", errors="replace")
        ev = summarize_log(text, known_status=entry.status)
        source_id = "bugswarm:" + str(entry.path.relative_to(root)).replace("\\", "/")
        db.upsert_run({
            "source_id": source_id, "repository": entry.repository,
            "artifact_key": entry.artifact_key, "status": entry.status,
            "log_path": str(entry.path.relative_to(root)), "log_text": text,
            "line_count": ev.line_count, "fingerprint": ev.fingerprint,
            "failure_family": ev.family, "exception_name": ev.exception_name,
            "failed_tests": ev.failed_tests, "log_sha256": hashlib.sha256(payload).hexdigest(),
        })
        added += 1
        failed += entry.status == "failed"
        passed += entry.status == "passed"
        lines += ev.line_count
    if added == 0:
        raise ValueError(
            "No labeled log files found. Run 'testpilot inspect --path PATH'. "
            "Expected actual failed/passed .log, .out, .trace or log*.txt files. "
            "You can also ingest a directory of real CI logs organized in failed/ and passed/."
        )
    return {"ingested": added, "failed": failed, "passed": passed, "log_lines": lines}
