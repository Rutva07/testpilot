from testpilot.retrieval import as_document


def test_incident_representation_contains_specific_evidence():
    result = as_document({"failure_family": "runtime", "exception_name": "IndexError",
                          "failed_tests": ["tests/test_core.py::test_index"], "fingerprint": "ab"})
    assert "IndexError" in result
    assert "test_index" in result
