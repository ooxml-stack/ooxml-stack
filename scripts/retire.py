"""CLI entry for the workspace retire gc (see scripts/retire_gc/).

Implements CLEANUP-TODO B1.1. Dry-run is the default; --execute performs
ledger-driven deletions and compaction. Unregistered .delivery-evidence
content, ~/.opc sessions, .archive-backups and .worktrees are report-only.
"""

from __future__ import annotations

import argparse
import json
import sys

from retire_gc.clock import utc_now
from retire_gc.runner import (
    DEFAULT_COMPACT_THRESHOLD,
    find_workspace,
    print_summary,
    run_gc,
)

DEFAULT_SESSION_ARCHIVE_DAYS = 30


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", help="workspace root (default: auto-detect)")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="perform deletions and compaction (default: dry-run)",
    )
    parser.add_argument("--json", dest="as_json", action="store_true", help="print full JSON report")
    parser.add_argument("--compact-threshold", type=int, default=DEFAULT_COMPACT_THRESHOLD)
    parser.add_argument("--session-archive-days", type=int, default=DEFAULT_SESSION_ARCHIVE_DAYS)
    parser.add_argument(
        "--managed-root",
        action="append",
        default=[],
        help="extra root under which ledger deletions are allowed (repeatable)",
    )
    parser.add_argument("--registry", help="override ledger path (default: workspace ledger)")
    parser.add_argument(
        "--fail-on-alarm",
        action="store_true",
        help="exit 3 when the tripwire reports unregistered content",
    )
    args = parser.parse_args(argv)
    try:
        workspace = find_workspace(args.workspace)
        report = run_gc(
            workspace,
            "execute" if args.execute else "dry-run",
            utc_now(),
            args.compact_threshold,
            args.session_archive_days,
            args.managed_root,
            args.registry,
        )
    except (OSError, ValueError) as exc:
        print(f"retire refused: {exc}", file=sys.stderr)
        return 1
    if args.as_json:
        print(json.dumps(report, indent=2))
    else:
        print_summary(report)
    if args.fail_on_alarm and report["tripwire"].get("alarms_total", 0) > 0:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
