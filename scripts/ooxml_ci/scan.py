"""Transient observation: ref resolution, repo identity and scan diagnostics.

Nothing here may end up inside the plan: HEADs, worktrees, remote
reachability, resolved refs and timings are only ever written to the scan report.
"""

from __future__ import annotations

import pathlib
from typing import Any

from . import deps, gitfacts
from .facts import HOST_KEY
from .inputs import checkout_dir
from .plan import counts
from .urls import normalize_repo


def _error(code: str, where: str, detail: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "level": "error", "where": where, "detail": detail, **extra}


def _warning(code: str, where: str, detail: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "level": "warning", "where": where, "detail": detail, **extra}


def _unverifiable(where: str, detail: str, required: bool = True) -> dict[str, Any]:
    return {
        "code": "unverifiable",
        "level": "unverifiable",
        "required": required,
        "where": where,
        "detail": detail,
    }


def _remote_for(edge: dict[str, Any], target: dict[str, Any], diagnostics: list) -> str | None:
    """Query the declared URL, and report when it is not the checkout's origin."""
    declared_url = edge["declared"].get("url")
    origin = target.get("remote_url")
    if declared_url and origin and normalize_repo(declared_url) != normalize_repo(origin):
        diagnostics.append(
            _error(
                "policy_repo_mismatch",
                f"{edge['from']} -> {edge['to']}",
                f"declared URL {declared_url} != checkout origin {origin}",
                direction="remote_mismatch",
            )
        )
    return declared_url or origin


def _classify(
    edge: dict[str, Any],
    raw: str,
    remote_url: str | None,
    root: pathlib.Path,
    offline: bool,
    timeout: int,
    cache: dict[str, Any],
    allow_fetch: bool,
) -> dict[str, Any]:
    if offline or not remote_url:
        why = "offline" if offline else "no remote configured for the declared target"
        return {"kind": "unverifiable", "reason": why}
    listing = gitfacts.remote_refs(remote_url, root, timeout, cache)
    directory = checkout_dir(root, edge["to"])
    return gitfacts.classify_remote_ref(
        raw, edge["declared"].get("ref_declared_kind", "unknown"), listing, directory, timeout, allow_fetch
    )


def _ref_diagnostics(edge: dict[str, Any], raw: str, resolved: dict, remote_url: str | None) -> list:
    where = f"{edge['from']} -> {edge['to']}"
    kind = resolved.get("kind")
    if kind == "unverifiable":
        return [_unverifiable(where, resolved.get("reason", "unknown"))]
    if kind == "missing":
        return [_error("missing_ref", where, f"{raw} not found on {remote_url}")]
    if kind == "branch":
        return [_error("unreproducible_ref", where, f"{raw} is a branch")]
    if kind == "full_commit" and edge.get("purpose") != "engine_ci_snapshot":
        return [_warning("non_release_ref", where, f"{raw} is a raw commit")]
    return []


def _lock_mismatch(edge: dict[str, Any], resolved: dict) -> list[dict[str, Any]]:
    expected = edge["expected"]["commit"]
    actual = resolved.get("commit")
    if not expected or not actual or expected == actual:
        return []
    return [
        _error(
            "lock_commit_mismatch",
            f"{edge['from']} -> {edge['to']}",
            f"{expected} recorded by {edge['expected']['source']}, remote resolves {actual}",
        )
    ]


def _ref_entry(
    edge: dict[str, Any], raw: str, remote_url: str | None, resolved: dict, target: dict
) -> dict[str, Any]:
    return {
        "from": edge["from"],
        "to": edge["to"],
        "kind": edge["kind"],
        "purpose": edge.get("purpose"),
        "ref": raw,
        "declared_kind": edge["declared"].get("ref_declared_kind"),
        "remote": remote_url,
        "resolved": resolved,
        "expected_commit": edge["expected"]["commit"],
        "expected_source": edge["expected"]["source"],
        "target_head": target.get("head"),
    }


