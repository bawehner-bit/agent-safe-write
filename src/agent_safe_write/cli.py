from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .core import DriftDetected, SafeWriteError, fingerprint, plan_write, safe_write


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-safe-write",
        description="Drift-aware atomic file writes for AI agents and automation.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    fp = sub.add_parser("fingerprint", help="print a target fingerprint as JSON")
    fp.add_argument("target")

    for name in ("plan", "apply"):
        cmd = sub.add_parser(name)
        cmd.add_argument("target")
        cmd.add_argument("--from-file", required=True, dest="source")
        cmd.add_argument(
            "--expect",
            help="expected current sha256; omit only when creating a file that must not already exist",
        )
        cmd.add_argument("--root", help="optional allowed root; target parent must resolve inside it")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "fingerprint":
            print(json.dumps(fingerprint(args.target).__dict__, indent=2, sort_keys=True))
            return 0

        data = Path(args.source).read_bytes()
        if args.command == "plan":
            receipt = plan_write(args.target, data, expected_sha256=args.expect, allowed_root=args.root)
        else:
            receipt = safe_write(args.target, data, expected_sha256=args.expect, allowed_root=args.root)
        print(receipt.to_json())
        return 0
    except DriftDetected as exc:
        print(json.dumps({"status": "NEEDS_REVIEW", "reason": str(exc)}, sort_keys=True), file=sys.stderr)
        return 3
    except SafeWriteError as exc:
        print(json.dumps({"status": "FAILED", "reason": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    except OSError as exc:
        print(json.dumps({"status": "FAILED", "reason": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
