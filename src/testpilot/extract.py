"""Deterministic extraction from unmodified CI logs; no generated training records."""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass

# Prioritized families: a failed build can contain several historical errors in its output.
RULES = [
    ("dependency", r"(?:ModuleNotFoundError|ImportError|No module named|Could not resolve|DependencyResolutionException|package .* not found|npm ERR! code ERESOLVE|pip.*No matching distribution)"),
    ("compilation", r"(?:Compilation failed|COMPILATION ERROR|SyntaxError:|cannot find symbol|error: package .* does not exist|fatal error: .*\.h: No such file)"),
    ("timeout", r"(?:TimeoutError|timed out|TimeoutException|exceeded the time limit|job exceeded maximum time)"),
    ("infrastructure", r"(?:ConnectionRefusedError|No space left on device|ECONNRESET|ENETUNREACH|502 Bad Gateway|503 Service Unavailable|network is unreachable)"),
    ("assertion", r"(?:AssertionError|AssertionFailedError|AssertionError:|expected .* but was|Assertion failed|FAILED\s+\S+::\S+)"),
    ("runtime", r"(?:\b(?:NullPointerException|IndexError|KeyError|TypeError|ValueError|RuntimeError|AttributeError|IOException|Segmentation fault|Exception in thread)\b)"),
    ("test_failure", r"(?:Tests run: \d+, Failures: [1-9]|\b[1-9]\d* failed\b|\bFAILURES!!!|There (?:was|were) \d+ failure)"),
]
COMPILED = [(name, re.compile(expr, re.IGNORECASE)) for name, expr in RULES]
EXCEPTION = re.compile(r"\b([\w.]+(?:Error|Exception|Failure))\b")
PYTEST = re.compile(r"^FAILED\s+(\S+::\S+)", re.MULTILINE)
JUNIT = re.compile(r"(?:^\d+\)\s+([\w.]+\([^\n]+\))|^\s*([\w.]+\s*<<< FAILURE!))", re.MULTILINE)
SECRETS = [
    re.compile(r"(?i)(authorization:\s*bearer\s+)\S+"),
    re.compile(r"(?i)((?:api[_-]?key|token|password|secret)\s*[=:]\s*)\S+"),
    re.compile(r"(?i)\b(?:ghp_|github_pat_)[A-Za-z0-9_]+"),
]


@dataclass(frozen=True)
class Evidence:
    predicted_status: str
    family: str
    fingerprint: str
    exception_name: str | None
    failed_tests: list[str]
    evidence_lines: list[str]
    line_count: int
    log_excerpt: str


def redact(text: str) -> str:
    for pat in SECRETS:
        text = pat.sub(lambda m: (m.group(1) if m.lastindex else "") + "[REDACTED]", text)
    return text


def normalize_signature(text: str) -> str:
    value = text.strip().lower()
    value = re.sub(r"\b[0-9a-f]{8,}\b", "<hex>", value)
    value = re.sub(r"\b\d+(?:\.\d+)*\b", "<n>", value)
    value = re.sub(r"(?:/[^\s/:]+){2,}", "<path>", value)
    return re.sub(r"\s+", " ", value)[:300]


def summarize_log(text: str, *, known_status: str | None = None, excerpt_chars: int = 12000) -> Evidence:
    lines = text.splitlines()
    matches = [(i, line.strip()[:350], name) for i, line in enumerate(lines)
               for name, pattern in COMPILED if pattern.search(line)]
    family = next((name for name, _ in COMPILED if any(t == name for _, _, t in matches)), "unknown")
    selected = [line for _, line, name in matches if name == family]
    if not selected:
        selected = [line for line in reversed(lines) if line.strip()][:3]
    selected = selected[:8]
    exc = EXCEPTION.search("\n".join(selected)) or EXCEPTION.search(text[-10000:])
    failed_tests = sorted(set(PYTEST.findall(text)))
    for match in JUNIT.findall(text):
        failed_tests.extend(v.strip() for v in match if v.strip())
    failed_tests = sorted(set(failed_tests))[:100]
    predicted_status = "failed" if matches else "passed"
    if known_status not in (None, "failed", "passed"):
        raise ValueError("known_status must be 'failed', 'passed', or None")
    basis = selected[0] if selected else (exc.group(1) if exc else "no-diagnostic-signal")
    sig = normalize_signature(basis)
    fingerprint = hashlib.sha256(f"{family}:{sig}".encode()).hexdigest()[:24]
    # Keep actual tail (often where the failure occurred) plus matched evidence.
    excerpt = "\n".join(["[MATCHED EVIDENCE]", *selected, "[LOG TAIL]", text[-max(200, excerpt_chars - 1500):]])
    return Evidence(
        predicted_status=predicted_status, family=family, fingerprint=fingerprint,
        exception_name=exc.group(1) if exc else None, failed_tests=failed_tests,
        evidence_lines=[redact(s) for s in selected], line_count=len(lines),
        log_excerpt=redact(excerpt)[:excerpt_chars],
    )


def evidence_dict(text: str, **kwargs: object) -> dict:
    return asdict(summarize_log(text, **kwargs))
