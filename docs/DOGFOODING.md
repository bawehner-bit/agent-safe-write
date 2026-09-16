# Dogfooding evidence

This document records first-party use of `agent-safe-write` in a real consumer workflow.

It is deliberately **not** presented as third-party adoption. The consumer repository is private and maintained by the same project author. The purpose of this evidence is to show that the package is used outside its own test suite and that its verification path is exercised by a real CI artifact write.

## Consumer scenario

On 2026-09-16, a private multi-agent operations repository integrated the public `agent-safe-write` package into a GitHub Actions contract workflow.

The consumer originally pinned the exact public project commit:

```text
ffe08d34dc8ca4686a2d9f5ff3963568ccfdf097
```

The package was installed from immutable public source content. The protected operation is the finalization of a CI-generated JSON contract-evidence artifact.

Instead of directly calling `Path.write_text(...)`, the consumer now:

1. fingerprints the current evidence file;
2. supplies that SHA-256 as the expected precondition;
3. calls `safe_write(...)` with the report directory as the allowed root;
4. emits the resulting receipt; and
5. treats the write as successful only when the package returns `SUCCEEDED` after read-back verification.

## What the real CI path demonstrates

The real CI job is a fresh, isolated workflow and does not normally have competing writers for this artifact. Its practical use of `agent-safe-write` therefore demonstrates:

- package consumption from a separate repository;
- a real non-demo artifact finalized through the library;
- a late pre-commit recheck in the write path;
- directory fsync and read-back verification before `SUCCEEDED`; and
- machine-readable outcome handling.

It does **not** demonstrate that the library prevents every concurrent lost update. In particular, the replacement-path final-check-to-rename race documented in the threat model remains possible.

## Consumer tests

The private consumer adds two focused integration tests in addition to its existing suite.

### Verified normal write

The test creates an evidence file, fingerprints it, performs a replacement through `safe_write`, and verifies:

- status is `SUCCEEDED`;
- the desired bytes are present;
- `observed_after` exists; and
- the read-back SHA-256 equals the desired content hash.

### Stale observation before the call

The second test fingerprints an initial evidence file, simulates a different writer updating it, and then calls `safe_write` using the stale hash.

The verified behavior is:

- the operation raises `DriftDetected`;
- the stable error code is `DRIFT_DETECTED`; and
- the newer bytes remain unchanged.

This demonstrates stale-precondition rejection when the drift is already visible before the library stages and commits a replacement. It is **not** a test of the final fingerprint-to-rename race window.

## CI result

According to the project author's private CI run, the integration installed the public package, passed the two dedicated dogfooding tests alongside the existing consumer tests, executed the real evidence finalizer, and reported a `SUCCEEDED` receipt whose post-write SHA-256 matched the desired content hash.

Because the consumer repository is private, those CI logs are not independently linkable from this public repository. This statement is therefore first-party reported evidence, not an externally verifiable adoption claim.

The dependency was pinned to immutable source content rather than a moving branch. This also kept the consumer's container build independent of a local Git executable.

## Privacy and reproducibility

The consumer repository is private, so its source and CI logs are not linked from this public repository. No claim of independent external adoption is made here.

The integration pattern is intentionally small enough to reproduce in another consumer that writes generated artifacts:

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
assert receipt.committed is True
```

For stale-precondition behavior, mutate the target after the caller fingerprints it and before calling `safe_write`; the operation should reject that stale expected hash. This does not close the separate final-check-to-rename window described in `docs/THREAT_MODEL.md`.

## What this evidence does and does not show

It shows that `agent-safe-write` is consumed by a separate real repository and used to finalize a non-demo CI artifact with read-back verification.

It does not show broad ecosystem adoption, independent users, production deployment, or elimination of all concurrent replacement races. Those are separate future milestones and should only be claimed if independently demonstrated.
