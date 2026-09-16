from __future__ import annotations

import os
from pathlib import Path
import threading

import pytest

import agent_safe_write.core as core
from agent_safe_write import (
    DriftDetected,
    SafeWriteError,
    UnsafeTarget,
    fingerprint,
    plan_write,
    safe_write,
    sha256_bytes,
)


def test_create_missing_file(tmp_path: Path) -> None:
    target = tmp_path / "new.txt"
    receipt = safe_write(target, b"hello\n", expected_sha256=None, allowed_root=tmp_path)
    assert target.read_bytes() == b"hello\n"
    assert receipt.status.value == "SUCCEEDED"
    assert receipt.committed is True
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
    assert receipt.committed is True


def test_wrong_hash_aborts_without_change(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_bytes(b"original")

    with pytest.raises(DriftDetected) as exc_info:
        safe_write(target, b"replacement", expected_sha256="0" * 64, allowed_root=tmp_path)
    assert exc_info.value.code == "DRIFT_DETECTED"
    assert exc_info.value.committed is False
    assert target.read_bytes() == b"original"


def test_deterministic_drift_injection_after_temp_fsync_aborts_before_replace(
    tmp_path: Path,
) -> None:
    target = tmp_path / "file.txt"
    target.write_bytes(b"v1")
    old_hash = fingerprint(target).sha256
    assert old_hash is not None

    def mutate_target(path: Path) -> None:
        path.write_bytes(b"someone else changed this")

    with pytest.raises(DriftDetected, match="changed after planning") as exc_info:
        safe_write(
            target,
            b"agent result",
            expected_sha256=old_hash,
            allowed_root=tmp_path,
            _after_temp_write=mutate_target,
        )
    assert exc_info.value.code == "DRIFT_DETECTED"
    assert target.read_bytes() == b"someone else changed this"


def test_documented_final_check_to_rename_window_is_not_atomic_cas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Document the unavoidable replace-path limitation.

    The competing write is injected at the os.replace call, which is after the
    final fingerprint has already completed. The library cannot detect it and
    its atomic rename wins. This test is intentionally a limitation proof, not
    a claim that concurrent replacement is prevented.
    """

    target = tmp_path / "file.txt"
    target.write_bytes(b"v1")
    old_hash = fingerprint(target).sha256
    assert old_hash is not None

    real_replace = core.os.replace

    def replace_after_competing_write(src: os.PathLike[str], dst: os.PathLike[str]) -> None:
        Path(dst).write_bytes(b"competing update")
        real_replace(src, dst)

    monkeypatch.setattr(core.os, "replace", replace_after_competing_write)

    receipt = safe_write(
        target,
        b"agent result",
        expected_sha256=old_hash,
        allowed_root=tmp_path,
    )

    assert receipt.status.value == "SUCCEEDED"
    assert target.read_bytes() == b"agent result"


def test_atomic_create_if_absent_does_not_clobber_racing_creator(tmp_path: Path) -> None:
    target = tmp_path / "new.txt"
    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    unexpected: list[BaseException] = []
    guard = threading.Lock()

    def pause_after_stage(_: Path) -> None:
        barrier.wait(timeout=5)

    def writer(payload: bytes) -> None:
        try:
            receipt = safe_write(
                target,
                payload,
                expected_sha256=None,
                allowed_root=tmp_path,
                _after_temp_write=pause_after_stage,
            )
            outcome = receipt.status.value
        except DriftDetected as exc:
            outcome = exc.code
        except BaseException as exc:  # pragma: no cover - failure diagnostic
            with guard:
                unexpected.append(exc)
            return
        with guard:
            outcomes.append(outcome)

    threads = [
        threading.Thread(target=writer, args=(b"writer-a",)),
        threading.Thread(target=writer, args=(b"writer-b",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not unexpected
    assert sorted(outcomes) == ["DRIFT_DETECTED", "SUCCEEDED"]
    assert target.read_bytes() in {b"writer-a", b"writer-b"}


def test_existing_file_cannot_be_created_as_new(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_bytes(b"exists")
    with pytest.raises(DriftDetected) as exc_info:
        safe_write(target, b"new", expected_sha256=None, allowed_root=tmp_path)
    assert exc_info.value.code == "DRIFT_DETECTED"


def test_symlink_target_is_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real.txt"
    real.write_bytes(b"real")
    link = tmp_path / "link.txt"
    link.symlink_to(real)
    with pytest.raises(UnsafeTarget, match="symlink") as exc_info:
        safe_write(link, b"bad", expected_sha256=None, allowed_root=tmp_path)
    assert exc_info.value.code == "SYMLINK_TARGET"
    assert real.read_bytes() == b"real"


def test_target_outside_allowed_root_is_rejected(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    target = outside / "x.txt"
    with pytest.raises(UnsafeTarget, match="outside allowed root") as exc_info:
        safe_write(target, b"x", expected_sha256=None, allowed_root=allowed)
    assert exc_info.value.code == "TARGET_OUTSIDE_ROOT"


def test_missing_allowed_root_has_stable_error_code(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    missing_root = tmp_path / "missing-root"
    with pytest.raises(UnsafeTarget) as exc_info:
        safe_write(target, b"x", expected_sha256=None, allowed_root=missing_root)
    assert exc_info.value.code == "ROOT_MISSING"


def test_non_regular_target_has_stable_error_code(tmp_path: Path) -> None:
    with pytest.raises(UnsafeTarget) as exc_info:
        fingerprint(tmp_path)
    assert exc_info.value.code == "TARGET_NOT_REGULAR_FILE"


def test_missing_parent_has_stable_error_code(tmp_path: Path) -> None:
    target = tmp_path / "missing" / "x.txt"
    with pytest.raises(UnsafeTarget) as exc_info:
        safe_write(target, b"x", expected_sha256=None, allowed_root=tmp_path)
    assert exc_info.value.code == "PARENT_MISSING"


def test_plan_and_apply_share_invalid_target_validation() -> None:
    with pytest.raises(UnsafeTarget) as plan_exc:
        plan_write("", b"x", expected_sha256=None)
    with pytest.raises(UnsafeTarget) as apply_exc:
        safe_write("", b"x", expected_sha256=None)
    assert plan_exc.value.code == "INVALID_TARGET"
    assert apply_exc.value.code == "INVALID_TARGET"


def test_uppercase_expected_hash_is_normalized(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_bytes(b"old")
    expected = fingerprint(target).sha256
    assert expected is not None

    receipt = safe_write(
        target,
        b"new",
        expected_sha256=expected.upper(),
        allowed_root=tmp_path,
    )
    assert receipt.status.value == "SUCCEEDED"
    assert receipt.expected_before_sha256 == expected


def test_invalid_expected_hash_has_stable_error_code(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_bytes(b"old")

    with pytest.raises(UnsafeTarget) as exc_info:
        safe_write(target, b"new", expected_sha256="not-a-hash", allowed_root=tmp_path)
    assert exc_info.value.code == "INVALID_EXPECTED_HASH"
    assert target.read_bytes() == b"old"


def test_non_posix_mutation_fails_before_target_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "new.txt"
    monkeypatch.setattr(core, "_is_supported_platform", lambda: False)

    with pytest.raises(UnsafeTarget) as exc_info:
        safe_write(target, b"new", expected_sha256=None, allowed_root=tmp_path)
    assert exc_info.value.code == "UNSUPPORTED_PLATFORM"
    assert exc_info.value.committed is False
    assert not target.exists()


def test_post_replace_directory_fsync_error_marks_committed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "file.txt"
    target.write_bytes(b"old")
    expected = fingerprint(target).sha256
    assert expected is not None

    def fail_fsync(_: Path) -> None:
        raise OSError("synthetic fsync failure")

    monkeypatch.setattr(core, "_fsync_directory", fail_fsync)

    with pytest.raises(SafeWriteError) as exc_info:
        safe_write(target, b"new", expected_sha256=expected, allowed_root=tmp_path)
    assert exc_info.value.code == "OS_ERROR"
    assert exc_info.value.committed is True
    assert target.read_bytes() == b"new"


def test_post_replace_fingerprint_error_marks_committed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "file.txt"
    target.write_bytes(b"old")
    expected = fingerprint(target).sha256
    assert expected is not None

    real_fingerprint = core.fingerprint
    calls = 0

    def fail_on_readback(path: str | os.PathLike[str]) -> core.Fingerprint:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise UnsafeTarget("synthetic readback target change", code="SYMLINK_TARGET")
        return real_fingerprint(path)

    monkeypatch.setattr(core, "fingerprint", fail_on_readback)

    with pytest.raises(SafeWriteError) as exc_info:
        safe_write(target, b"new", expected_sha256=expected, allowed_root=tmp_path)
    assert exc_info.value.code == "SYMLINK_TARGET"
    assert exc_info.value.committed is True
    assert target.read_bytes() == b"new"


def test_post_replace_readback_mismatch_marks_committed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "file.txt"
    target.write_bytes(b"old")
    expected = fingerprint(target).sha256
    assert expected is not None

    real_fsync = core._fsync_directory

    def fsync_then_compete(path: Path) -> None:
        real_fsync(path)
        target.write_bytes(b"newer competing state")

    monkeypatch.setattr(core, "_fsync_directory", fsync_then_compete)

    with pytest.raises(SafeWriteError) as exc_info:
        safe_write(target, b"agent result", expected_sha256=expected, allowed_root=tmp_path)
    assert exc_info.value.code == "READBACK_VERIFICATION_FAILED"
    assert exc_info.value.committed is True
    assert target.read_bytes() == b"newer competing state"


def test_preserves_mode_on_replace(tmp_path: Path) -> None:
    target = tmp_path / "script.sh"
    target.write_bytes(b"old")
    os.chmod(target, 0o750)
    old_hash = fingerprint(target).sha256
    assert old_hash is not None

    safe_write(target, b"new", expected_sha256=old_hash, allowed_root=tmp_path)
    assert (os.stat(target).st_mode & 0o777) == 0o750
