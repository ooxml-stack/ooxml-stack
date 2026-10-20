"""Verify pinned source commits and the frozen wheelhouse."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


class InputLockError(ValueError):
    """A release input does not match its committed pin."""


def verify_inputs(config: dict[str, Any], wheelhouse: Path) -> dict[str, Any]:
    root = Path(config["_repo_root"])
    expected = config["reproducibility"]["source_commits"]
    actual = {}
    for name, relative in config["sources"].items():
        repo = (root / relative).resolve()
        result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        actual[name] = result.stdout.strip()
        if result.returncode != 0 or actual[name] != expected[name]:
            raise InputLockError(
                f"source pin mismatch for {name}: {actual[name]} != {expected[name]}"
            )
    lock_path = root / config["reproducibility"]["wheelhouse_lock"]
    expected_lock = json.loads(lock_path.read_text(encoding="utf-8"))
    actual_lock = wheelhouse_lock(wheelhouse)
    if actual_lock != expected_lock:
        raise InputLockError("wheelhouse does not match its committed SHA-256 lock")
    return {"source_commits": actual, "wheelhouse_sha256": actual_lock["sha256"]}


def write_wheelhouse_lock(wheelhouse: Path, path: Path) -> dict[str, Any]:
    lock = wheelhouse_lock(wheelhouse)
    path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return lock


def wheelhouse_lock(wheelhouse: Path) -> dict[str, Any]:
    files = []
    digest = hashlib.sha256()
    for wheel in sorted(wheelhouse.glob("*.whl")):
        data = wheel.read_bytes()
        row = {
            "filename": wheel.name,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        files.append(row)
        digest.update(json.dumps(row, sort_keys=True).encode())
    if not files:
        raise InputLockError("wheelhouse contains no wheels")
    return {"schema_version": 1, "sha256": digest.hexdigest(), "files": files}
