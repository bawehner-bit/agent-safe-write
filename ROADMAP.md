# Roadmap

## v0.1 - Local atomic write core

- [x] exact SHA-256 compare-and-swap precondition
- [x] final drift recheck immediately before replace
- [x] temp-file fsync and atomic replace
- [x] directory fsync
- [x] read-back verification
- [x] symlink rejection
- [x] optional allowed-root boundary
- [x] JSON receipts and CLI exit codes
- [x] tests for race/drift and failure paths

## v0.2 - Agent integration surface

- [ ] JSON input mode for tool-call runtimes
- [ ] patch-scoped writes with expected base hash
- [ ] optional receipt file output
- [ ] Codex/AGENTS.md integration example
- [ ] Claude Code hook example
- [ ] OpenCode example

## v0.3 - Pluggable effects

- [ ] verifier interface for non-file postconditions
- [ ] bounded retry/settle policy for eventually consistent systems
- [ ] idempotency key helper for external writes
- [ ] reference adapter for GitHub issue/comment mutation with read-back

## Non-goals

The project will not become an LLM orchestration framework. Deterministic write safety and outcome verification remain the focus.
