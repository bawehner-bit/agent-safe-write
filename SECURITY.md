# Security policy

Please do not publish exploitable safety-boundary defects as a public issue before the maintainer has had a reasonable chance to assess them.

Until a dedicated security contact is configured, open a GitHub issue that contains no exploit details and asks for a private reporting channel.

## Supported versions

The latest released minor version is supported.

## Important limitation

`agent-safe-write` is not a sandbox or access-control layer. Its guarantees apply only when callers actually route a write through this library.
