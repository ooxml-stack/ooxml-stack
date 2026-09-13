"""Git and network facts: the only module allowed to touch HEAD, worktrees or remotes."""

from __future__ import annotations

import pathlib
import re
import subprocess
from typing import Any

from .inputs import checkout_dir
from .urls import normalize_repo

SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def git(args: list[str], cwd: pathlib.Path, timeout: int) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=timeout
        )
    except FileNotFoundError:
        return 127, "", "git not found"
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def normalize_remote(url: str) -> str:
    return normalize_repo(url)


def common_dir(directory: pathlib.Path, timeout: int) -> str | None:
    """Absolute git common dir, so a main checkout and its worktrees compare equal."""
    code, common, _ = git(["rev-parse", "--git-common-dir"], directory, timeout)
    if code != 0 or not common:
        return None
    path = pathlib.Path(common)
    resolved = path.resolve() if path.is_absolute() else (directory / path).resolve()
    return str(resolved)


def _worktree_list(directory: pathlib.Path, timeout: int) -> list[dict[str, Any]]:
    code, listing, _ = git(["worktree", "list", "--porcelain"], directory, timeout)
    if code != 0:
        return []
    out = []
    for block in listing.split("\n\n"):
        lines = [line for line in block.strip().splitlines() if line.strip()]
        if not lines:
            continue
        path = lines[0].removeprefix("worktree ")
        out.append({"path": path, "main": directory.as_posix() == path})
    return out


def _checkout_entry(root: pathlib.Path, key: str, timeout: int) -> dict[str, Any]:
    directory = checkout_dir(root, key)
    entry: dict[str, Any] = {"path": str(directory.relative_to(root)), "exists": directory.is_dir()}
    if not directory.is_dir():
        return entry
    code, head, _ = git(["rev-parse", "HEAD"], directory, timeout)
    entry["head"] = head if code == 0 else None
    code, remote, _ = git(["remote", "get-url", "origin"], directory, timeout)
    entry["remote_url"] = remote if code == 0 and remote else None
    entry["remote"] = normalize_remote(remote) if code == 0 and remote else None
    entry["common_dir"] = common_dir(directory, timeout)
    entry["worktrees"] = _worktree_list(directory, timeout)
    return entry


