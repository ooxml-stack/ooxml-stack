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


def _digest_over(root: Path, relpaths: list[str]) -> str:
    digest = hashlib.sha256()
    for relpath in sorted(relpaths):
        digest.update(relpath.encode("utf-8"))
        digest.update(b"\0")
        digest.update((root / relpath).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def reverify_inputs(plan: dict[str, Any], root: Path) -> dict[str, Any]:
    """Re-derive ``inputs_digest`` from the workspace when the inputs are present.

    Returns ``{"verified": bool, "reason": str}``. When every declared input can
    be read, a mismatch means the plan no longer describes the configuration it
    claims to, and the caller must fail rather than trust the stored digest.
    """
    relpaths = list(plan["payload"].get("inputs") or [])
    if not relpaths:
        return {"verified": False, "reason": "plan declares no input paths"}
    missing = [relpath for relpath in relpaths if not (Path(root) / relpath).is_file()]
    if missing:
        return {
            "verified": False,
            "reason": f"{len(missing)} of {len(relpaths)} plan inputs are not present in the workspace",
        }
    derived = _digest_over(Path(root), relpaths)
    if derived != plan["inputs_digest"]:
        raise PlanError(
            "plan inputs_digest does not match the workspace: the plan was modified "
            "or the configuration moved since it was written"
        )
    return {"verified": True, "reason": "inputs_digest re-derived from the workspace"}