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
    """Base class for safe-write failures with a stable machine-readable code."""

    default_code = "SAFE_WRITE_ERROR"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        committed: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code or self.default_code
        self.committed = committed


class DriftDetected(SafeWriteError):
    """Raised when the target changed before commit."""

    default_code = "DRIFT_DETECTED"


class UnsafeTarget(SafeWriteError):
    """Raised when a path violates the write boundary."""

    default_code = "UNSAFE_TARGET"


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
    committed: bool
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


def _is_supported_platform() -> bool:
    return os.name == "posix"


def _require_supported_platform() -> None:
    if not _is_supported_platform():
        raise UnsafeTarget(
            "agent-safe-write v0.1 supports mutation only on POSIX platforms",
            code="UNSUPPORTED_PLATFORM",
        )


def _read_regular_file(path: Path) -> bytes:
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode):
        raise UnsafeTarget(f"refusing symlink target: {path}", code="SYMLINK_TARGET")
    if not stat.S_ISREG(st.st_mode):
        raise UnsafeTarget(
            f"target is not a regular file: {path}", code="TARGET_NOT_REGULAR_FILE"
        )
    with path.open("rb") as handle:
        return handle.read()


def fingerprint(path: str | os.PathLike[str]) -> Fingerprint:
    target = Path(path)
    try:
        st = os.lstat(target)
    except FileNotFoundError:
        return Fingerprint(False, None, None, None, None, None, None, None, None)

    if stat.S_ISLNK(st.st_mode):
        raise UnsafeTarget(f"refusing symlink target: {target}", code="SYMLINK_TARGET")
    if not stat.S_ISREG(st.st_mode):
        raise UnsafeTarget(
            f"target is not a regular file: {target}", code="TARGET_NOT_REGULAR_FILE"
        )

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


def _validate_target_shape(target: Path) -> None:
    if not target.name or target.name in {".", ".."}:
        raise UnsafeTarget(f"invalid target: {target}", code="INVALID_TARGET")
    if not target.parent.exists():
        raise UnsafeTarget(
            f"parent directory does not exist: {target.parent}", code="PARENT_MISSING"
        )


def _validate_root(target: Path, allowed_root: Path | None) -> None:
    if allowed_root is None:
        return
    try:
        root = allowed_root.resolve(strict=True)
    except FileNotFoundError as exc:
        raise UnsafeTarget(
            f"allowed root does not exist: {allowed_root}", code="ROOT_MISSING"
        ) from exc
    try:
        parent = target.parent.resolve(strict=True)
    except FileNotFoundError as exc:
        raise UnsafeTarget(
            f"parent directory does not exist: {target.parent}", code="PARENT_MISSING"
        ) from exc
    try:
        parent.relative_to(root)
    except ValueError as exc:
        raise UnsafeTarget(
            f"target is outside allowed root: {target}", code="TARGET_OUTSIDE_ROOT"
        ) from exc


def _normalize_expected_sha256(expected_sha256: str | None) -> str | None:
    if expected_sha256 is None:
        return None
    normalized = expected_sha256.lower()
    if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
        raise UnsafeTarget(
            "expected_sha256 must be exactly 64 hexadecimal characters",
            code="INVALID_EXPECTED_HASH",
        )
    return normalized


def _coerce_data(data: bytes) -> bytes:
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("data must be bytes-like")
    return bytes(data)


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


