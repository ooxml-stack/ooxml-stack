"""Create a recorded developer checkout under .worktrees/<task>/<repository>."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from ooxml_runner.snapshot import git, resolve_commit


def _component(value, label):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value):
        raise ValueError(f"{label} must be a single name without path separators")
    return value


def _paths(workspace, task, repository):
    root = Path(workspace).resolve(strict=True)
    task = _component(task, "task")
    repository = _component(repository, "repository")
    source = root / repository
    parent = root / ".worktrees" / task
    target = parent / repository
    receipt = parent / f"{repository}.worktree.json"
    for path in (source, root / ".worktrees", parent, target, receipt):
        if path.is_symlink() or path.resolve() != path:
            raise ValueError(f"symlinked workspace path is not supported: {path}")
    if target.exists() or receipt.exists():
        raise ValueError(f"checkout or task record already exists: {target}")
    if Path(git(source, "rev-parse", "--show-toplevel")).resolve() != source:
        raise ValueError("repository must identify a checkout at the workspace root")
    return root, source, target, receipt


def _write_record(stream, record):
    stream.seek(0)
    json.dump(record, stream, indent=2)
    stream.write("\n")
    stream.truncate()
    stream.flush()


def create(workspace, task, repository, owner, retire_when, revision="HEAD", branch=None):
    if not owner.strip() or not retire_when.strip():
        raise ValueError("owner and retirement condition must be nonempty")
    root, source, target, receipt = _paths(workspace, task, repository)
    commit = resolve_commit(source, revision)
    record = {"schema_version": 1, "task": task, "owner": owner,
              "repository": repository, "commit": commit, "branch": branch,
              "checkout": str(target.relative_to(root)),
              "evidence": str(Path(".delivery-evidence") / task),
              "retire_when": retire_when, "status": "preparing"}
    target.parent.mkdir(parents=True, exist_ok=True)
    with receipt.open("x+") as stream:
        _write_record(stream, record)
        try:
            if target.is_symlink() or target.resolve() != target or target.exists():
                raise ValueError(f"checkout path changed before creation: {target}")
            options = ["-b", branch] if branch is not None else ["--detach"]
            git(source, "worktree", "add", *options, str(target), commit)
        except (OSError, ValueError, subprocess.CalledProcessError, KeyboardInterrupt) as exc:
            record.update(status="interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                          error_type=type(exc).__name__)
            _write_record(stream, record)
            raise
        record["status"] = "ready"
        _write_record(stream, record)
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--retire-when", required=True)
    parser.add_argument("--revision", default="HEAD")
    parser.add_argument("--branch")
    args = parser.parse_args(argv)
    try:
        print(create(**vars(args)))
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"worktree creation refused: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
