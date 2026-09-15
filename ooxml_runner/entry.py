"""Adapter-driven container entry.

This is what runs inside the pinned image: it loads the repository adapter named
by the plan, builds the stage implementations, and hands them to the generic
stage protocol in :mod:`ooxml_runner.container`.

The report skeleton is prepared by the host before the container starts, so a
container that dies before its first stage still leaves a report that names the
commit, runner version and plan it was supposed to verify.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import adapter as adapters
from . import container
from . import report as report_module
from .docker import CONTAINER_REPORTS, CONTAINER_WORKSPACE
from .report import utc_now


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ooxml_runner.entry", description="Run one repository's gate")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--root", default=None)
    parser.add_argument("--reports", default=CONTAINER_REPORTS)
    args = parser.parse_args(argv)
    root = Path(args.root or Path(CONTAINER_WORKSPACE) / args.repository)
    reports = Path(args.reports)
    report = report_module.load(reports)
    try:
        adapter = adapters.load(root, args.adapter)
        config = adapter.load_config(root)
        steps = adapters.operations(adapter, root, reports, config)
        container.run_stages(reports, steps, report, int(config["stage_timeout_seconds"]))
        container.finalize(root, reports, report, input_hashes=adapter.input_hashes, is_dirty=adapter.is_dirty)
    except BaseException as exc:  # noqa: BLE001 - the report must record every failure
        container.fail(reports, report, exc)
    finally:
        report["finished_at"] = utc_now()
        container.save_report(reports, report)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())