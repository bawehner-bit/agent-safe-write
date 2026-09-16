# Changelog

## 0.1.0 - Unreleased

Initial public release candidate:

- late target fingerprint recheck before replacement commit;
- atomic POSIX create-if-absent path for new files;
- atomic rename for replacement, explicitly documented as **not** atomic compare-and-swap;
- temp-file and directory fsync;
- post-write read-back SHA-256 verification;
- explicit `committed` semantics for post-commit failures;
- POSIX-only mutation guard before staging or target mutation;
- symlink and allowed-root preflight guards with documented path-race limitations;
- CLI plans, applies, fingerprints, JSON receipts, and machine-readable usage/internal errors;
- stable machine-readable error codes for failure receipts;
- deterministic stale-precondition/drift-injection tests;
- a documented negative test for the unavoidable final-recheck-to-rename race window;
- racing create-if-absent and post-commit failure regression tests;
- first-party dogfooding in a separate private CI evidence workflow, disclosed as non-independent adoption.
