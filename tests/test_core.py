from __future__ import annotations

import os
from pathlib import Path

import pytest

from agent_safe_write import DriftDetected, UnsafeTarget, fingerprint, safe_write, sha256_bytes


def test_create_missing_file(tmp_path: Path) -> None:
    target = tmp_path / "new.txt"
    receipt = safe_write(target, b"hello\n", expected_sha256=None, allowed_root=tmp_path)
    assert target.read_bytes() == b"hello\n"
    assert receipt.status.value == "SUCCEEDED"
    assert receipt.observed_after is not None
    assert receipt.observed_after.sha256 == sha256_bytes(b"hello\n")


def test_replace_requires_matching_hash(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_bytes(b"old")
    old_hash = fingerprint(target).sha256
    assert old_hash is not None

    receipt = safe_write(target, b"new", expected_sha256=old_hash, allowed_root=tmp_path)
    assert target.read_bytes() == b"new"
    assert receipt.expected_before_sha256 == old_hash


def test_wrong_hash_aborts_without_change(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_bytes(b"original")

    with pytest.raises(DriftDetected):
        safe_write(target, b"replacement", expected_sha256="0" * 64, allowed_root=tmp_path)
    assert target.read_bytes() == b"original"


def test_drift_after_temp_fsync_aborts_before_replace(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_bytes(b"v1")
    old_hash = fingerprint(target).sha256
    assert old_hash is not None

    def mutate_target(path: Path) -> None:
        path.write_bytes(b"someone else changed this")

    with pytest.raises(DriftDetected, match="changed after planning"):
        safe_write(
            target,
            b"agent result",
            expected_sha256=old_hash,
            allowed_root=tmp_path,
            _after_temp_write=mutate_target,
        )
    assert target.read_bytes() == b"someone else changed this"


def test_existing_file_cannot_be_created_as_new(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_bytes(b"exists")
    with pytest.raises(DriftDetected):
        safe_write(target, b"new", expected_sha256=None, allowed_root=tmp_path)


def test_symlink_target_is_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real.txt"
    real.write_bytes(b"real")
    link = tmp_path / "link.txt"
    link.symlink_to(real)
    with pytest.raises(UnsafeTarget, match="symlink"):
        safe_write(link, b"bad", expected_sha256=None, allowed_root=tmp_path)
    assert real.read_bytes() == b"real"


def test_target_outside_allowed_root_is_rejected(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    target = outside / "x.txt"
    with pytest.raises(UnsafeTarget, match="outside allowed root"):
        safe_write(target, b"x", expected_sha256=None, allowed_root=allowed)


def test_preserves_mode_on_replace(tmp_path: Path) -> None:
    target = tmp_path / "script.sh"
    target.write_bytes(b"old")
    os.chmod(target, 0o750)
    old_hash = fingerprint(target).sha256
    assert old_hash is not None

    safe_write(target, b"new", expected_sha256=old_hash, allowed_root=tmp_path)
    assert (os.stat(target).st_mode & 0o777) == 0o750
