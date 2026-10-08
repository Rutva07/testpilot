CREATE TABLE IF NOT EXISTS ci_runs (
    id BIGSERIAL PRIMARY KEY,
    source_id TEXT NOT NULL UNIQUE,
    source_dataset TEXT NOT NULL DEFAULT 'TQRG/BugSwarm',
    repository TEXT NOT NULL,
    artifact_key TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('failed', 'passed')),
    log_path TEXT NOT NULL,
    log_text TEXT NOT NULL,
    line_count INTEGER NOT NULL,
    fingerprint TEXT NOT NULL,
    failure_family TEXT NOT NULL,
    exception_name TEXT,
    failed_tests JSONB NOT NULL DEFAULT '[]'::jsonb,
    log_sha256 TEXT NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_runs_repository ON ci_runs(repository);
CREATE INDEX IF NOT EXISTS idx_runs_fingerprint ON ci_runs(fingerprint);
CREATE INDEX IF NOT EXISTS idx_runs_status_family ON ci_runs(status, failure_family);
CREATE INDEX IF NOT EXISTS idx_runs_artifact ON ci_runs(artifact_key);
CREATE TABLE IF NOT EXISTS triage_reports (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES ci_runs(id) ON DELETE CASCADE,
    predicted_status TEXT NOT NULL,
    predicted_cause TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    method TEXT NOT NULL,
    result JSONB NOT NULL,
    analysis_ms DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_reports_run ON triage_reports(run_id, created_at DESC);
