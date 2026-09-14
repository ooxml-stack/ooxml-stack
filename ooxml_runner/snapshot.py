"""Clean execution snapshots and Git plumbing.

Moved out of the engine so that every repository gets the same snapshot
semantics: a full commit id, a depth-1 fetch from the local repository, a
detached checkout with host Git configuration disabled, and a post-checkout
assertion that the snapshot really is the requested commit.
"""

from __future__ import annotations

import contextlib
import os
import re
import subprocess
import tempfile
from functools import partial
from pathlib import Path

_COMMIT = re.compile(r"[0-9a-f]{40}")
# Host Git state must not leak into a snapshot: a stray index, work tree or
# object directory would silently change what gets checked out.
_GIT_ENV = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_PREFIX",
    "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_SHALLOW_FILE",
)


class SnapshotError(RuntimeError):
    """A snapshot could not be prepared or did not match the request."""


def git(repo: Path, *args: str, isolated: bool = False, binary: bool = False):
    env = dict(os.environ)
    for name in _GIT_ENV:
        env.pop(name, None)
    if isolated:
        env.update(GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1", GIT_ATTR_NOSYSTEM="1")
        env.pop("GIT_CONFIG_COUNT", None)
        env.pop("GIT_CONFIG_PARAMETERS", None)
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, check=True, env=env,
    )
    if binary:
        return result.stdout
    return result.stdout.decode("utf-8", errors="replace").strip()


def resolve_commit(repo: Path, revision: str) -> str:
    """Resolve a revision to a full commit id; anything else is refused."""
    try:
        commit = git(repo, "rev-parse", "--verify", "--end-of-options", f"{revision}^{{commit}}")
    except subprocess.CalledProcessError as exc:
        raise SnapshotError(f"cannot resolve {revision!r} to a commit in {repo}") from exc
    if not _COMMIT.fullmatch(commit):
        raise SnapshotError(f"expected a complete Git commit id, got {commit!r}")
    return commit


def read_at_commit(repo: Path, commit: str, relpath: str) -> bytes:
    """Read one file from a commit, never from the working tree."""
    return git(repo, "show", f"{commit}:{relpath}", binary=True)


def checkout(repo: Path, commit: str, destination: Path) -> Path:
    """Materialize ``commit`` into ``destination`` as an isolated checkout."""
    destination = Path(destination)
    destination.mkdir(parents=True)
    invoke = partial(git, destination, isolated=True)
    invoke("-c", "init.templateDir=", "init", "--quiet")
    invoke("config", "core.autocrlf", "false")
    invoke("config", "core.eol", "lf")
    invoke("config", "core.attributesFile", "/dev/null")
    invoke("config", "core.hooksPath", "/dev/null")
    invoke("fetch", "--quiet", "--depth=1", "--no-tags", str(Path(repo).resolve()), commit)
    invoke("checkout", "--quiet", "--detach", "FETCH_HEAD")
    if invoke("rev-parse", "HEAD") != commit:
        raise SnapshotError("snapshot commit does not match the requested commit")
    return destination


def is_dirty(repo: Path) -> bool:
    """Tracked modifications in a checkout; untracked files are not the gate's."""
    return bool(git(repo, "status", "--porcelain", "--untracked-files=no"))


def is_exact(repo: Path, commit: str) -> bool:
    """True when ``repo`` already is a clean checkout of exactly ``commit``."""
    try:
        return git(repo, "rev-parse", "HEAD") == commit and not is_dirty(repo)
    except (OSError, subprocess.CalledProcessError):
        return False


@contextlib.contextmanager
def materialize(repo: Path, commit: str):
    """Yield a checkout of ``commit``, reusing ``repo`` when it already is that commit.

    Reuse requires both the exact commit and a clean tracked tree, so a working
    checkout with local edits never becomes the verification subject.
    """
    if is_exact(repo, commit):
        yield Path(repo)
        return
    with tempfile.TemporaryDirectory(prefix="ooxml-runner-") as temporary:
        yield checkout(repo, commit, Path(temporary) / Path(repo).name)


def credential() -> str:
    """Private-dependency token: environment, then ``~/.claude/.env``, then ``gh``."""
    token = os.environ.get("OOXML_STACK_TOKEN", "").strip()
    if token:
        return token
    env_file = Path.home() / ".claude" / ".env"
    if env_file.is_file():
        for line in env_file.read_text().splitlines():
            name, separator, value = line.removeprefix("export ").partition("=")
            if separator and name.strip() == "OOXML_STACK_TOKEN":
                found = value.strip().strip("\"'")
                if found:
                    return found
    try:
        result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SnapshotError("private dependency credentials unavailable") from exc
    if not result.stdout.strip():
        raise SnapshotError("private dependency credentials unavailable")
    return result.stdout.strip()