def _edge_refs(
    root: pathlib.Path, policy: dict[str, Any], plan: dict[str, Any], facts: dict[str, Any], offline: bool
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    timeout = int((policy.get("scan") or {}).get("ref_timeout_seconds", 25))
    allow_fetch = bool((policy.get("scan") or {}).get("allow_fetch_sha"))
    cache: dict[str, Any] = {}
    entries: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for edge in plan["edges"]:
        declared = edge["declared"]
        raw = declared.get("ref_raw")
        if not raw:
            continue
        if edge.get("purpose") == "workflow_uses":
            continue  # CI refs are judged by _ci_refs
        target = facts["checkouts"].get(edge["to"], {})
        remote_url = _remote_for(edge, target, diagnostics)
        resolved = _classify(edge, raw, remote_url, root, offline, timeout, cache, allow_fetch)
        entries.append(_ref_entry(edge, raw, remote_url, resolved, target))
        diagnostics.extend(_ref_diagnostics(edge, raw, resolved, remote_url))
        if declared.get("ref_declared_kind") != "release_tag":
            diagnostics.extend(_lock_mismatch(edge, resolved))
    return entries, diagnostics


def _ci_refs(
    root: pathlib.Path, policy: dict[str, Any], plan: dict[str, Any], facts: dict[str, Any], offline: bool
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Workflow ``uses:`` refs get the same query, classification and recording as pins."""
    config = policy.get("scan") or {}
    timeout = int(config.get("ref_timeout_seconds", 25))
    allow_fetch = bool(config.get("allow_fetch_sha"))
    cache: dict[str, Any] = {}
    entries: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for edge in plan["edges"]:
        if edge.get("purpose") != "workflow_uses":
            continue
        raw = edge["declared"].get("ref_raw")
        target = facts["checkouts"].get(edge["to"], {})
        remote_url = _remote_for(edge, target, diagnostics)
        site = (edge.get("sites") or [{}])[0]
        where = f"{site.get('file', '?')}:{site.get('line', '?')}"
        if offline or not remote_url:
            why = "offline" if offline else "no remote configured for the declared target"
            resolved: dict[str, Any] = {"kind": "unverifiable", "reason": why}
        else:
            listing = gitfacts.remote_refs(remote_url, root, timeout, cache)
            resolved = gitfacts.classify_remote_ref(
                raw,
                edge["declared"].get("ref_declared_kind", "unknown"),
                listing,
                checkout_dir(root, edge["to"]),
                timeout,
                allow_fetch,
            )
        entries.append(_ref_entry(edge, raw, remote_url, resolved, target))
        if resolved["kind"] == "branch":
            diagnostics.append(_error("floating_ci_ref", where, f"uses {edge['to']}@{raw}"))
        elif resolved["kind"] == "missing":
            diagnostics.append(_error("missing_ref", where, f"{raw} not found on {remote_url}"))
        elif resolved["kind"] == "unverifiable":
            diagnostics.append(_unverifiable(where, resolved.get("reason", "unknown")))
    return entries, diagnostics


def scan(
    root: pathlib.Path, policy: dict[str, Any], plan: dict[str, Any], offline: bool
) -> dict[str, Any]:
    timeout = int((policy.get("scan") or {}).get("ref_timeout_seconds", 25))
    facts = gitfacts.local_facts(root, policy, timeout)
    diagnostics = list(facts["diagnostics"])
    refs, ref_diagnostics = _edge_refs(root, policy, plan, facts, offline)
    ci_refs, ci_diagnostics = _ci_refs(root, policy, plan, facts, offline)
    refs.extend(ci_refs)
    diagnostics.extend(ref_diagnostics)
    diagnostics.extend(ci_diagnostics)
    diagnostics.sort(key=lambda item: (item["code"], item["where"]))
    return {
        "schema_version": 1,
        "kind": "ecosystem-scan",
        "host": HOST_KEY,
        "note": "Transient observation. Never merged into the committed plan.",
        "environment": deps.observation(),
        "checkouts": facts["checkouts"],
        "duplicate_repo_identity": facts["duplicates"],
        "refs": refs,
        "diagnostics": diagnostics,
        "diagnostic_counts": counts(diagnostics),
        "plan_inputs_digest": plan["inputs_digest"],
    }