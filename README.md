# Agent Safe Write

**A file write is not successful just because an agent says it wrote the file.**

`agent-safe-write` is a small, dependency-free Python library and CLI for drift-aware, atomic filesystem mutations by AI coding agents and automation.

It addresses a narrow operational failure mode: an agent reads a file, plans a change, the world changes underneath it, and the agent still overwrites the target or reports success without verifying the resulting state.

## What it guarantees

For one regular-file write on a local filesystem, `agent-safe-write`:

1. fingerprints the exact target state the caller claims to have observed;
2. rejects symlink targets and optional out-of-scope paths;
3. writes new bytes to a temporary file in the same directory;
4. flushes and `fsync`s the temporary file;
5. **re-fingerprints the target immediately before `os.replace`** and aborts on drift;
6. replaces atomically;
7. `fsync`s the containing directory; and
8. reads the target back and verifies the desired SHA-256 before returning `SUCCEEDED`.

The important rule is simple:

> **No verified postcondition, no success claim.**

## Why agents need this

Optimistic agent workflows often treat a successful tool invocation as proof that the intended state exists. That is weaker than a verified outcome. Timeouts, concurrent edits, stale observations, symlink surprises, partial writes, and incorrect execution context can all make `"done"` a false statement.

This project turns a write into an explicit compare-and-swap style contract:

```text
observed state -> expected hash -> staged bytes -> final drift check -> atomic replace -> read-back proof
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
  "target": "target.txt",
  "verification": "read-back sha256 matched desired content after os.replace + directory fsync"
}
```

If the target changed after the agent observed it, the command exits without replacing it and emits `NEEDS_REVIEW`.

## Failure receipts

Failures are also machine-readable. Callers should branch on `status` and `code`, not parse the human-readable `reason` string.

```json
{
  "status": "NEEDS_REVIEW",
  "code": "DRIFT_DETECTED",
  "reason": "sha256 mismatch: expected ..., observed ..."
}
```

Current stable codes include:

- `DRIFT_DETECTED`
- `SYMLINK_TARGET`
- `TARGET_NOT_REGULAR_FILE`
- `TARGET_OUTSIDE_ROOT`
- `PARENT_MISSING`
- `INVALID_TARGET`
- `OWNERSHIP_PRESERVATION_FAILED`
- `READBACK_VERIFICATION_FAILED`
- `OS_ERROR`

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
print(receipt.status)  # SUCCEEDED only after read-back verification
```

To create a new file, pass `expected_sha256=None`; creation fails if the file already exists.

## Real dogfooding

The package is already consumed by a separate private multi-agent operations repository maintained by the project author. There it protects the final write of a CI-generated contract-evidence artifact. Consumer tests verify both a normal `SUCCEEDED` write and a stale-hash attempt that returns `DRIFT_DETECTED` without overwriting the newer state.

This is disclosed as **first-party dogfooding, not third-party adoption**. See [`docs/DOGFOODING.md`](docs/DOGFOODING.md) for the sanitized evidence and limitations.

## Threat model and non-claims

This library reduces accidental lost updates and false-success reporting for cooperative local automation. It is **not** a sandbox, permission system, malware defense, distributed lock, or cryptographic attestation service. A malicious process with direct filesystem access can bypass it. See [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md).

## Design principles

- **Fail closed on drift.** A stale plan never silently wins.
- **Success is a verified state, not a tool response.**
- **No hidden network or model calls.** The core is Python standard library only.
- **Small trust boundary.** One file, one expected state, one atomic commit.
- **Machine-readable outcomes.** Agent runtimes can distinguish `SUCCEEDED`, `FAILED`, and `NEEDS_REVIEW` without parsing prose.

## Current scope

v0.1 covers local regular-file writes on POSIX-like systems. The roadmap includes Windows semantics, pluggable postcondition verifiers, patch-scoped writes, and adapters for common agent runtimes.

See [`ROADMAP.md`](ROADMAP.md) and [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Development

```bash
python -m pip install -e .
python -m pytest
```

The tests include target drift after the temp file is fsynced, stale hashes, symlink rejection, allowed-root enforcement, mode preservation, CLI receipts, stable error codes, and verified read-back.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
