# Contributing

Contributions are welcome, especially reproducible failure cases from real agent workflows.

## Principles

1. Keep the deterministic core independent of model providers.
2. A write path must never report success without a postcondition check.
3. Drift, ambiguity, and incomplete verification should fail closed.
4. Add a regression test before or with every safety-relevant fix.
5. Do not weaken the final pre-replace recheck for convenience.

## Setup

```bash
python -m pip install -e .
python -m pytest
```

## Good first issues

- Windows replace/durability semantics
- richer machine-readable error codes
- property-based test corpus
- documentation for integrating the CLI as an agent tool
