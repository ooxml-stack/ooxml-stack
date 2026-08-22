"""Helpers for P90 JSONL artifacts that outgrow single GitHub files."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Iterable

MAX_PART_BYTES = 20 * 1024 * 1024


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return list(iter_jsonl(path))


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    index = _index_path(path)
    if index.exists():
        for part in _index(index).get("parts", []):
            yield from _iter_file(index.parent / part["path"])
        return
    if path.exists():
        yield from _iter_file(path)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    target = _shard_dir(path)
    tmp = path.with_name(path.name + ".tmp.d")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    parts, stream, size, total_count = [], None, 0, 0
    try:
        for row in rows:
            line = json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            data_size = len(line.encode("utf-8"))
            if stream is None or size + data_size > MAX_PART_BYTES:
                if stream is not None:
                    stream.close()
                stream, size = _open_part(tmp, parts)
            stream.write(line)
            size += data_size
            total_count += 1
            parts[-1]["row_count"] += 1
            parts[-1]["size"] += data_size
    finally:
        if stream is not None:
            stream.close()
    _write_index(tmp, path.name, total_count, parts)
    if target.exists():
        shutil.rmtree(target)
    tmp.rename(target)
    path.unlink(missing_ok=True)


def logical_exists(root: Path, rel: str) -> bool:
    path = root / rel
    return path.exists() or _index_path(path).exists()


def artifact_paths(root: Path, rel: str) -> list[str]:
    path = root / rel
    index = _index_path(path)
    if not index.exists():
        return [rel]
    prefix = f"{rel}.d"
    parts = [f"{prefix}/{part['path']}" for part in _index(index).get("parts", [])]
    return [f"{prefix}/index.json", *parts]


def _iter_file(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def _open_part(tmp: Path, parts: list[dict[str, Any]]):
    name = f"part-{len(parts):04d}.jsonl"
    parts.append({"path": name, "row_count": 0, "size": 0})
    return (tmp / name).open("w", encoding="utf-8"), 0


def _write_index(tmp: Path, logical_name: str, count: int, parts: list[dict[str, Any]]) -> None:
    payload = {"schema_version": "p90-jsonl-shards-v1", "logical_name": logical_name, "row_count": count, "part_count": len(parts), "parts": parts}
    (tmp / "index.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _index(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _index_path(path: Path) -> Path:
    return _shard_dir(path) / "index.json"


def _shard_dir(path: Path) -> Path:
    return path.with_name(path.name + ".d")
