"""Prepare an isolated workspace whose checkouts are at each node's default branch.

The published plan is a fact about what each repository *publishes*, and that is
defined as the default branch of every policy node. Reproducing it therefore
needs a workspace built the same way: a plain clone of each node, in an isolated
directory, at whatever branch that repository calls its default.

This module deliberately does not try to be a repository manager. It reads the
node set out of the existing policy, runs one ``git clone`` per node, and stops.
Nothing here queries "the default branch" by name - ``git clone`` already checks
out the default branch, which is the point: ``python-docx`` and ``python-pptx``
default to ``master``, and hardcoding ``main`` silently produced a different
basis.

Standard library only: the dependency precheck still owns the interpreter, and
preparing a workspace must not need the parsing layer.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import time

from . import paths

DEFAULT_OWNER = "ooxml-stack"


class WorkspaceError(RuntimeError):
    """The isolated workspace could not be prepared."""


def node_keys(policy_path: pathlib.Path) -> list[str]:
    """The node set, taken from the policy rather than repeated here."""
    try:
        policy = json.loads(pathlib.Path(policy_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkspaceError(f"policy is unreadable: {policy_path}: {exc}") from exc
    keys = [node.get("key") for node in policy.get("nodes") or []]
    if not keys or any(not isinstance(key, str) or not key for key in keys):
        raise WorkspaceError(f"policy declares no usable node keys: {policy_path}")
    return keys


def clone_url(key: str, owner: str = DEFAULT_OWNER) -> str:
    return f"https://github.com/{owner}/{key}.git"


CLONE_ATTEMPTS = 3


def _clone(key: str, target: pathlib.Path, owner: str) -> None:
    """Clone one node, retrying a transient transport failure.

    A dropped HTTP/2 stream or an early EOF is a temporary transport fault, not a
    statement about the node, and a refresh that has already cloned ten nodes
    must not be discarded because the eleventh hit one. A partially written
    target is removed before the retry; a genuine failure still ends in
    ``WorkspaceError`` after the bounded attempts.
    """
    last = ""
    for attempt in range(1, CLONE_ATTEMPTS + 1):
        if target.exists():
            shutil.rmtree(target)
        result = subprocess.run(["git", "clone", "--quiet", clone_url(key, owner), str(target)],
                                capture_output=True, text=True)
        if result.returncode == 0:
            return
        last = result.stderr.strip()
        if attempt < CLONE_ATTEMPTS:
            time.sleep(attempt * 2)
    raise WorkspaceError(f"git clone failed for {key} after {CLONE_ATTEMPTS} attempts: {last}")


def prepare(root: pathlib.Path, policy_path: pathlib.Path, owner: str = DEFAULT_OWNER) -> list[str]:
    """Clone every policy node into ``root`` at its own default branch."""
    root = pathlib.Path(root)
    root.mkdir(parents=True, exist_ok=True)
    cloned: list[str] = []
    for key in node_keys(policy_path):
        target = root / key
        if target.exists():
            raise WorkspaceError(f"{target} already exists; refusing to reuse a workspace")
        _clone(key, target, owner)
        cloned.append(key)
    return cloned