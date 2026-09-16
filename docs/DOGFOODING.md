# Dogfooding evidence

This document records first-party use of `agent-safe-write` in a real consumer workflow.

It is deliberately **not** presented as third-party adoption. The consumer repository is private and maintained by the same project author. The purpose of this evidence is to show that the package is used outside its own test suite and that its safety contract is exercised by a real CI write path.

## Consumer scenario

On 2026-09-16, a private multi-agent operations repository integrated the public `agent-safe-write` package into a GitHub Actions contract workflow.

The consumer pins the exact public project commit:

```text
ffe08d34dc8ca4686a2d9f5ff3963568ccfdf097
```

The package is installed from that immutable commit archive. The protected operation is the finalization of a CI-generated JSON contract-evidence artifact.

Instead of directly calling `Path.write_text(...)`, the consumer now:

1. fingerprints the current evidence file;
2. supplies that SHA-256 as the expected precondition;
3. calls `safe_write(...)` with the report directory as the allowed root;
4. emits the resulting receipt; and
5. treats the write as successful only when the package returns `SUCCEEDED` after read-back verification.

## Consumer tests

The private consumer adds two focused integration tests in addition to its existing suite.

### Verified normal write

The test creates an evidence file, fingerprints it, performs a replacement through `safe_write`, and verifies:

- status is `SUCCEEDED`;
- the desired bytes are present;
- `observed_after` exists; and
- the read-back SHA-256 equals the desired content hash.

### Stale observation

The second test fingerprints an initial evidence file, simulates a different writer updating it, and then attempts to commit using the stale hash.

The expected behavior is verified:

- the operation raises `DriftDetected`;
- the stable error code is `DRIFT_DETECTED`; and
- the newer writer's bytes remain unchanged.

This is the failure mode the project is specifically designed to prevent.

## CI result

The integration has run in GitHub Actions as part of the consumer's existing contract suite. A successful contract run installed the public package, passed the two dedicated dogfooding tests alongside the existing consumer tests, executed the real evidence finalizer, and produced a `SUCCEEDED` receipt whose post-write SHA-256 matched the desired content hash.

The dependency is pinned to immutable source content rather than a moving branch. This also keeps the consumer's container build independent of a local Git executable.

## Privacy and reproducibility

The consumer repository is private, so its source and CI logs are not linked from this public repository. No claim of independent external adoption is made here.

The public package test suite covers the same core safety properties, and the integration pattern is intentionally small enough to reproduce in any consumer that writes generated artifacts:

```python
from agent_safe_write import fingerprint, safe_write

observed = fingerprint(report_path)
receipt = safe_write(
    report_path,
    desired_bytes,
    expected_sha256=observed.sha256 if observed.exists else None,
    allowed_root=report_path.parent,
)
assert receipt.status.value == "SUCCEEDED"
```

For stale-write behavior, mutate the target after the fingerprint and before calling `safe_write`; the operation must fail closed instead of clobbering the newer state.

## What this evidence does and does not show

It shows that `agent-safe-write` is already consumed by a separate real repository and protects a non-demo CI artifact write.

It does not show broad ecosystem adoption, independent users, or production deployment. Those are future adoption milestones and should be measured separately if they occur.
