# Design

## The boundary

`agent-safe-write` sits at the mutation boundary, not at the prompt or reporting layer.

The caller supplies:

- the bytes it wants to become authoritative; and
- evidence of the state it actually observed (`expected_sha256`).

For replacement, the library rechecks that evidence late, immediately before rename. This reduces the stale-write window but does not eliminate it.

## State machine

```text
OBSERVED
  |
  v
PLANNED -- target mismatch --> NEEDS_REVIEW (committed=false)
  |
  v
STAGED (temp file written + fsynced)
  |
  +-- final visible drift --> NEEDS_REVIEW (committed=false)
  |
  v
COMMIT
  |  replacement: os.replace (atomic rename, not atomic CAS)
  |  creation: atomic create-if-absent link
  v
COMMITTED
  |
  +-- durability/read-back error --> FAILED (committed=true)
  |
  v
DURABLE (directory fsync)
  |
  v
VERIFIED (read-back sha256)
  |
  v
SUCCEEDED (committed=true)
```

The last transitions matter: crossing the commit point is not treated as proof that durability and verification succeeded.

## Replacement is compare-then-swap, not compare-and-swap

A common optimistic write pattern checks the target before doing expensive staging work. This implementation stages and fsyncs the candidate first, then re-fingerprints the authoritative target immediately before `os.replace`.

That late recheck catches drift that is already visible. It cannot make `os.replace` conditional on the fingerprint that was just observed. Another writer can still change the destination after the final fingerprint and before rename, and that update can be overwritten.

The test suite contains an explicit limitation test that injects a competing update at the rename boundary and demonstrates this behavior.

## Creation is different

When `expected_sha256=None`, the caller means "create only if missing". On POSIX, v0.1 commits this path with an atomic hard-link create-if-absent operation. If another creator wins first, the destination link fails with `EEXIST` and the library returns `DRIFT_DETECTED` instead of replacing the winner.

## Why `committed` is explicit

After rename/link succeeds, directory `fsync` or read-back can still fail. Reporting only `FAILED` would be ambiguous because the target may already have changed.

Both API errors and CLI error payloads therefore expose `committed`:

- `false` means the library did not cross its commit point;
- `true` means it did, but post-commit confirmation failed.

## Why the receipt is secondary

The JSON receipt is useful to an agent runtime, but it is not a security attestation. The important properties are the deterministic checks and the explicit outcome semantics. A `SUCCEEDED` receipt records a read-back observation; it does not prove the file remained unchanged afterward.

## Current path-safety boundary

v0.1 uses path-based symlink and allowed-root checks. These checks reduce accidental misuse, but they are not race-free against concurrent directory-entry replacement and are not a sandbox. fd-based `O_NOFOLLOW`/`dir_fd` hardening is a later roadmap item.

## Current portability boundary

v0.1 mutation is intentionally POSIX-only. `plan_write` and `safe_write` reject non-POSIX platforms before staging or changing a target. Atomic replacement, ownership, mode bits, directory fsync, and Windows sharing semantics differ enough that claiming cross-platform equivalence before dedicated implementation and tests would be misleading.
