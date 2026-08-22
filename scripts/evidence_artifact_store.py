from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any


def store_artifact(path: Path, store_dir: Path, root: Path) -> dict[str, Any]:
    digest, size = _sha256(path)
    blob = _blob_path(store_dir, digest, path.suffix)
    blob.parent.mkdir(parents=True, exist_ok=True)
    if not blob.exists():
        _copy_atomic(path, blob)
    hardlinked = _replace_with_hardlink(path, blob)
    record = {
        "schema_version": "ooxml-evidence-artifact-v1",
        "logical_path": _rel(path, root),
        "artifact_sha256": digest,
        "artifact_size": size,
        "artifact_blob": _rel(blob, root),
        "artifact_hardlinked": hardlinked,
    }
    _append_manifest(store_dir, record)
    return record


def _sha256(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size


def _blob_path(store_dir: Path, digest: str, suffix: str) -> Path:
    return store_dir / "sha256" / digest[:2] / digest[2:4] / f"{digest}{suffix}"


def _copy_atomic(src: Path, dst: Path) -> None:
    tmp = dst.with_name(f".{dst.name}.tmp-{os.getpid()}")
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
    finally:
        tmp.unlink(missing_ok=True)


def _append_manifest(store_dir: Path, record: dict[str, Any]) -> None:
    path = store_dir / "artifact-manifest.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")


def _replace_with_hardlink(path: Path, blob: Path) -> bool:
    if _same_inode(path, blob):
        return True
    tmp = path.with_name(f".{path.name}.link-{os.getpid()}")
    try:
        os.link(blob, tmp)
        os.replace(tmp, path)
        return True
    except OSError:
        tmp.unlink(missing_ok=True)
        shutil.copy2(blob, path)
        return False


def _same_inode(left: Path, right: Path) -> bool:
    try:
        return left.stat().st_ino == right.stat().st_ino and left.stat().st_dev == right.stat().st_dev
    except FileNotFoundError:
        return False


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
