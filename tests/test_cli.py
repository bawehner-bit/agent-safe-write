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
    assert json.loads(result.stderr)["status"] == "NEEDS_REVIEW"