def _checkout_diagnostics(key: str, node: dict[str, Any], entry: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    expected = node.get("remote")
    if not entry["exists"]:
        out.append(
            {
                "code": "policy_repo_mismatch",
                "level": "error",
                "where": key,
                "direction": "missing_checkout",
                "detail": f"expected a checkout at {entry['path']}",
            }
        )
    elif expected and entry.get("remote") and entry["remote"] != expected:
        out.append(
            {
                "code": "policy_repo_mismatch",
                "level": "error",
                "where": key,
                "direction": "remote_mismatch",
                "detail": f"remote {entry['remote']} != policy {expected}",
            }
        )
    for worktree in entry.get("worktrees", []):
        if not worktree["main"]:
            out.append(
                {"code": "alternate_worktree", "level": "info", "where": key, "detail": worktree["path"]}
            )
    return out


def _duplicate_diagnostics(checkouts: dict[str, Any]) -> tuple[list, list]:
    seen: dict[str, list[str]] = {}
    for key, entry in checkouts.items():
        if entry.get("remote"):
            seen.setdefault(entry["remote"], []).append(key)
    duplicates, diagnostics = [], []
    for remote, keys in sorted(seen.items()):
        if len(keys) > 1:
            duplicates.append({"remote": remote, "nodes": sorted(keys)})
            diagnostics.append(
                {
                    "code": "duplicate_repo_identity",
                    "level": "info",
                    "where": ",".join(sorted(keys)),
                    "detail": f"shared remote {remote}",
                }
            )
    return duplicates, diagnostics


def _undeclared_diagnostics(
    root: pathlib.Path, declared: dict[str, Any], checkouts: dict[str, Any], timeout: int
) -> list[dict[str, Any]]:
    known = {entry.get("common_dir") for entry in checkouts.values() if entry.get("common_dir")}
    out = []
    for child in sorted(path for path in root.iterdir() if (path / ".git").exists()):
        if child.name in declared or common_dir(child, timeout) in known:
            continue  # a declared node, or an alternate worktree of one
        out.append(
            {
                "code": "policy_repo_mismatch",
                "level": "error",
                "where": child.name,
                "direction": "undeclared_local",
                "detail": "git checkout under the workspace root is not a policy node",
            }
        )
    return out


def local_facts(root: pathlib.Path, policy: dict[str, Any], timeout: int) -> dict[str, Any]:
    declared = {node["key"]: node for node in policy["nodes"]}
    checkouts = {key: _checkout_entry(root, key, timeout) for key in declared}
    diagnostics: list[dict[str, Any]] = []
    for key, node in declared.items():
        diagnostics.extend(_checkout_diagnostics(key, node, checkouts[key]))
    duplicates, duplicate_diagnostics = _duplicate_diagnostics(checkouts)
    diagnostics.extend(duplicate_diagnostics)
    diagnostics.extend(_undeclared_diagnostics(root, declared, checkouts, timeout))
    return {"checkouts": checkouts, "duplicates": duplicates, "diagnostics": diagnostics}


def remote_refs(remote_url: str, cwd: pathlib.Path, timeout: int, cache: dict[str, Any]) -> dict[str, Any]:
    if remote_url in cache:
        return cache[remote_url]
    code, listing, error = git(["ls-remote", "--tags", "--heads", remote_url], cwd, timeout)
    if code != 0:
        result: dict[str, Any] = {"ok": False, "error": error or f"exit {code}", "tags": {}, "heads": {}}
    else:
        tags: dict[str, str] = {}
        peeled: dict[str, str] = {}
        heads: dict[str, str] = {}
        for line in listing.splitlines():
            parts = line.split("\t")
            if len(parts) != 2:
                continue
            sha, ref = parts
            if ref.startswith("refs/tags/"):
                name = ref[len("refs/tags/") :]
                if name.endswith("^{}"):
                    peeled[name[:-3]] = sha
                else:
                    tags[name] = sha
            elif ref.startswith("refs/heads/"):
                heads[ref[len("refs/heads/") :]] = sha
        result = {"ok": True, "tags": tags, "peeled": peeled, "heads": heads}
    cache[remote_url] = result
    return result


def _verify_sha(raw: str, directory: pathlib.Path | None, timeout: int, allow_fetch: bool) -> dict[str, Any]:
    """A full SHA can only be confirmed by a local object or an explicit fetch."""
    if directory is not None:
        code, _, _ = git(["cat-file", "-e", f"{raw}^{{commit}}"], directory, timeout)
        if code == 0:
            return {"kind": "full_commit", "commit": raw}
        if allow_fetch:
            code, _, _ = git(["fetch", "--quiet", "origin", raw], directory, timeout)
            if code == 0:
                return {"kind": "full_commit", "commit": raw}
    return {"kind": "unverifiable", "reason": "SHA existence cannot be proven locally or by fetch"}


def _tag_result(raw: str, listing: dict[str, Any]) -> dict[str, Any] | None:
    if raw not in listing.get("tags", {}):
        return None
    commit = listing.get("peeled", {}).get(raw) or listing["tags"][raw]
    kind = "annotated_tag" if raw in listing.get("peeled", {}) else "lightweight_tag"
    return {"kind": kind, "commit": commit}


def classify_remote_ref(
    raw: str,
    declared_kind: str,
    listing: dict[str, Any],
    directory: pathlib.Path | None,
    timeout: int,
    allow_fetch: bool = False,
) -> dict[str, Any]:
    """Classify a ref against the remote listing, honouring the declared selector.

    ``tag``/``release_tag`` only consult tags and ``branch`` only consults heads,
    so a branch is never masked by a same-named tag. ``unknown`` (and ``rev``,
    which may name any commit-ish) keeps the query-order fallback.
    """
    if not listing.get("ok"):
        return {"kind": "unverifiable", "reason": listing.get("error", "query failed")}
    tag = _tag_result(raw, listing)
    branch = {"kind": "branch", "commit": listing["heads"][raw]} if raw in listing.get("heads", {}) else None
    missing = {"kind": "missing", "reason": "ref confirmed absent on the remote"}
    if declared_kind in ("tag", "release_tag"):
        return tag or missing
    if declared_kind == "branch":
        return branch or missing
    if tag is not None:
        return tag
    if branch is not None:
        return branch
    if declared_kind == "sha" or SHA_RE.match(raw):
        return _verify_sha(raw, directory, timeout, allow_fetch)
    return missing