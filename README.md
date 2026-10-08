# TestPilot — Automated Test Failure Analysis

**Python · LangGraph · LLM tool calling · PostgreSQL · Pandas-compatible JSON/CSV outputs · Scikit-learn · FastAPI**

TestPilot ingests authentic CI execution logs from the [TQRG/BugSwarm](https://github.com/TQRG/BugSwarm) research archive, extracts failure evidence, retrieves related incidents in PostgreSQL, scores anomalous failure patterns with Isolation Forest, and produces evidence-grounded root-cause triage reports. Its LangGraph workflow uses specialized log, database, anomaly, investigation, and reporting nodes. When an OpenAI key is configured, the investigator can call three restricted PostgreSQL-backed evidence tools and an LLM writes the final structured diagnosis. The deterministic workflow also runs without an LLM key.

## Architecture

```text
Public real BugSwarm failing/passing CI logs
                  |
        Path/status validation
                  |
   Regex-based evidence + fingerprints
                  |
            PostgreSQL
                  |
           LangGraph DAG
                  |
   Log Analyst -> Database Investigator
                  | (SQL + TF-IDF neighbors)
            Anomaly Analyst
                  | (Isolation Forest)
          Root-Cause Investigator
                  |<---- Read-only DB tools <--|
                  |---- Tool call loop ------>|
                  |
            Triage Reporter
                  |
  JSON evidence + classification + confidence
    + similar failures + suggested actions
                  |
         CLI / FastAPI / evaluation
```

**Database design:** `ci_runs` stores the original log, ground-truth build status, repository/artifact identifiers, normalized signature, extracted tests/exceptions, and a source checksum. `triage_reports` stores structured reports, diagnosis time, and provenance. SQL queries are parameterized; LLM tools cannot execute arbitrary SQL or shell commands.

## Dataset

**Name:** [BugSwarm, TQRG fault-localization review archive](https://github.com/TQRG/BugSwarm)

**Origin:** Public open-source projects whose Travis CI jobs were mined as failed/passed build pairs. The archive contains their real CI build transcripts and associated source-level changes. The reviewed collection identifies **112 build pairs** suitable for fault-localization/program-repair research; the larger original BugSwarm benchmark contains **3,091 pairs**, which is *not* the size of this reviewed archive. Counts of imported logs and log lines are obtained from the local database, not inferred from the original benchmark.

**Source link:** https://github.com/TQRG/BugSwarm

**Labels:** `failed` and `passed` are derived from the archive's labeled log filenames or directories. Unlabeled files are skipped rather than assigned invented labels. Extracted exceptions and failure families are heuristic features, **not** manually verified ground-truth root-cause labels. The archive is third-party data; its license and original research attribution remain with its authors.

**No generated incident data is used.** Each imported record corresponds to bytes read from a downloaded real CI log. Repeated ingestion upserts by the source path; raw log SHA-256 values preserve traceability.

## Requirements

- Python 3.10+ and Git.
- PostgreSQL 14+ (PostgreSQL 16 configuration provided in `docker-compose.yml`).
- Internet access for installing Python dependencies and obtaining the public BugSwarm repository.
- Optional OpenAI API key for LLM-assisted diagnosis. No key is needed for rule-based evidence extraction, SQL retrieval, anomaly scoring, or deterministic reports.

## Setup and execution

```bash
# 1. Create Python environment
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'

# 2. Start PostgreSQL (alternative: use an existing PostgreSQL instance)
docker compose up -d postgres
cp .env.example .env
# To connect to an existing PostgreSQL instance, edit DATABASE_URL in .env.

# 3. Create database tables
testpilot init-db

# 4. Get the authentic public CI failure corpus
testpilot fetch --path data/bugswarm

# 5. Check the real files identified by the importer
testpilot inspect --path data/bugswarm

# 6. Load the real logs into PostgreSQL
testpilot ingest --path data/bugswarm

# 7. Verify actual imported record counts and select one build
testpilot stats
testpilot list --limit 10

# 8. Investigate a real run (copy source_id from the previous command)
testpilot analyze 'bugswarm:PASTE_ACTUAL_SOURCE_PATH_HERE' --output reports/triage.json

# 9. Evaluate actual detection and runtime metrics
testpilot evaluate --limit 100 --output reports/evaluation.json

# 10. Serve local JSON API and interactive Swagger docs
uvicorn testpilot.api:api --host 127.0.0.1 --port 8000
# http://127.0.0.1:8000/docs
```

`data/bugswarm` can also be a manually cloned BugSwarm archive. The importer searches recursively for labeled `.log`, `.out`, `.trace`, and log-named `.txt` files. The command `testpilot inspect` displays precisely which files matched. For another real CI log corpus, organize originals under `failed/` and `passed/` directories, then point `--path` to that directory; no format conversion is required. Logs over 8 MiB and files without an explicit status in their path are skipped to avoid unverifiable automatic labeling.

**Optional LLM:** Set `OPENAI_API_KEY` and optionally `OPENAI_MODEL` in `.env`. The root-cause investigation can then call `find_similar_failures`, `repository_failure_summary`, and `fetch_failure_evidence`. The default model setting is `gpt-4.1-mini`; this uses your API account and may incur charges. Keeping `OPENAI_API_KEY` blank uses deterministic reasoning and no model API calls.

## Project layout

```text
TestPilot/
├── src/testpilot/
│   ├── api.py           # FastAPI endpoints
│   ├── anomaly.py       # sklearn IsolationForest on authentic historical runs
│   ├── cli.py           # fetch / inspect / ingest / analyze / evaluate
│   ├── config.py        # Environment variables
│   ├── dataset.py       # Public CI-log download and no-guess status ingestion
│   ├── db.py            # PostgreSQL schema and parameterized queries
│   ├── evaluate.py      # Logged-run detection, latency, optional human baselines
│   ├── extract.py       # Log parsers, error signatures, privacy redaction
│   ├── graph.py         # LangGraph agents + LLM tool loop + reports
│   ├── retrieval.py     # TF-IDF / cosine similarity over SQL candidates
│   └── schema.sql       # Packaged database schema
├── sql/schema.sql       # Database schema (human-readable)
├── tests/               # Offline unit tests (not evaluation datasets)
├── reports/             # JSON outputs, human-label/timing templates
├── data/                # Cloned public corpus (gitignored)
├── .github/workflows/   # Unit-test CI
├── .env.example
├── docker-compose.yml   # PostgreSQL only
├── Makefile
└── pyproject.toml
```

## Experiment and evaluation

**Study unit:** one authentic CI job transcript with failed/passed status from its source archive. **Retrieval evidence:** distinct historical failed runs, excluding the target job. **Failure categorization:** dependency, compilation, timeout, infrastructure, assertion, runtime, test failure, or unknown. **Statistical features:** log length, count of failed tests, exception presence, failed/passed marker, and one-hot family indicators. The Isolation Forest is fit on other real historical records in the local database; when fewer than 30 exist, the report marks the anomaly score unavailable.

`testpilot evaluate` computes observed classification accuracy, precision, recall, F1 (positive class: failed), run-level diagnosis latency, and failure-category distributions. Root-cause family accuracy is only computed against separately verified human annotations. Diagnosis-time reduction is measured on *matching* CI records with externally observed manual investigation times.

To add verified manual root-cause annotations, create a CSV with `source_id,root_cause_family` and pass `--labeled-csv PATH`. To calculate human-comparison time reduction, create `source_id,human_seconds` and pass `--baseline-csv PATH`:

```bash
testpilot evaluate --limit 100 \
    --labeled-csv reports/root_cause_labels.csv \
    --baseline-csv reports/human_baseline.csv \
    --output reports/evaluation.json
```

### Results

| Measurement | Value |
| --- | --- |
| Public benchmark | TQRG/BugSwarm (real Travis CI failed/passed logs) |
| Source archive's reviewed build pairs | 112 |
| Imported CI jobs | XX (reported by `testpilot stats`) |
| Imported original CI log lines | XX (reported by `testpilot stats`) |
| Failure detection accuracy | XX (reported by `testpilot evaluate`) |
| Failure detection precision / recall / F1 | XX / XX / XX |
| Median automated analysis duration | XX ms |
| Manually validated root-cause family accuracy | XX |
| Matched-case manual diagnosis time reduction | XX% |

**Interpretation:** Failure detection measures whether log patterns predict the archived *build outcome*. It is not equivalent to verified root-cause diagnosis. Isolation Forest percentiles represent relative anomaly, not accuracy or a causal explanation. Any time-reduction figure must use paired manual investigation data, not an assumed baseline.

## API

```text
GET  /health
GET  /stats
GET  /runs?limit=20&status=failed
POST /analyze/{source_id}
GET  /reports/{report_id}
```

`/analyze/{source_id}` runs the full investigation and stores its JSON result in PostgreSQL. The local server binds to `127.0.0.1`; network/public deployment should add authentication and access controls. Imported logs are untrusted text, may contain user tokens, and should be reviewed before sharing; LLM-visible excerpts use basic secret redaction, not a guarantee of complete sanitization.

## Tests

```bash
python -m pytest -q
```

The tests validate parsing, redaction, source-label recognition, feature construction, and retrieval text preparation. They do not represent a measured run over BugSwarm and do not contribute to experimental results.

## References

- BugSwarm authors and public dataset: https://www.bugswarm.org/ and https://github.com/BugSwarm/bugswarm
- Critical Review of BugSwarm for Fault Localization and Program Repair: https://github.com/TQRG/BugSwarm
- BugSwarm paper: Tomassi et al., *BugSwarm: Mining and Continuously Growing a Dataset of Reproducible Failures and Fixes*, ICSE 2019.
