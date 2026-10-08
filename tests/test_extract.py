"""Unit checks for the parser. Strings here are test inputs, not dataset records."""
from testpilot.extract import normalize_signature, redact, summarize_log


def test_parse_pytest_exception():
    log = "FAILED tests/test_math.py::test_add - AssertionError: expected 2 but was 1\n"
    result = summarize_log(log)
    assert result.predicted_status == "failed"
    assert result.family == "assertion"
    assert result.failed_tests == ["tests/test_math.py::test_add"]
    assert result.exception_name == "AssertionError"
    assert result.evidence_lines


def test_pass_without_failure_tokens():
    result = summarize_log("12 passed in 0.35s\n")
    assert result.predicted_status == "passed"
    assert result.family == "unknown"


def test_fingerprint_collapses_numbers():
    assert normalize_signature("TimeoutError at line 123") == normalize_signature("TimeoutError at line 456")


def test_secret_redaction():
    assert "abcd" not in redact("Authorization: Bearer abcd")
    assert "[REDACTED]" in redact("token=abcd")


def test_known_status_does_not_leak_into_prediction():
    result = summarize_log("Finished successfully\n", known_status="failed")
    assert result.predicted_status == "passed"