def _write_temp_file(parent: Path, name: str, data: bytes) -> Path:
    fd, temp_name = tempfile.mkstemp(prefix=f".{name}.", suffix=".tmp", dir=parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
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
        st = os.stat(temp_path)
        if (st.st_uid, st.st_gid) != (before.uid, before.gid):
            raise UnsafeTarget(
                "cannot preserve target uid/gid", code="OWNERSHIP_PRESERVATION_FAILED"
            )


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _raise_post_commit(exc: Exception) -> None:
    if isinstance(exc, SafeWriteError):
        exc.committed = True
        raise exc
    if isinstance(exc, OSError):
        raise SafeWriteError(str(exc), code="OS_ERROR", committed=True) from exc
    raise SafeWriteError(str(exc), code="INTERNAL_ERROR", committed=True) from exc


def safe_write(
    target: str | os.PathLike[str],
    data: bytes,
    *,
    expected_sha256: str | None,
    allowed_root: str | os.PathLike[str] | None = None,
    create_mode: int = 0o644,
    _after_temp_write: Callable[[Path], None] | None = None,
) -> WriteReceipt:
    """Write bytes with a late pre-commit recheck and mandatory read-back.

    `expected_sha256=None` means create only if missing. On POSIX this path uses
    an atomic hard-link create-if-absent operation, so an already-created target
    is not overwritten.

    Replacement is deliberately *not* described as atomic compare-and-swap.
    The target is re-fingerprinted immediately before `os.replace`, but another
    writer can still land in the final-check-to-rename window. A successful
    return always includes read-back SHA-256 verification of the resulting path.
    """

    _require_supported_platform()
    path = Path(target)
    _validate_target_shape(path)
    payload = _coerce_data(data)
    expected = _normalize_expected_sha256(expected_sha256)

    root = Path(allowed_root) if allowed_root is not None else None
    _validate_root(path, root)

    before = fingerprint(path)
    _assert_expected(before, expected)
    desired_sha = sha256_bytes(payload)
    mode = before.mode if before.exists and before.mode is not None else create_mode

    temp_path: Path | None = None
    try:
        temp_path = _write_temp_file(path.parent, path.name, payload)
        _preserve_owner(temp_path, before)
        os.chmod(temp_path, mode)

        if _after_temp_write is not None:
            _after_temp_write(path)

        final_before = fingerprint(path)
        if final_before.stable_identity() != before.stable_identity():
            raise DriftDetected("target changed after planning; write aborted")
        _assert_expected(final_before, expected)

        if expected is None:
            try:
                os.link(temp_path, path)
            except FileExistsError as exc:
                raise DriftDetected(
                    "target appeared before atomic create; write aborted"
                ) from exc
            committed = True
            commit_description = "atomic create-if-absent link"
        else:
            os.replace(temp_path, path)
            committed = True
            commit_description = "atomic rename"
            temp_path = None

        try:
            if expected is None:
                temp_path.unlink()
                temp_path = None

            _fsync_directory(path.parent)

            after = fingerprint(path)
            if not after.exists or after.sha256 != desired_sha:
                raise SafeWriteError(
                    "read-back verification failed after commit",
                    code="READBACK_VERIFICATION_FAILED",
                    committed=True,
                )
        except Exception as exc:
            _raise_post_commit(exc)

        return WriteReceipt(
            version="agent-safe-write/0.1",
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=WriteStatus.SUCCEEDED,
            target=str(path),
            expected_before_sha256=expected,
            observed_before=before,
            observed_after=after,
            desired_sha256=desired_sha,
            bytes_written=len(payload),
            committed=committed,
            verification=(
                f"read-back sha256 matched desired content after {commit_description} "
                "+ directory fsync"
            ),
        )
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def plan_write(
    target: str | os.PathLike[str],
    data: bytes,
    *,
    expected_sha256: str | None,
    allowed_root: str | os.PathLike[str] | None = None,
) -> WriteReceipt:
    _require_supported_platform()
    path = Path(target)
    _validate_target_shape(path)
    payload = _coerce_data(data)
    expected = _normalize_expected_sha256(expected_sha256)
    _validate_root(path, Path(allowed_root) if allowed_root is not None else None)
    before = fingerprint(path)
    _assert_expected(before, expected)
    return WriteReceipt(
        version="agent-safe-write/0.1",
        timestamp=datetime.now(timezone.utc).isoformat(),
        status=WriteStatus.PLANNED,
        target=str(path),
        expected_before_sha256=expected,
        observed_before=before,
        observed_after=None,
        desired_sha256=sha256_bytes(payload),
        bytes_written=0,
        committed=False,
        verification="not executed; plan only",
    )
