# Threat model

## Security property

`agent-safe-write` makes a narrow claim: when `safe_write()` returns `SUCCEEDED`, the library crossed its commit point, `fsync`ed the containing directory, then read the target path back and observed the desired SHA-256.

For replacement, the library also refuses the mutation when the target fingerprint differs between the initial observation and the final pre-rename recheck.

This is **not atomic compare-and-swap** for replacement. A writer that changes the target after the final fingerprint and before `os.replace` can still be overwritten.

For create-if-missing, v0.1 uses an atomic POSIX hard-link create-if-absent step. If the destination appears first, the create fails with `DRIFT_DETECTED` rather than overwriting it.

## In scope

- stale observations that are visible at the final pre-commit recheck;
- deterministic rejection of a mismatched expected SHA-256;
- two writers racing to create the same previously missing path;
- partial temp-file writes or process failures before commit;
- accidental writes outside an explicitly supplied root as a preflight misconfiguration check;
- symlink targets as a best-effort path check;
- false completion claims caused by skipping post-write verification;
- explicit reporting of whether an error happened before or after the commit point.

## Out of scope

- preventing replacement-path lost updates in the final-recheck-to-rename window;
- malicious local processes that can bypass the library;
- parent-directory replacement races;
- race-free symlink rejection with fd-based `O_NOFOLLOW` semantics;
- using `allowed_root` as an enforced sandbox boundary;
- kernel or filesystem compromise;
- network/distributed filesystems with semantics weaker than assumed by local POSIX filesystems;
- authorization, sandboxing, or user identity;
- semantic correctness of the new file contents;
- cryptographic non-repudiation;
- multi-file transactions;
- rollback after a committed write;
- preservation of hardlink aliasing when replacing a path.

## Replacement TOCTOU boundary

Replacement uses a late compare-then-swap sequence:

1. fingerprint the target;
2. stage and `fsync` the candidate bytes;
3. fingerprint the target again;
4. call `os.replace`.

The interval between step 3 and step 4 cannot be closed with the current portable path-based design. The final fingerprint itself reads and hashes the target, so the effective race window is not guaranteed to be "small"; it includes the full re-read plus scheduler latency before rename.

The repository contains a regression test that deliberately injects a competing write at the `os.replace` call and demonstrates that the competing update can be lost. That test documents the boundary rather than claiming to eliminate it.

## Path checks

Symlink and root checks in v0.1 are path-based preflight checks. `fingerprint()` currently performs `lstat` followed by a normal open, so a path swap between those operations is possible. `allowed_root` resolves the parent during validation but is not enforced through a retained directory file descriptor at commit time.

These checks are useful against accidental misuse by cooperative automation, but they are not a sandbox or security boundary against a process that can mutate directory entries concurrently.

## Platform boundary

Mutation APIs (`plan_write` and `safe_write`) reject non-POSIX platforms before staging or changing the target. Full Windows mutation semantics are not claimed in v0.1.

## Metadata

For normal replacement, v0.1 attempts to preserve uid/gid and then applies the observed permission mode to the staged file before commit. Hardlink aliasing is not preserved: replacing one hardlinked pathname gives that name a new inode while other links continue to reference the old inode.

## Commit and failure semantics

The commit point is:

- successful destination link creation for create-if-missing; or
- successful `os.replace` for replacement.

After that point, later operations can still fail. Errors therefore carry a boolean `committed` field/property:

- `committed=false`: the library did not cross its commit point;
- `committed=true`: the target mutation occurred, but durability or read-back verification did not complete successfully.

`FAILED` must therefore not be interpreted as "target unchanged" without checking `committed`.

## Verification semantics

`SUCCEEDED` is emitted only after:

1. the commit point was crossed;
2. the containing directory was `fsync`ed; and
3. the target path was read back with SHA-256 equal to the desired bytes.

This verifies the observed postcondition at read-back time. It does not prevent another writer from changing the file immediately afterward.
