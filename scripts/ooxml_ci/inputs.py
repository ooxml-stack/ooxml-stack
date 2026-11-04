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


def _workflow_paths(root: pathlib.Path, key: str, commit: str | None = None) -> list[str]:
    if commit:
        from . import gitfacts

        found: list[str] = []
        for pattern in WORKFLOW_GLOBS:
            found.extend(
                f"{key}/{relpath}"
                for relpath in sorted(gitfacts.commit_paths(root, key, commit, pattern))
            )
        return found
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


def bound_commits(root: pathlib.Path, policy: dict[str, Any]) -> tuple[dict[str, str], set[str]]:
    """Resolve policy-bound node inputs to commit IDs, never worktree bytes."""
    binding = policy.get("input_binding") or {}
    if not binding:
        return {}, set()
    if binding.get("kind") != "git_commit":
        raise InputError(f"unsupported input_binding kind: {binding.get('kind')!r}")
    from . import gitfacts

    exempt = set(binding.get("exempt_nodes") or [])
    source = binding.get("commit_source") or {}
    source_path = root / str(source.get("file", ""))
    try:
        declared = json.loads(source_path.read_text(encoding="utf-8"))
        for part in str(source.get("field", "")).split("."):
            declared = declared[part]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise InputError(f"input binding cannot read declared commits: {exc}") from exc
    if not isinstance(declared, dict):
        raise InputError("input binding declared commits must be an object")
    commits: dict[str, str] = {}
    for node in policy["nodes"]:
        key = node["key"]
        if key in exempt or not node.get("inputs"):
            continue
        commit = declared.get(key)
        if not isinstance(commit, str) or not gitfacts.SHA_RE.fullmatch(commit):
            raise InputError(f"input binding has no immutable commit for {key}")
        code, _, _ = gitfacts.git(["cat-file", "-e", f"{commit}^{{commit}}"], root / key, 25)
        if code != 0:
            raise InputError(f"input binding commit is unresolvable for {key}: {commit}")
        commits[key] = commit
    return commits, exempt


def _dynamic_version_paths(
    root: pathlib.Path, policy: dict[str, Any], files: dict[str, bytes]
) -> list[str]:
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


def _bound_blob(
    root: pathlib.Path, key: str, commit: str, relpath: str
) -> bytes | None:
    from . import gitfacts

    return gitfacts.commit_blob(root, key, commit, relpath.removeprefix(f"{key}/"))


def select_inputs(
    root: pathlib.Path, policy: dict[str, Any], binding=None
) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    """Capture every selected input exactly once, plus the missing-required list."""
    required, optional = required_and_optional_paths(root, policy)
    commits, exempt = binding or bound_commits(root, policy)
    bound = {key for key in commits if key not in exempt}
    optional = [path for path in optional if path.split("/", 1)[0] not in bound]
    for key in sorted(bound):
        optional.extend(_workflow_paths(root, key, commits[key]))
    files: dict[str, bytes] = {}
    missing: list[dict[str, Any]] = []
    for relpath in sorted(set(required)):
        key = relpath.split("/", 1)[0]
        if key == HOST_KEY or relpath == f"{HOST_KEY}/{POLICY_RELPATH}":
            blob = _read(root / relpath)
        else:
            blob = _bound_blob(root, key, commits[key], relpath) if key in bound else _read(root / relpath)
        if blob is None:
            why = f"commit {commits[key]} does not contain it" if key in bound else "declared input is absent"
            missing.append({"path": relpath, "why": why})
        else:
            files[relpath] = blob
    for relpath in optional:
        key = relpath.split("/", 1)[0]
        blob = _bound_blob(root, key, commits[key], relpath) if key in bound else _read(root / relpath)
        if blob is not None:
            files[relpath] = blob
    for relpath in _dynamic_version_paths(root, policy, files):
        if relpath in files:
            continue
        key = relpath.split("/", 1)[0]
        blob = _bound_blob(root, key, commits[key], relpath) if key in bound else _read(root / relpath)
        if blob is None:
            missing.append({"path": relpath, "why": "dynamic version source is absent"})
        else:
            files[relpath] = blob
    return files, missing


def input_manifest(files: dict[str, bytes], sources: dict[str, dict[str, str]] | None = None) -> list[dict[str, str]]:
    """Name every declared input with its own digest.

    The plan has to state its input identity, not just a digest over whatever
    happened to be readable. A consumer holding only part of the workspace can
    then check the inputs it does have against the plan instead of silently
    skipping them, and can report the rest as unchecked rather than as a pass.
    """
    sources = sources or {}
    return [
        {"path": relpath, "sha256": hashlib.sha256(files[relpath]).hexdigest(), **sources.get(relpath, {})}
        for relpath in sorted(files)
    ]


def inputs_digest(manifest: list[dict[str, str]]) -> str:
    """Digest the manifest itself, so the identity is the manifest."""
    digest = hashlib.sha256()
    for entry in manifest:
        digest.update(entry["path"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(entry["sha256"].encode("ascii"))
        digest.update(b"\0")
        digest.update(entry.get("source", "").encode("utf-8"))
        digest.update(b"\0")
        digest.update(entry.get("commit", "").encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def canonical_json(payload: Any) -> str:
    """Deterministic serialization: sorted keys, fixed indent, trailing newline."""
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


# -------------------------------------------------------------------- gather


def _workflow_files(files: dict[str, bytes], key: str) -> list[tuple[str, bytes]]:
    prefix = f"{key}/.github/workflows/"
    return [
        (rel, blob) for rel, blob in sorted(files.items()) if rel.startswith(prefix)
    ]


def gather_facts(
    root: pathlib.Path,
    policy: dict[str, Any],
    files: dict[str, bytes],
    missing: list[dict[str, Any]] | None = None,
    binding=None,
) -> Facts:
    commits, exempt = binding or bound_commits(root, policy)
    sources = {
        relpath: {"source": "git", "commit": commits[relpath.split("/", 1)[0]]}
        for relpath in files
        if relpath.split("/", 1)[0] in commits and relpath.split("/", 1)[0] not in exempt
    }
    manifest = input_manifest(files, sources)
    facts = Facts(
        root=root,
        policy=policy,
        inputs=files,
        digest=inputs_digest(manifest),
        manifest=manifest,
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
                {**item, "where": f"{relpath}:{item['where']}"}
                for item in parsed["errors"]
            )
    for source in policy.get("edge_sources", []):
        if source.get("from") == "environment_json" and source.get("file"):
            blob = files.get(source["file"])
            if blob is not None:
                facts.environment = parsers.parse_environment_json(blob)
    return facts
