# Changelog

## 0.1.0 - Unreleased

Initial public release candidate:

- drift-aware compare-and-swap file writes;
- temp-file and directory fsync;
- final fingerprint recheck immediately before atomic replace;
- post-write read-back SHA-256 verification;
- symlink and allowed-root guards;
- CLI plans, applies, fingerprints, and JSON receipts;
- stable machine-readable error codes for failure receipts;
- regression tests for stale plans, concurrent drift, and safety error classes.
