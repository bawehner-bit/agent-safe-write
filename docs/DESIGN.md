# Design

## The boundary

`agent-safe-write` sits at the mutation boundary, not at the prompt or reporting layer.

The caller supplies two things:

- the bytes it wants to become authoritative; and
- evidence of the state it actually observed (`expected_sha256`).

The library commits only if that evidence is still current.

## State machine

```text
OBSERVED
  |
  v
PLANNED -- target mismatch --> NEEDS_REVIEW
  |
  v
STAGED (temp file written + fsynced)
  |
  +-- final target drift --> NEEDS_REVIEW
  |
  v
REPLACED (atomic os.replace)
  |
  v
DURABLE (directory fsync)
  |
  v
VERIFIED (read-back sha256)
  |
  v
SUCCEEDED
```

The last transition matters: replacement is not treated as proof of the resulting state.

## Why the final recheck is late

A common compare-and-swap implementation checks the target before doing expensive staging work. That leaves a larger window in which another actor can update the file. This implementation stages and fsyncs the candidate first, then re-fingerprints the authoritative target immediately before `os.replace`.

## Why the receipt is secondary

The JSON receipt is useful to an agent runtime, but it is not the primary safety mechanism. The important property is that an unsafe or stale mutation is not committed. Evidence is emitted from that deterministic control path rather than used as a substitute for it.

## Current portability boundary

v0.1 is intentionally POSIX-oriented. Atomic replacement, ownership, mode bits, directory fsync, and Windows sharing semantics differ enough that claiming cross-platform equivalence before dedicated tests would be misleading.
