"""Runner identity: which shared implementation actually ran.

The runner is obtained at a pinned full commit SHA, so its own checkout is the
authority on its version. ``identity()`` reads that commit from the checkout and
also hashes the package source, so a tampered working tree is visible even when
the commit is right.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

from . import snapshot

PACKAGE_DIR = Path(__file__).resolve().parent


class IdentityError(RuntimeError):
    """The runner could not prove which version of itself is executing."""


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False,
        env=snapshot.git_environment(),
    )
    if result.returncode != 0:
        raise IdentityError(f"git {' '.join(args)} failed in {root}: {result.stderr.strip()}")
    return result.stdout.strip()


def source_sha256(package_dir: Path | None = None) -> str:
    """Deterministic hash over the runner package's own source files."""
    directory = Path(package_dir or PACKAGE_DIR)
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*.py")):
        digest.update(path.relative_to(directory).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def identity(package_dir: Path | None = None, runner_root: Path | None = None) -> dict[str, Any]:
    """Return ``{"commit": ..., "source_sha256": ..., "root": ...}``.

    ``root`` is the checkout that contains the package. It must be a Git
    worktree; a copy without ``.git`` cannot prove its version and fails closed.
    """
    directory = Path(package_dir or PACKAGE_DIR)
    root = Path(runner_root) if runner_root else directory.parent
    commit = _git(root, "rev-parse", "HEAD")
    if len(commit) != 40:
        raise IdentityError(f"runner checkout {root} has no full commit id")
    return {"commit": commit, "source_sha256": source_sha256(directory), "root": str(root)}


def require_expected(observed: dict[str, Any], expected_commit: str) -> None:
    """Fail closed when the running implementation is not the requested one."""
    if observed.get("commit") != expected_commit:
        raise IdentityError(
            "runner commit mismatch: requested "
            f"{expected_commit}, running {observed.get('commit')}"
        )