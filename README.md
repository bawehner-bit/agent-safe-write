# Agent Safe Write

**A file write is not successful just because an agent says it wrote the file.**

`agent-safe-write` is a small, dependency-free Python library and CLI for drift-aware, verified filesystem mutations by AI coding agents and automation on POSIX systems.

It is designed for workflows where an agent observes a file, plans a change, and later commits bytes while wanting a deterministic precondition check and a verified postcondition.

## What it does

For one regular-file write on a local POSIX filesystem, `agent-safe-write`:

1. fingerprints the target state the caller claims to have observed;
2. rejects symlink targets and optional out-of-scope paths on a best-effort path check;
3. writes new bytes to a temporary file in the same directory;
4. flushes and `fsync`s the temporary file;
5. re-fingerprints the target immediately before commit and aborts if drift is visible then;
6. commits a replacement with an atomic rename, or creates a missing file with atomic create-if-absent semantics;
7. `fsync`s the containing directory; and
8. reads the target back and verifies the desired SHA-256 before returning `SUCCEEDED`.

The important rule is:

> **No verified postcondition, no `SUCCEEDED` claim.**

## Important concurrency limitation

Replacement is **not atomic compare-and-swap**. The implementation performs a late compare-then-swap: it fingerprints the target, stages the new bytes, fingerprints again, then calls `os.replace`.

A different writer that changes the target **after the final fingerprint and before the rename** can still be overwritten. The project includes a regression test that intentionally demonstrates this limitation.

So the replacement guarantee is narrower:

> Drift visible before the final recheck is rejected. Drift landing in the final-check-to-rename window is not detectable with this portable path-based design.

The create-if-missing path is stronger: on POSIX it uses atomic create-if-absent semantics so two racing creators do not silently overwrite each other.

## Why agents need this

Optimistic agent workflows often treat a successful tool invocation as proof that the intended state exists. That is weaker than a verified outcome. Timeouts, stale observations, partial writes, incorrect execution context, and post-write failures can all make `"done"` a false statement.

The write contract is therefore:

```text
observed state -> expected hash -> staged bytes -> late recheck -> commit -> read-back proof
```

It is intentionally not an agent framework and does not call an LLM.

## 60-second quick start

```bash
python -m pip install -e .

printf 'before\n' > target.txt
python -m agent_safe_write fingerprint target.txt
# Copy the reported sha256.

printf 'after\n' > desired.txt
python -m agent_safe_write plan target.txt --from-file desired.txt --expect <SHA256>
python -m agent_safe_write apply target.txt --from-file desired.txt --expect <SHA256>
```

A successful apply emits a machine-readable receipt:

```json
{
  "status": "SUCCEEDED",
  "committed": true,
  "target": "target.txt",
  "verification": "read-back sha256 matched desired content after atomic rename + directory fsync"
}
```

If the target changed after the caller observed it and that change is visible before the final recheck, the command exits without committing and emits `NEEDS_REVIEW`.

## Failure receipts

Failures are machine-readable. Callers should branch on `status`, `code`, and `committed`, not parse the human-readable `reason` string.

```json
{
  "status": "NEEDS_REVIEW",
  "code": "DRIFT_DETECTED",
  "committed": false,
  "reason": "sha256 mismatch: expected ..., observed ..."
}
```

A critical distinction is that **`FAILED` does not always mean the target is unchanged**. If replacement has already happened and a later directory `fsync` or read-back check fails, the error payload carries:

```json
{
  "status": "FAILED",
  "committed": true,
  "code": "OS_ERROR"
}
```

That means the mutation crossed the commit point, but the library could not verify or durably confirm the final state.

Current stable codes include:

- `DRIFT_DETECTED`
- `SYMLINK_TARGET`
- `TARGET_NOT_REGULAR_FILE`
- `TARGET_OUTSIDE_ROOT`
- `PARENT_MISSING`
- `ROOT_MISSING`
- `INVALID_TARGET`
- `INVALID_EXPECTED_HASH`
- `UNSUPPORTED_PLATFORM`
- `OWNERSHIP_PRESERVATION_FAILED`
- `READBACK_VERIFICATION_FAILED`
- `OS_ERROR`
- `INTERNAL_ERROR`
- `USAGE_ERROR`

New codes may be added in minor releases. Existing code meanings should not be silently repurposed.

## Python API

```python
from agent_safe_write import fingerprint, safe_write

before = fingerprint("config.toml")
receipt = safe_write(
    "config.toml",
    b"enabled = true\n",
    expected_sha256=before.sha256,
    allowed_root=".",
)
print(receipt.status)       # SUCCEEDED only after read-back verification
print(receipt.committed)    # True on every successful write
```

To create a new file, pass `expected_sha256=None`; creation fails if another writer creates that path first.

## Real dogfooding

The package is consumed by a separate private multi-agent operations repository maintained by the project author. There it finalizes a CI-generated contract-evidence artifact and verifies the resulting bytes via the same read-back path used by the public library.

That real CI path does not normally have competing writers, so its practical benefit there is verified finalization rather than demonstrated race prevention. A dedicated consumer test separately exercises stale-hash rejection.

This is disclosed as **first-party dogfooding, not third-party adoption**. See [`docs/DOGFOODING.md`](docs/DOGFOODING.md) for the sanitized evidence and limitations.

## Threat model and non-claims

This library reduces some accidental stale-write and false-success failure modes for cooperative local automation. It is **not** a sandbox, permission system, malware defense, distributed lock, atomic compare-and-swap primitive, or cryptographic attestation service. A malicious process with direct filesystem access can bypass it, and a cooperative writer landing in the final-check-to-rename window can still be overwritten. See [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md).

## Design principles

- **Reject observable drift.** If the target differs at the final recheck, the mutation does not commit.
- **Success is a verified state, not a tool response.**
- **Expose commit state explicitly.** Post-commit failures carry `committed=true`.
- **No hidden network or model calls.** The core is Python standard library only.
- **Small trust boundary.** One file, one expected state, one commit path.
- **Machine-readable outcomes.** Agent runtimes can distinguish `SUCCEEDED`, `FAILED`, and `NEEDS_REVIEW` without parsing prose.

## Current scope

v0.1 supports mutation only on POSIX systems and rejects `plan`/`apply` on non-POSIX platforms before any write. The roadmap includes Windows semantics, fd-based path hardening, pluggable postcondition verifiers, patch-scoped writes, and adapters for common agent runtimes.

The current symlink and `allowed_root` checks are path-based preflight checks, not a sandbox. Parent-directory replacement races and lstat/open races are documented limitations for v0.1.

See [`ROADMAP.md`](ROADMAP.md), [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md), and [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Development

```bash
python -m pip install -e .
python -m pytest
```

The tests include deterministic drift injection, an explicit final-window lost-update limitation test, racing create-if-absent writers, post-commit failure semantics, symlink rejection, allowed-root checks, mode preservation, CLI receipts, stable error codes, and verified read-back.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
