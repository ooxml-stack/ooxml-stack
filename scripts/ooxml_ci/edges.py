"""Edge derivation: dependency, environment-snapshot and workflow edges."""

from __future__ import annotations

from typing import Any

from . import ciedges, urls, versions
from .facts import Facts
from .inputs import node_index

ROLE_BY_KIND = {
    "runtime": "runtime",
    "dev": "dev",
    "codegen": "codegen",
    "ci": "ci",
    "data": "data",
}
PIP_KINDS = ("runtime", "dev", "codegen")


def _where(declaration) -> str:
    suffix = f"[{declaration.group}]" if declaration.group else ""
    return f"{declaration.repo}/{declaration.section}{suffix}"


def _error(code: str, where: str, detail: str) -> dict[str, Any]:
    return {"code": code, "level": "error", "where": where, "detail": detail}


def missing_input_diagnostics(facts: Facts) -> list[dict[str, Any]]:
    return [_error("missing_input", item["path"], item["why"]) for item in facts.missing]


def _source_selector(source: dict[str, Any]) -> tuple[str | None, str]:
    """``uv.sources`` keys carry the selector kind: tag, rev or branch."""
    for key in ("tag", "rev", "branch"):
        value = source.get(key)
        if value:
            return value, key
    return None, "unknown"


def effective_source(
    declaration, source: dict[str, Any] | None
) -> tuple[str | None, str | None, str, list]:
    """``uv.sources`` relocates a dependency; it wins, and conflicts are reported."""
    if not source:
        return declaration.url, declaration.ref_raw, declaration.ref_declared_kind, []
    source_url = source.get("git")
    source_ref, source_kind = _source_selector(source)
    diags: list[dict[str, Any]] = []
    if (
        declaration.url
        and source_url
        and urls.normalize_repo(declaration.url) != urls.normalize_repo(source_url)
    ):
        diags.append(
            _error(
                "source_override_conflict",
                _where(declaration),
                f"{declaration.name} URL {declaration.url} != uv.sources URL {source_url}",
            )
        )
    if declaration.ref_raw and source_ref and declaration.ref_raw != source_ref:
        diags.append(
            _error(
                "source_override_conflict",
                _where(declaration),
                f"{declaration.name} ref {declaration.ref_raw} != uv.sources ref {source_ref}",
            )
        )
    if source_ref:
        return source_url or declaration.url, source_ref, source_kind, diags
    return source_url or declaration.url, declaration.ref_raw, declaration.ref_declared_kind, diags


def dependency_diagnostics(declaration, url, ref, locked: dict[str, Any]) -> list[dict[str, Any]]:
    where = _where(declaration)
    name = declaration.name
    diags: list[dict[str, Any]] = []
    if declaration.kind in PIP_KINDS and url and not ref:
        diags.append(
            _error("unpinned_dependency", where, f"{name} is a git dependency without tag/rev")
        )
    if url and not locked:
        diags.append(
            _error("lock_missing", f"{declaration.repo}/uv.lock", f"{name} is declared but absent from the lock")
        )
    if url and locked and not locked.get("expected_commit"):
        diags.append(
            _error(
                "lock_missing",
                f"{declaration.repo}/uv.lock",
                f"{name} is locked from git without a full commit SHA",
            )
        )
    if url and locked.get("url") and urls.normalize_repo(url) != urls.normalize_repo(locked["url"]):
        diags.append(
            _error(
                "source_override_conflict",
                where,
                f"{name} resolves to {url} but the lock records {locked['url']}",
            )
        )
    version = locked.get("version")
    if version and declaration.version_spec:
        verdict = versions.satisfies(version, declaration.version_spec)
        if verdict is None:
            diags.append(
                _error(
                    "unsupported_constraint",
                    where,
                    f"cannot evaluate version spec {declaration.version_spec!r} for {name}",
                )
            )
        elif verdict is False:
            diags.append(
                _error(
                    "constraint_violation",
                    where,
                    f"{name} {version} violates {declaration.version_spec}",
                )
            )
    return diags


def dependency_edge(facts: Facts, declaration) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    nodes = node_index(facts.policy)
    name = declaration.name
    source = facts.uv_sources.get(declaration.repo, {}).get(name)
    url, ref, declared_kind, diags = effective_source(declaration, source)
    if not url and name not in nodes:
        return None, diags  # an ordinary PyPI dependency, not an ecosystem edge
    if name not in nodes:
        diags.append(
            _error("policy_node_mismatch", _where(declaration), f"dependency {name!r} is not a policy node")
        )
        return None, diags
    locked = facts.locks.get(declaration.repo, {}).get(name, {})
    diags.extend(dependency_diagnostics(declaration, url, ref, locked))
    edge = {
        "from": declaration.repo,
        "to": name,
        "kind": declaration.kind,
        "role": ROLE_BY_KIND.get(declaration.kind, declaration.kind),
        "group": declaration.group,
        "purpose": "dependency",
        "declared": {
            "section": declaration.section,
            "url": url,
            "ref_raw": ref,
            "ref_declared_kind": declared_kind,
            "version_spec": declaration.version_spec or None,
        },
        "expected": {
            "version": locked.get("version"),
            "commit": locked.get("expected_commit"),
            "source": f"{declaration.repo}/uv.lock" if locked else None,
        },
        "source_file": f"{declaration.repo}/pyproject.toml",
    }
    return edge, diags


def _declared_url(edge: dict[str, Any]) -> str:
    url = edge["declared"].get("url")
    return urls.normalize_repo(url) if url else ""


def dedupe(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse identical edges, keeping every declaration site.

    The key includes the normalized URL and the declared selector: two references
    that name different repositories, or the same repository through a different
    selector, are different claims and each keeps its own verification duty.
    """
    merged: dict[tuple, dict[str, Any]] = {}
    for edge in edges:
        key = (
            edge["from"],
            edge["to"],
            edge["kind"],
            edge.get("purpose"),
            _declared_url(edge),
            edge["declared"].get("ref_declared_kind"),
            edge["declared"].get("ref_raw"),
            edge["declared"].get("version_spec"),
        )
        if key not in merged:
            merged[key] = edge
            continue
        kept = merged[key]
        sites = kept.setdefault("sites", [])
        for site in edge.get("sites", []):
            if site not in sites:
                sites.append(site)
    return list(merged.values())


def _edge_sort_key(edge: dict[str, Any]) -> tuple:
    return (
        edge["from"],
        edge["to"],
        edge["kind"],
        edge.get("purpose") or "-",
        _declared_url(edge),
        edge["declared"].get("ref_raw") or "",
    )


def build_edges(facts: Facts) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    edges: list[dict[str, Any]] = []
    diagnostics = missing_input_diagnostics(facts)
    for declaration in facts.declarations:
        edge, diags = dependency_edge(facts, declaration)
        diagnostics.extend(diags)
        if edge is not None:
            edges.append(edge)
    edges.extend(ciedges.environment_edges(facts, diagnostics))
    edges.extend(ciedges.workflow_edges(facts, diagnostics))
    edges = dedupe(edges)
    edges.sort(key=_edge_sort_key)
    return edges, diagnostics