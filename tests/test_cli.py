from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from agent_safe_write import fingerprint


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "agent_safe_write", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_cli_apply_and_receipt(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    source = tmp_path / "source.txt"
    target.write_text("before")
    source.write_text("after")
    expected = fingerprint(target).sha256
    assert expected is not None

    result = run_cli(
        "apply",
        str(target),
        "--from-file",
        str(source),
        "--expect",
        expected,
        "--root",
        str(tmp_path),
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "SUCCEEDED"
    assert payload["committed"] is True
    assert target.read_text() == "after"


def test_cli_drift_exit_code(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    source = tmp_path / "source.txt"
    target.write_text("before")
    source.write_text("after")

    result = run_cli(
        "apply",
        str(target),
        "--from-file",
        str(source),
        "--expect",
        "f" * 64,
    )
    assert result.returncode == 3
    payload = json.loads(result.stderr)
    assert payload["status"] == "NEEDS_REVIEW"
    assert payload["code"] == "DRIFT_DETECTED"
    assert payload["committed"] is False


def test_cli_outside_root_has_stable_error_code(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    source = allowed / "source.txt"
    source.write_text("desired")

    result = run_cli(
        "apply",
        str(outside / "target.txt"),
        "--from-file",
        str(source),
        "--root",
        str(allowed),
    )
    assert result.returncode == 2
    payload = json.loads(result.stderr)
    assert payload["status"] == "FAILED"
    assert payload["code"] == "TARGET_OUTSIDE_ROOT"
    assert payload["committed"] is False


def test_cli_usage_error_is_json_with_distinct_exit_code() -> None:
    result = run_cli("apply", "target.txt")
    assert result.returncode == 64
    payload = json.loads(result.stderr)
    assert payload["status"] == "FAILED"
    assert payload["code"] == "USAGE_ERROR"
    assert payload["committed"] is False


def test_cli_missing_source_is_machine_readable(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    result = run_cli(
        "apply",
        str(target),
        "--from-file",
        str(tmp_path / "missing-source.txt"),
    )
    assert result.returncode == 2
    payload = json.loads(result.stderr)
    assert payload["status"] == "FAILED"
    assert payload["code"] == "OS_ERROR"
    assert payload["committed"] is False
