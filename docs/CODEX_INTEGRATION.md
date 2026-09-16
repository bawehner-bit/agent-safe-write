# Codex integration pattern

`agent-safe-write` can be used as a deterministic mutation boundary around agent-generated file content. It does not replace Codex's normal repository editing workflow; it is useful when a host or custom agent runtime needs an explicit expected-hash precondition and verified postcondition.

For replacement, this is a late compare-then-swap design, **not atomic compare-and-swap**. Drift visible at the final recheck is rejected, but a writer landing in the final-recheck-to-rename window can still be overwritten. See `docs/THREAT_MODEL.md`.

## Host workflow

1. Read or fingerprint the target outside the model.
2. Let the model propose the desired content.
3. Call `plan` with the exact observed SHA-256.
4. Apply only after any host policy or human-review gate passes.
5. Treat only exit code `0` / `SUCCEEDED` as completion.
6. On exit code `3` / `NEEDS_REVIEW`, re-read the target and re-plan; do not blind-retry.
7. On `FAILED`, inspect `committed` before deciding whether the target is unchanged. `committed=true` means the mutation crossed its commit point but durability/read-back confirmation failed.

Example:

```bash
BASE=$(python -m agent_safe_write fingerprint config.toml | python -c 'import json,sys; print(json.load(sys.stdin)["sha256"])')
python -m agent_safe_write plan config.toml --from-file /tmp/proposed.toml --expect "$BASE" --root "$PWD"
python -m agent_safe_write apply config.toml --from-file /tmp/proposed.toml --expect "$BASE" --root "$PWD"
```

## Suggested agent rule

```text
For consequential file writes routed through agent-safe-write:
- never omit the expected base hash for an existing file;
- never retry NEEDS_REVIEW without re-reading and re-planning;
- never translate PLANNED or ATTEMPTED into "done";
- claim completion only from a SUCCEEDED receipt;
- if FAILED, inspect committed before assuming the target is unchanged;
- do not describe replacement as atomic compare-and-swap.
```
