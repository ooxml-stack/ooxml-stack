"""Consume the ecosystem plan as an execution input.

The plan is a *static* description. It is used here for three things only:

1. proving the target repository is a declared full-verification node and that
   its declared workflow/job binding still exists,
2. naming the adapter that owns the repository's checks,
3. binding the run to a plan file identity (SHA-256) and to the configuration
   identity the plan was derived from (``inputs_digest``).

The plan's shell text is never executed. A workflow step that calls the shared
entry is evidence that the binding is wired up, not a command to run - running
it would re-enter the runner.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION


class PlanError(RuntimeError):
    """The plan is missing, malformed, or does not declare this repository."""


def load(path: Path) -> dict[str, Any]:
    """Read the plan file and attach its byte identity and derived digest."""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise PlanError(f"plan is unreadable: {path}") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PlanError(f"plan is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PlanError("plan must be a JSON object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise PlanError(f"plan schema_version must be {SCHEMA_VERSION}")
    if not payload.get("inputs_digest"):
        raise PlanError("plan does not carry an inputs_digest")
    errors = [item for item in payload.get("diagnostics") or [] if item.get("level") == "error"]
    if errors:
        raise PlanError(
            "plan carries blocking diagnostics: "
            + "; ".join(f"{item.get('code')} {item.get('where')}" for item in errors[:5])
        )
    return {
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "inputs_digest": payload["inputs_digest"],
        "payload": payload,
    }


def binding_for(plan: dict[str, Any], repo: str) -> dict[str, Any]:
    """Resolve the declared full-verification binding for one repository."""
    payload = plan["payload"]
    keys = {node.get("key") for node in payload.get("nodes") or []}
    if repo not in keys:
        raise PlanError(f"repository {repo!r} is not a declared node in the plan")
    full = (payload.get("full") or {}).get(repo)
    if not full:
        raise PlanError(f"repository {repo!r} has no full-verification binding in the plan")
    jobs = [job.get("id") for job in full.get("jobs") or []]
    if not full.get("workflow") or not jobs:
        raise PlanError(f"full binding for {repo!r} is incomplete")
    adapter = full.get("adapter")
    if not adapter:
        raise PlanError(
            f"full binding for {repo!r} declares no adapter; the runner cannot "
            "execute a repository whose checks have no declared implementation"
        )
    return {"workflow": full["workflow"], "jobs": jobs, "adapter": adapter}


def _manifest(plan: dict[str, Any]) -> list[dict[str, str]]:
    """The declared input manifest, newest shape first.

    Older plans carried a bare path list and a digest over the bytes. Reading
    them here would reintroduce the defect this manifest exists to remove, so a
    plan without per-input digests is refused rather than half-checked.
    """
    entries = plan["payload"].get("inputs")
    if not isinstance(entries, list):
        raise PlanError("plan declares no input manifest")
    manifest: list[dict[str, str]] = []
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("path") or not entry.get("sha256"):
            raise PlanError(f"plan input manifest entry is malformed: {entry!r}")
        manifest.append({"path": str(entry["path"]), "sha256": str(entry["sha256"])})
    return manifest


EXCLUDED_REASON = "target_repository"


def _classify(manifest: list[dict[str, str]], root: Path, repo: str | None, commit: str | None):
    """Split the manifest into checked, mismatched, unchecked and excluded.

    Paths are de-duplicated first: the accounting has to add up, and a repeated
    path must not be counted twice.
    """
    prefix = f"{repo}/" if repo else None
    checked: set[str] = set()
    mismatched: list[str] = []
    unchecked: list[str] = []
    excluded: list[dict[str, str]] = []
    for entry in {item["path"]: item["sha256"] for item in manifest}.items():
        path, expected = entry
        if prefix and path.startswith(prefix):
            excluded.append({"path": path, "reason": EXCLUDED_REASON, "bound_to": commit})
            continue
        candidate = root / path
        if not candidate.is_file():
            unchecked.append(path)
            continue
        checked.add(path)
        if hashlib.sha256(candidate.read_bytes()).hexdigest() != expected:
            mismatched.append(path)
    return sorted(checked), sorted(mismatched), sorted(unchecked), excluded


def reverify_inputs(
    plan: dict[str, Any], root: Path, repo: str | None = None, commit: str | None = None
) -> dict[str, Any]:
    """Check every declared input the workspace can actually supply.

    The verdict must not depend on how complete the workspace happens to be.
    Each declared input is compared against its own recorded digest:

    * present and matching - checked;
    * present and different - the plan no longer describes this configuration,
      so the caller must fail closed, however many other inputs are missing;
    * absent - unchecked, named in ``unchecked_paths`` and never counted as a pass;
    * the target repository's own - excluded, with the reason and the commit they
      are bound to instead.

    ``repo`` names the repository under verification. Its own declared inputs are
    excluded: they are already bound twice over, by the commit being verified and
    by the report's own input hashes, and letting a caller's working tree decide
    them would make an uncommitted edit change the verdict for an older commit.
    The manifest is what binds the *rest* of the ecosystem. That exclusion is a
    statement about the plan baseline, not a proof that the target commit's bytes
    equal the recorded ones, so the entries say which commit they are bound to.

    ``verified`` means the applicable scope is *complete*: every declared input is
    either checked and matching, or excluded with a reason. A workspace that
    leaves inputs unchecked is partial evidence, and says so.
    """
    manifest = _manifest(plan)
    if not manifest:
        return {"verified": False, "total": 0, "checked": 0, "unchecked": 0,
                "unchecked_paths": [], "excluded": [], "reason": "plan declares no input paths"}
    root = Path(root)
    checked, mismatched, unchecked, excluded = _classify(manifest, root, repo, commit)
    if mismatched:
        raise PlanError(
            "plan input digest does not match the workspace for "
            + ", ".join(mismatched)
            + ": the plan was modified or the configuration moved since it was written"
        )
    total = len(checked) + len(unchecked) + len(excluded)
    scope = f"{len(checked)} of {total} plan inputs checked"
    if excluded:
        scope += f"; {len(excluded)} excluded because they belong to {repo} and are bound to {commit}"
    if unchecked:
        scope += f"; {len(unchecked)} unchecked because they are absent"
    return {
        "verified": not unchecked,
        "total": total,
        "checked": len(checked),
        "unchecked": len(unchecked),
        "unchecked_paths": unchecked,
        "excluded": excluded,
        "reason": scope + ("; every present input matches the plan" if checked else ""),
    }