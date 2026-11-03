"""Versioned cache-generation manifests for the shared verification runner.

The cache root is mounted at ``/cache`` in the pinned execution image. A
normal run may use that cache only when ``READY.json`` names the complete
generation and every component still has the digest recorded in it. Creating
or refreshing the manifest is an explicit repair action.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable

CACHE_SCHEMA_VERSION = 1
READY_NAME = "READY.json"
CACHE_ROOT_ENV = "OOXML_CI_CACHE_ROOT"
DEFAULT_CACHE_ROOT = Path.home() / ".cache" / "ooxml-ci"
DEFAULT_COMPONENTS = ("repositories", "corpus", "dotnet")


class CacheError(RuntimeError):
    """The cache generation is absent, malformed, stale, or not ready."""


def cache_root(value: str | Path | None = None) -> Path:
    """Resolve the host cache root without creating or repairing it."""
    selected = value or os.environ.get(CACHE_ROOT_ENV) or DEFAULT_CACHE_ROOT
    return Path(selected).expanduser().resolve()


def _component_path(root: Path, value: Any) -> tuple[str, Path]:
    if not isinstance(value, str) or not value.strip():
        raise CacheError("cache component path must be a non-empty string")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or str(relative) in {"", "."}:
        raise CacheError(f"cache component path escapes the cache root: {value!r}")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise CacheError(f"cache component path escapes the cache root: {value!r}") from exc
    return relative.as_posix(), candidate


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _digest_tree(path: Path) -> str:
    """Hash names, node kinds and file bytes; timestamps and modes are excluded."""
    digest = hashlib.sha256()

    def add(*parts: str) -> None:
        for part in parts:
            encoded = part.encode("utf-8")
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)

    def visit(candidate: Path, relative: str) -> None:
        if candidate.is_symlink():
            add("symlink", relative, os.readlink(candidate))
            return
        if candidate.is_dir():
            add("dir", relative)
            for child in sorted(candidate.iterdir(), key=lambda item: item.name):
                visit(child, f"{relative}/{child.name}" if relative else child.name)
            return
        if candidate.is_file():
            add("file", relative)
            digest.update(bytes.fromhex(_hash_file(candidate)))
            return
        raise CacheError(f"cache component contains an unsupported filesystem node: {candidate}")

    visit(path, "")
    return digest.hexdigest()


def component_digest(path: Path) -> tuple[str, str]:
    """Return ``(kind, sha256)`` for one file or directory component."""
    if path.is_symlink():
        raise CacheError(f"cache component root must not be a symlink: {path}")
    if path.is_dir():
        return "directory", _digest_tree(path)
    if path.is_file():
        return "file", _hash_file(path)
    raise CacheError(f"required cache component is missing: {path}")


def _generation_id(schema_version: int, components: Iterable[dict[str, str]]) -> str:
    payload = {
        "schema_version": schema_version,
        "components": sorted(components, key=lambda item: item["path"]),
    }
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def generation(root: Path, components: Iterable[str] = DEFAULT_COMPONENTS) -> dict[str, Any]:
    """Describe the current cache generation without writing it."""
    root = Path(root).resolve()
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for value in components:
        relative, candidate = _component_path(root, value)
        if relative in seen:
            raise CacheError(f"cache component is declared more than once: {relative}")
        seen.add(relative)
        kind, sha256 = component_digest(candidate)
        rows.append({"path": relative, "kind": kind, "sha256": sha256})
    rows.sort(key=lambda item: item["path"])
    return {
        "schema_version": CACHE_SCHEMA_VERSION,
        "generation_id": _generation_id(CACHE_SCHEMA_VERSION, rows),
        "ready": True,
        "components": rows,
    }


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def repair(root: Path, components: Iterable[str] = DEFAULT_COMPONENTS) -> dict[str, Any]:
    """Explicitly create or refresh READY.json after checking every component."""
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    payload = generation(root, components)
    _write_atomic(root / READY_NAME, payload)
    return payload


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CacheError(f"cache manifest {field} must be an object")
    return value


def _load_manifest(root: Path) -> dict[str, Any]:
    path = root / READY_NAME
    if not path.is_file():
        raise CacheError(f"cache READY manifest is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CacheError(f"cache READY manifest is unreadable: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CacheError(f"cache READY manifest is not valid JSON: {path}: {exc}") from exc
    return _mapping(payload, "root")


def validate(
    root: Path,
    components: Iterable[str] = DEFAULT_COMPONENTS,
) -> dict[str, Any]:
    """Fail closed unless READY.json matches the current required generation."""
    root = Path(root).resolve()
    manifest = _load_manifest(root)
    if manifest.get("schema_version") != CACHE_SCHEMA_VERSION:
        raise CacheError(
            f"unsupported cache schema {manifest.get('schema_version')!r}; "
            f"expected {CACHE_SCHEMA_VERSION}"
        )
    if manifest.get("ready") is not True:
        raise CacheError("cache READY marker is not true")
    recorded = manifest.get("components")
    if not isinstance(recorded, list) or not recorded:
        raise CacheError("cache manifest has no component list")
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in recorded:
        row = _mapping(row, "component")
        relative, _ = _component_path(root, row.get("path"))
        if relative in seen:
            raise CacheError(f"cache manifest repeats component {relative!r}")
        seen.add(relative)
        kind = row.get("kind")
        sha256 = row.get("sha256")
        if kind not in {"file", "directory"}:
            raise CacheError(f"cache component {relative!r} has invalid kind {kind!r}")
        if not isinstance(sha256, str) or len(sha256) != 64 or any(
            character not in "0123456789abcdef" for character in sha256
        ):
            raise CacheError(f"cache component {relative!r} has an invalid sha256")
        normalized.append({"path": relative, "kind": kind, "sha256": sha256})
    expected_components = sorted(
        str(_component_path(root, value)[0]) for value in components
    )
    if sorted(seen) != expected_components:
        raise CacheError(
            f"cache manifest component set {sorted(seen)!r} does not match "
            f"required {expected_components!r}"
        )
    expected_id = _generation_id(CACHE_SCHEMA_VERSION, normalized)
    if manifest.get("generation_id") != expected_id:
        raise CacheError("cache manifest generation_id does not match its components")
    current = generation(root, expected_components)
    if current["generation_id"] != expected_id:
        raise CacheError("cache content changed after READY.json was written")
    return current


def ensure(
    root: Path,
    *,
    repair_cache: bool = False,
    components: Iterable[str] = DEFAULT_COMPONENTS,
) -> dict[str, Any]:
    """Validate in normal mode or explicitly create READY.json in repair mode."""
    return repair(root, components) if repair_cache else validate(root, components)
