"""Runner identity: which shared implementation actually ran.

The runner is obtained at a pinned full commit SHA, so the pinned commit is the
authority on its version. Two facts have to agree:

* the checkout the runner is executing from is that commit, and
* the source actually loaded from it is the source that commit contains.

The second is not implied by the first. ``HEAD`` does not move when the working
tree is edited, and a read-only bind mount says nothing about what it holds, so
the trusted hash is derived from the commit's own tree and compared against the
running package. Only the executed package is in scope: a documentation change
or another author's file in the same checkout does not invalidate a run.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

from . import snapshot

PACKAGE_DIR = Path(__file__).resolve().parent
PACKAGE_NAME = PACKAGE_DIR.name


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


def _git_bytes(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, check=False,
        env=snapshot.git_environment(),
    )
    if result.returncode != 0:
        raise IdentityError(f"git {' '.join(args)} failed in {root}")
    return result.stdout


def _digest(entries) -> str:
    """Hash rule: sorted relative path, NUL, file bytes, NUL - per source file.

    A file added, removed or edited inside the package changes the digest, in
    the working tree and in a commit alike.
    """
    digest = hashlib.sha256()
    for relative, payload in entries:
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")
    return digest.hexdigest()


def source_sha256(package_dir: Path | None = None) -> str:
    """Deterministic hash over the runner package's own source files on disk."""
    directory = Path(package_dir or PACKAGE_DIR)
    return _digest(
        (path.relative_to(directory).as_posix(), path.read_bytes())
        for path in sorted(directory.rglob("*.py"))
    )


def source_sha256_at(root: Path, commit: str) -> str:
    """The same hash, derived from ``commit``'s tree instead of the working tree.

    This is the only trustworthy expectation: it cannot be influenced by an
    uncommitted edit, and it fails closed if the checkout does not contain the
    commit at all.
    """
    root = Path(root)
    listed = _git(root, "ls-tree", "-r", "--name-only", commit, "--", PACKAGE_NAME).splitlines()
    entries = []
    for name in sorted(listed):
        if not name.endswith(".py"):
            continue
        entries.append((name[len(PACKAGE_NAME) + 1:], _git_bytes(root, "show", f"{commit}:{name}")))
    if not entries:
        raise IdentityError(f"commit {commit} contains no {PACKAGE_NAME} source in {root}")
    return _digest(entries)


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


def require_expected(observed: dict[str, Any], expected_commit: str) -> dict[str, Any]:
    """Fail closed unless the running source is what ``expected_commit`` contains.

    Returns the trusted identity derived from that commit, which callers use as
    the expectation for reports and cache entries.
    """
    if observed.get("commit") != expected_commit:
        raise IdentityError(
            "runner commit mismatch: requested "
            f"{expected_commit}, running {observed.get('commit')}"
        )
    root = observed.get("root")
    if not root:
        raise IdentityError("runner identity does not name the checkout it ran from")
    trusted = {"commit": expected_commit, "source_sha256": source_sha256_at(Path(root), expected_commit),
               "root": root}
    if observed.get("source_sha256") != trusted["source_sha256"]:
        raise IdentityError(
            f"runner source does not match pinned commit {expected_commit}: "
            f"running {observed.get('source_sha256')}, commit {trusted['source_sha256']}"
        )
    return trusted