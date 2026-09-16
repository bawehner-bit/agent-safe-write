from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Callable


class WriteStatus(str, Enum):
    PLANNED = "PLANNED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class SafeWriteError(RuntimeError):
    """Base class for safe-write failures."""


class DriftDetected(SafeWriteError):
    """Raised when the target changed between planning and commit."""


class UnsafeTarget(SafeWriteError):
    """Raised when a path violates the write boundary."""


@dataclass(frozen=True)
class Fingerprint:
    exists: bool
    sha256: str | None
    size: int | None
    mode: int | None
    uid: int | None
    gid: int | None
    inode: int | None
    device: int | None
    mtime_ns: int | None

    def stable_identity(self) -> tuple[object, ...]:
        return (
            self.exists,
            self.sha256,
            self.size,
            self.mode,
            self.uid,
            self.gid,
            self.inode,
            self.device,
            self.mtime_ns,
        )


@dataclass(frozen=True)
class WriteReceipt:
    version: str
    timestamp: str
    status: WriteStatus
    target: str
    expected_before_sha256: str | None
    observed_before: Fingerprint
    observed_after: Fingerprint | None
    desired_sha256: str
    bytes_written: int
    verification: str
    reason: str | None = None

    def as_dict(self) -> dict:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.as_dict(), indent=indent, sort_keys=True)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_regular_file(path: Path) -> bytes:
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode):
        raise UnsafeTarget(f"refusing symlink target: {path}")
    if not stat.S_ISREG(st.st_mode):
        raise UnsafeTarget(f"target is not a regular file: {path}")
    with path.open("rb") as handle:
        return handle.read()


def fingerprint(path: str | os.PathLike[str]) -> Fingerprint:
    target = Path(path)
    try:
        st = os.lstat(target)
    except FileNotFoundError:
        return Fingerprint(False, None, None, None, None, None, None, None, None)

    if stat.S_ISLNK(st.st_mode):
        raise UnsafeTarget(f"refusing symlink target: {target}")
    if not stat.S_ISREG(st.st_mode):
        raise UnsafeTarget(f"target is not a regular file: {target}")

    data = _read_regular_file(target)
    return Fingerprint(
        exists=True,
        sha256=sha256_bytes(data),
        size=st.st_size,
        mode=stat.S_IMODE(st.st_mode),
        uid=st.st_uid,
        gid=st.st_gid,
        inode=st.st_ino,
        device=st.st_dev,
        mtime_ns=st.st_mtime_ns,
    )


def _validate_root(target: Path, allowed_root: Path | None) -> None:
    if allowed_root is None:
        return
    root = allowed_root.resolve(strict=True)
    parent = target.parent.resolve(strict=True)
    try:
        parent.relative_to(root)
    except ValueError as exc:
        raise UnsafeTarget(f"target is outside allowed root: {target}") from exc


def _assert_expected(observed: Fingerprint, expected_sha256: str | None) -> None:
    if expected_sha256 is None:
        if observed.exists:
            raise DriftDetected(
                "target exists but caller expected a new file; provide its current sha256 to replace it"
            )
        return
    if not observed.exists:
        raise DriftDetected("target disappeared before commit")
    if observed.sha256 != expected_sha256:
        raise DriftDetected(
            f"sha256 mismatch: expected {expected_sha256}, observed {observed.sha256}"
        )


def _write_temp_file(parent: Path, name: str, data: bytes, mode: int) -> Path:
    fd, temp_name = tempfile.mkstemp(prefix=f".{name}.", suffix=".tmp", dir=parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, mode)
        return temp_path
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        finally:
            raise


def _preserve_owner(temp_path: Path, before: Fingerprint) -> None:
    if not before.exists or before.uid is None or before.gid is None:
        return
    try:
        os.chown(temp_path, before.uid, before.gid)
    except PermissionError:
        # A non-root process normally already owns the temp file. If the target
        # has different ownership, silently changing ownership would be worse
        # than surfacing the mismatch after replacement, so fail closed.
        st = os.stat(temp_path)
        if (st.st_uid, st.st_gid) != (before.uid, before.gid):
            raise UnsafeTarget("cannot preserve target uid/gid")


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def safe_write(
    target: str | os.PathLike[str],
    data: bytes,
    *,
    expected_sha256: str | None,
    allowed_root: str | os.PathLike[str] | None = None,
    create_mode: int = 0o644,
    _after_temp_write: Callable[[Path], None] | None = None,
) -> WriteReceipt:
    """Atomically write bytes only if the target still matches caller evidence.

    `expected_sha256=None` means "create only if missing". For replacement,
    callers must supply the exact SHA-256 they observed before planning.

    The target is re-fingerprinted after the temporary file has been fully
    written and fsynced, immediately before `os.replace`. Any drift aborts the
    write. A successful return always includes a read-back hash verification.
    """

    path = Path(target)
    if not path.name or path.name in {".", ".."}:
        raise UnsafeTarget(f"invalid target: {path}")
    if not path.parent.exists():
        raise UnsafeTarget(f"parent directory does not exist: {path.parent}")

    root = Path(allowed_root) if allowed_root is not None else None
    _validate_root(path, root)

    before = fingerprint(path)
    _assert_expected(before, expected_sha256)
    desired_sha = sha256_bytes(data)
    mode = before.mode if before.exists and before.mode is not None else create_mode

    temp_path: Path | None = None
    try:
        temp_path = _write_temp_file(path.parent, path.name, data, mode)
        _preserve_owner(temp_path, before)

        if _after_temp_write is not None:
            _after_temp_write(path)

        # Final drift check: keep this immediately before replace.
        final_before = fingerprint(path)
        if final_before.stable_identity() != before.stable_identity():
            raise DriftDetected("target changed after planning; write aborted")
        _assert_expected(final_before, expected_sha256)

        os.replace(temp_path, path)
        temp_path = None
        _fsync_directory(path.parent)

        after = fingerprint(path)
        if not after.exists or after.sha256 != desired_sha:
            raise SafeWriteError("read-back verification failed after atomic replace")

        return WriteReceipt(
            version="agent-safe-write/0.1",
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=WriteStatus.SUCCEEDED,
            target=str(path),
            expected_before_sha256=expected_sha256,
            observed_before=before,
            observed_after=after,
            desired_sha256=desired_sha,
            bytes_written=len(data),
            verification="read-back sha256 matched desired content after os.replace + directory fsync",
        )
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def plan_write(
    target: str | os.PathLike[str],
    data: bytes,
    *,
    expected_sha256: str | None,
    allowed_root: str | os.PathLike[str] | None = None,
) -> WriteReceipt:
    path = Path(target)
    if not path.parent.exists():
        raise UnsafeTarget(f"parent directory does not exist: {path.parent}")
    _validate_root(path, Path(allowed_root) if allowed_root is not None else None)
    before = fingerprint(path)
    _assert_expected(before, expected_sha256)
    return WriteReceipt(
        version="agent-safe-write/0.1",
        timestamp=datetime.now(timezone.utc).isoformat(),
        status=WriteStatus.PLANNED,
        target=str(path),
        expected_before_sha256=expected_sha256,
        observed_before=before,
        observed_after=None,
        desired_sha256=sha256_bytes(data),
        bytes_written=0,
        verification="not executed; plan only",
    )
