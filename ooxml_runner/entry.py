"""Adapter-driven container entry.

This is what runs inside the pinned image: it proves which runner it is, loads
the repository adapter named by the plan, builds the stage implementations, and
hands them to the generic stage protocol in :mod:`ooxml_runner.container`.

The report skeleton is prepared by the host before the container starts, so a
container that dies before its first stage still leaves a report that names the
commit, runner version and plan it was supposed to verify.

The runner identity is checked here, inside the container, because the host's
read-only bind mount says nothing about what the mount actually contains.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import adapter as adapters
from . import container
from . import identity as identity_module
from . import report as report_module
from .docker import CONTAINER_REPORTS, CONTAINER_WORKSPACE

RUNNER_COMMIT_VAR = "OOXML_CI_RUNNER_COMMIT"


def _verify_runner() -> None:
    """Fail closed unless the mounted runner is the pinned commit's source."""
    expected = os.environ.get(RUNNER_COMMIT_VAR, "").strip()
    if not expected:
        raise identity_module.IdentityError(
            f"the container was not told which runner commit to execute ({RUNNER_COMMIT_VAR})"
        )
    identity_module.require_expected(identity_module.identity(), expected)


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
        _verify_runner()
        adapter = adapters.load(root, args.adapter)
        config = adapter.load_config(root)
        steps = adapters.operations(adapter, root, reports, config)
        container.run_stages(reports, steps, report, int(config["stage_timeout_seconds"]))
        container.finalize(root, reports, report, input_hashes=adapter.input_hashes, is_dirty=adapter.is_dirty)
    except BaseException as exc:  # noqa: BLE001 - the report must record every failure
        container.fail(reports, report, exc)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())