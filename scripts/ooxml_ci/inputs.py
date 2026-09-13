"""Read layer: workspace discovery, policy loading, input selection, digest.

Everything here reads the working tree exactly once and hands the captured
bytes to `parsers`. Git and network facts live in `gitfacts`.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Any

from . import deps, parsers, workflows
from .facts import (
    HOST_KEY,
    POLICY_RELPATH,
    SCHEMA_VERSION,
    WORKFLOW_GLOBS,
    Facts,
)
from .paths import InputError, find_root  # noqa: F401  (re-exported for callers)

# ----------------------------------------------------------------- discovery


def load_policy(root: pathlib.Path) -> dict[str, Any]:
    path = root / HOST_KEY / POLICY_RELPATH
    if not path.is_file():
        raise InputError(f"policy not found: {path}")
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy.get("schema_version") != SCHEMA_VERSION:
        raise InputError(f"policy schema_version must be {SCHEMA_VERSION}")
    keys = [node["key"] for node in policy.get("nodes", [])]
    if len(keys) != len(set(keys)):
        raise InputError("policy declares duplicate node keys")
    if HOST_KEY not in keys:
        raise InputError(f"policy must declare the host node {HOST_KEY!r}")
    for node in policy["nodes"]:
        if not node.get("role"):
            raise InputError(f"node {node['key']!r} lacks a role")
    return policy


def node_keys(policy: dict[str, Any]) -> list[str]:
    return [node["key"] for node in policy["nodes"]]


def node_index(policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {node["key"]: node for node in policy["nodes"]}


def checkout_dir(root: pathlib.Path, key: str) -> pathlib.Path:
    return root / key


# ------------------------------------------------------------ input selection


def _workflow_paths(root: pathlib.Path, key: str) -> list[str]:
    found: list[str] = []
    for pattern in WORKFLOW_GLOBS:
        for path in sorted((root / key).glob(pattern)):
            found.append(str(path.relative_to(root)))
    return found


def required_and_optional_paths(
    root: pathlib.Path, policy: dict[str, Any]
) -> tuple[list[str], list[str]]:
    """Declared inputs, split by whether their absence is a structural error."""
    required = [
        f"{HOST_KEY}/{POLICY_RELPATH}",
        # The pinned tool environment is an input: changing it must change the digest.
        f"{HOST_KEY}/{deps.REQUIREMENTS_RELPATH}",
    ]
    optional: list[str] = []
    for node in policy["nodes"]:
        key = node["key"]
        for relpath in node.get("inputs", []):
            required.append(f"{key}/{relpath}")
        optional.extend(_workflow_paths(root, key))
    for source in policy.get("edge_sources", []):
        if source.get("file"):
            required.append(source["file"])
    return sorted(set(required)), sorted(set(optional))


def _read(path: pathlib.Path) -> bytes | None:
    return path.read_bytes() if path.is_file() else None


def _dynamic_version_paths(root: pathlib.Path, policy: dict[str, Any], files: dict[str, bytes]) -> list[str]:
    """Version source files referenced by setuptools' dynamic attr."""
    extra: list[str] = []
    for node in policy["nodes"]:
        key = node["key"]
        blob = files.get(f"{key}/pyproject.toml")
        if blob is None:
            continue
        attr = parsers.dynamic_version_attr(blob)
        relpath = parsers.dynamic_version_path(attr) if attr else None
        if relpath:
            extra.append(f"{key}/{relpath}")
    return sorted(set(extra))


def select_inputs(
    root: pathlib.Path, policy: dict[str, Any]
) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    """Capture every selected input exactly once, plus the missing-required list."""
    required, optional = required_and_optional_paths(root, policy)
    files: dict[str, bytes] = {}
    missing: list[dict[str, Any]] = []
    for relpath in required:
        blob = _read(root / relpath)
        if blob is None:
            missing.append({"path": relpath, "why": "declared input is absent"})
        else:
            files[relpath] = blob
    for relpath in optional:
        blob = _read(root / relpath)
        if blob is not None:
            files[relpath] = blob
    for relpath in _dynamic_version_paths(root, policy, files):
        if relpath in files:
            continue
        blob = _read(root / relpath)
        if blob is None:
            missing.append({"path": relpath, "why": "dynamic version source is absent"})
        else:
            files[relpath] = blob
    return files, missing


def inputs_digest(files: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for relpath in sorted(files):
        digest.update(relpath.encode("utf-8"))
        digest.update(b"\0")
        digest.update(files[relpath])
        digest.update(b"\0")
    return digest.hexdigest()


def canonical_json(payload: Any) -> str:
    """Deterministic serialization: sorted keys, fixed indent, trailing newline."""
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


# -------------------------------------------------------------------- gather


def _workflow_files(files: dict[str, bytes], key: str) -> list[tuple[str, bytes]]:
    prefix = f"{key}/.github/workflows/"
    return [(rel, blob) for rel, blob in sorted(files.items()) if rel.startswith(prefix)]


def gather_facts(
    root: pathlib.Path,
    policy: dict[str, Any],
    files: dict[str, bytes],
    missing: list[dict[str, Any]] | None = None,
) -> Facts:
    facts = Facts(
        root=root,
        policy=policy,
        inputs=files,
        digest=inputs_digest(files),
        missing=list(missing or []),
    )
    for node in policy["nodes"]:
        key = node["key"]
        pyproject = files.get(f"{key}/pyproject.toml")
        if pyproject is not None:
            facts.declarations.extend(parsers.parse_pyproject(pyproject, key))
            facts.uv_sources[key] = parsers.parse_uv_sources(pyproject)
        lock = files.get(f"{key}/uv.lock")
        facts.locks[key] = parsers.parse_uv_lock(lock) if lock is not None else {}
        attr = parsers.dynamic_version_attr(pyproject) if pyproject else None
        version_path = parsers.dynamic_version_path(attr) if attr else None
        blob = files.get(f"{key}/{version_path}") if version_path else None
        facts.versions[key] = parsers.parse_project_version(pyproject, key, blob)
        for relpath, data in _workflow_files(files, key):
            parsed = workflows.parse_workflow(data)
            facts.workflow_uses[relpath] = parsed["uses"]
            facts.workflow_jobs[relpath] = parsed["jobs"]
            facts.clone_refs[relpath] = parsed["clone_refs"]
            facts.workflow_errors.extend(
                {**item, "where": f"{relpath}:{item['where']}"} for item in parsed["errors"]
            )
    for source in policy.get("edge_sources", []):
        if source.get("from") == "environment_json" and source.get("file"):
            blob = files.get(source["file"])
            if blob is not None:
                facts.environment = parsers.parse_environment_json(blob)
    return facts