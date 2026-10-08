from __future__ import annotations

from contextlib import contextmanager
from importlib.resources import files
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .config import get_settings

SCHEMA_TEXT = files("testpilot").joinpath("schema.sql").read_text(encoding="utf-8")


@contextmanager
def connection() -> Iterator[psycopg.Connection]:
    with psycopg.connect(get_settings().database_url, row_factory=dict_row) as conn:
        yield conn


def init_database() -> None:
    with connection() as conn:
        conn.execute(SCHEMA_TEXT)


def upsert_run(item: dict[str, Any]) -> bool:
    sql = """
        INSERT INTO ci_runs (source_id, repository, artifact_key, status, log_path, log_text,
                             line_count, fingerprint, failure_family, exception_name,
                             failed_tests, log_sha256)
        VALUES (%(source_id)s, %(repository)s, %(artifact_key)s, %(status)s, %(log_path)s,
                %(log_text)s, %(line_count)s, %(fingerprint)s, %(failure_family)s,
                %(exception_name)s, %(failed_tests)s, %(log_sha256)s)
        ON CONFLICT (source_id) DO UPDATE SET
            repository=EXCLUDED.repository, artifact_key=EXCLUDED.artifact_key,
            status=EXCLUDED.status, log_path=EXCLUDED.log_path, log_text=EXCLUDED.log_text,
            line_count=EXCLUDED.line_count, fingerprint=EXCLUDED.fingerprint,
            failure_family=EXCLUDED.failure_family, exception_name=EXCLUDED.exception_name,
            failed_tests=EXCLUDED.failed_tests, log_sha256=EXCLUDED.log_sha256
        RETURNING id
    """
    values = {**item, "failed_tests": Jsonb(item["failed_tests"])}
    with connection() as conn:
        return conn.execute(sql, values).fetchone() is not None


def get_run(source_id: str, *, include_log: bool = True) -> dict[str, Any] | None:
    col = "*" if include_log else "id, source_id, repository, artifact_key, status, log_path, line_count, fingerprint, failure_family, exception_name, failed_tests"
    with connection() as conn:
        return conn.execute(f"SELECT {col} FROM ci_runs WHERE source_id = %s", (source_id,)).fetchone()


def get_run_by_id(run_id: int, *, include_log: bool = False) -> dict[str, Any] | None:
    col = "*" if include_log else "id, source_id, repository, artifact_key, status, log_path, line_count, fingerprint, failure_family, exception_name, failed_tests"
    with connection() as conn:
        return conn.execute(f"SELECT {col} FROM ci_runs WHERE id = %s", (run_id,)).fetchone()


def list_runs(limit: int = 20, status: str | None = None) -> list[dict[str, Any]]:
    with connection() as conn:
        return conn.execute(
            """SELECT id, source_id, repository, status, failure_family, line_count
               FROM ci_runs WHERE (%s::text IS NULL OR status = %s)
               ORDER BY id LIMIT %s""",
            (status, status, min(max(1, limit), 1000)),
        ).fetchall()


def candidates(run: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    with connection() as conn:
        return conn.execute(
            """SELECT id, source_id, repository, artifact_key, status, fingerprint,
                      failure_family, exception_name, failed_tests
               FROM ci_runs WHERE id <> %s AND status = 'failed'
               ORDER BY CASE WHEN repository = %s THEN 0 ELSE 1 END,
                        CASE WHEN failure_family = %s THEN 0 ELSE 1 END, id
               LIMIT %s""",
            (run["id"], run["repository"], run["failure_family"], limit),
        ).fetchall()


def repo_summary(repo: str) -> dict[str, Any]:
    with connection() as conn:
        result = conn.execute(
            """SELECT COUNT(*) AS total,
                      COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                      COUNT(*) FILTER (WHERE status = 'passed') AS passed
               FROM ci_runs WHERE repository = %s""", (repo,)
        ).fetchone()
        result["families"] = conn.execute(
            """SELECT failure_family, COUNT(*) AS n FROM ci_runs
               WHERE repository = %s AND status = 'failed'
               GROUP BY failure_family ORDER BY n DESC LIMIT 10""", (repo,)
        ).fetchall()
        return result


def fetch_features(*, max_rows: int = 30000) -> list[dict[str, Any]]:
    with connection() as conn:
        return conn.execute(
            """SELECT id, repository, status, line_count, failure_family, exception_name,
                      COALESCE(jsonb_array_length(failed_tests), 0) AS failed_test_count
               FROM ci_runs ORDER BY id LIMIT %s""", (max_rows,)
        ).fetchall()


def save_report(run_id: int, report: dict[str, Any], duration_ms: float) -> int:
    with connection() as conn:
        result = conn.execute(
            """INSERT INTO triage_reports (run_id, predicted_status, predicted_cause,
                    confidence, method, result, analysis_ms)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (run_id, report["predicted_status"], report["cause"], report["confidence"],
             report["method"], Jsonb(report), duration_ms),
        ).fetchone()
        return result["id"]


def get_report(report_id: int) -> dict[str, Any] | None:
    with connection() as conn:
        return conn.execute(
            """SELECT t.id, r.source_id, t.result, t.analysis_ms, t.created_at
               FROM triage_reports t JOIN ci_runs r ON r.id = t.run_id WHERE t.id = %s""",
            (report_id,),
        ).fetchone()


def counts() -> dict[str, int]:
    with connection() as conn:
        return conn.execute(
            """SELECT COUNT(*) AS total,
                      COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                      COUNT(*) FILTER (WHERE status = 'passed') AS passed,
                      COALESCE(SUM(line_count),0) AS log_lines,
                      COUNT(DISTINCT repository) AS repositories FROM ci_runs"""
        ).fetchone()
