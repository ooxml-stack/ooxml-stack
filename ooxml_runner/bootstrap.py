"""Container entry point: materialize the snapshot, then run the stages.

The engine's historical ``scripts/ci/bootstrap.py`` did this for one repository.
It now lives here so that every repository gets the same container bootstrap:
copy the read-only snapshot into a writable workspace, run the stage executor,
and hand the report directory back to the invoking host user.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .credentials import configure
from .docker import CONTAINER_INPUT, CONTAINER_REPORTS, CONTAINER_WORKSPACE


def prepare_workspace(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, symlinks=True, dirs_exist_ok=True)


def export_ownership(reports: Path, uid: int, gid: int) -> None:
    for directory, folders, files in os.walk(reports, followlinks=False):
        for path in [Path(directory), *(Path(directory) / name for name in folders + files)]:
            os.chown(path, uid, gid, follow_symlinks=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ooxml_runner.bootstrap", description="Container bootstrap")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--adapter", required=True)
    args = parser.parse_args(argv)
    root = Path(CONTAINER_WORKSPACE) / args.repository
    reports = Path(CONTAINER_REPORTS)
    try:
        configure()
        prepare_workspace(Path(CONTAINER_INPUT) / args.repository, root)
        return subprocess.run(
            [sys.executable, "-m", "ooxml_runner.entry", "--repository", args.repository,
             "--adapter", args.adapter, "--root", str(root), "--reports", str(reports)],
            cwd=root,
            check=False,
        ).returncode
    finally:
        export_ownership(reports, int(os.environ["OOXML_CI_REPORT_UID"]), int(os.environ["OOXML_CI_REPORT_GID"]))


if __name__ == "__main__":
    sys.exit(main())