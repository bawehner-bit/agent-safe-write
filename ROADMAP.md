# Roadmap

## v0.1 - Local verified write core

- [x] exact SHA-256 precondition for replacement planning
- [x] late drift recheck immediately before replacement rename
- [x] atomic POSIX create-if-absent path for missing files
- [x] temp-file fsync and atomic rename for replacement
- [x] directory fsync
- [x] read-back verification before `SUCCEEDED`
- [x] explicit `committed` semantics for post-commit failures
- [x] symlink rejection as a path-based preflight check
- [x] optional allowed-root preflight boundary
- [x] POSIX-only mutation guard
- [x] JSON receipts and CLI exit codes
- [x] deterministic drift-injection tests
- [x] documented negative test for the final-recheck-to-rename lost-update window
- [x] racing create-if-absent and post-commit failure tests

## v0.2 - Agent integration and path hardening

- [ ] JSON input mode for tool-call runtimes
- [ ] fd-based target reads with `O_NOFOLLOW` + `fstat`
- [ ] dir-fd based commit path and directory fsync
- [ ] explicit hardlink policy (`st_nlink`)
- [ ] optional cooperative advisory lock for participating writers
- [ ] patch-scoped writes with expected base hash
- [ ] optional receipt file output
- [ ] Codex/AGENTS.md integration example
- [ ] Claude Code hook example
- [ ] OpenCode example
- [ ] Windows mutation design and CI coverage

## v0.3 - Pluggable effects

- [ ] verifier interface for non-file postconditions
- [ ] bounded retry/settle policy for eventually consistent systems
- [ ] idempotency key helper for external writes
- [ ] reference adapter for GitHub issue/comment mutation with read-back

## Non-goals

The project will not become an LLM orchestration framework. Deterministic mutation checks, explicit outcome semantics, and postcondition verification remain the focus.

Replacement-path atomic compare-and-swap is also not claimed: portable `os.replace` cannot make rename conditional on the fingerprint observed immediately beforehand.
