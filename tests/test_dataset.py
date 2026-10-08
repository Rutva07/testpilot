from pathlib import Path

from testpilot.dataset import detect_status, is_log, discover_logs


def test_path_based_status_detection():
    assert detect_status(Path("BugSwarm", "abc", "failed", "console.log")) == "failed"
    assert detect_status(Path("BugSwarm", "abc", "passed", "console.log")) == "passed"
    assert detect_status(Path("BugSwarm", "abc", "misc", "console.log")) is None


def test_only_logs_in_documented_formats():
    assert is_log(Path("archive", "failed", "build.log"))
    assert is_log(Path("archive", "passed", "log.txt"))
    assert not is_log(Path("archive", "README.md"))
    assert not is_log(Path("archive", "source.py"))


def test_empty_source_generates_no_log_records(tmp_path):
    assert list(discover_logs(tmp_path)) == []
