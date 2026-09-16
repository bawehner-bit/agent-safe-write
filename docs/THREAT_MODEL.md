# Threat model

## Security property

`agent-safe-write` makes one narrow claim: when `safe_write()` returns `SUCCEEDED`, the target was atomically replaced from an explicitly observed state and the resulting bytes were read back with the expected SHA-256.

It also refuses a normal replacement when the target's fingerprint changes between initial observation and the final pre-replace check.

## In scope

- stale agent observations;
- concurrent cooperative file edits;
- partial temp-file writes or process failures before replace;
- accidental writes outside an explicitly supplied root;
- symlink targets;
- false completion claims caused by skipping post-write verification.

## Out of scope

- malicious local processes that can bypass the library;
- kernel or filesystem compromise;
- network/distributed filesystems with semantics weaker than assumed by local POSIX filesystems;
- authorization, sandboxing, or user identity;
- semantic correctness of the new file contents;
- cryptographic non-repudiation;
- multi-file transactions;
- rollback after a verified replace.

## TOCTOU boundary

There is necessarily a small race between the final fingerprint and `os.replace`. The implementation deliberately places the final check immediately before replacement and performs no unrelated work in between. Stronger protection would require filesystem/platform primitives with different portability tradeoffs.

## Metadata

Existing file mode and, where permitted, uid/gid are preserved on replacement. If ownership cannot be preserved safely, the write fails closed rather than silently changing ownership.

## Verification semantics

A successful tool call is not sufficient. `SUCCEEDED` is emitted only after:

1. atomic replacement;
2. directory fsync; and
3. read-back SHA-256 equality with the desired content.
