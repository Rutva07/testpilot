from testpilot.anomaly import vector


def test_numeric_anomaly_features():
    features = vector({"status": "failed", "line_count": 120,
                       "failed_tests": ["a", "b"], "failure_family": "assertion",
                       "exception_name": "AssertionError"})
    assert len(features) == 11
    assert features[3] == 1
    assert features[8] == 1
