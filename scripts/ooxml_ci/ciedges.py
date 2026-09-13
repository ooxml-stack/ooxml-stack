"""CI edges: environment.json snapshots and workflow ``uses:``/``clone`` references."""

from __future__ import annotations

from typing import Any

from . import urls
from .facts import Facts
from .inputs import node_index
from .parsers import classify_declared_ref


def _error(code: str, where: str, detail: str) -> dict[str, Any]:
    return {"code": code, "level": "error", "where": where, "detail": detail}


def _ci_edge(
    repo: str, target: str, purpose: str, ref: str | None, relpath: str, line: int, url: str | None
) -> dict[str, Any]:
    return {
        "from": repo,
        "to": target,
        "kind": "ci",
        "role": "ci",
        "group": None,
        "purpose": purpose,
        "declared": {
            "section": "workflow",
            "url": url,
            "ref_raw": ref,
            "ref_declared_kind": classify_declared_ref(ref),
            "version_spec": None,
        },
        "expected": {"version": None, "commit": None, "source": None},
        "source_file": relpath,
        "sites": [{"file": relpath, "line": line}],
    }


def _undeclared(relpath: str, line: int, detail: str) -> dict[str, Any]:
    return _error("policy_node_mismatch", f"{relpath}:{line}", detail)


def _uses_edges(facts: Facts, nodes: dict, owner: str, scan_global: bool, diagnostics: list) -> list:
    edges: list[dict[str, Any]] = []
    for relpath, entries in sorted(facts.workflow_uses.items()):
        repo = relpath.split("/", 1)[0]
        for entry in entries:
            if not scan_global and not entry["name"].startswith(f"{owner}/"):
                continue
            target = urls.repo_from_uses(entry["name"])
            if target in nodes:
                edges.append(
                    _ci_edge(
                        repo,
                        target,
                        "workflow_uses",
                        entry["ref"],
                        relpath,
                        entry["line"],
                        urls.url_from_uses(entry["name"]),
                    )
                )
            elif urls.owner_from_uses(entry["name"]) == owner:
                diagnostics.append(
                    _undeclared(
                        relpath,
                        entry["line"],
                        f"workflow uses {entry['name']!r} names undeclared node {target!r}",
                    )
                )
    return edges


def _clone_edges(facts: Facts, nodes: dict, owner: str, diagnostics: list) -> list:
    edges: list[dict[str, Any]] = []
    for relpath, entries in sorted(facts.clone_refs.items()):
        repo = relpath.split("/", 1)[0]
        for entry in entries:
            target = urls.repo_name(entry["url"])
            if target in nodes:
                edges.append(
                    _ci_edge(repo, target, "workflow_clone", None, relpath, entry["line"], entry["url"])
                )
            elif urls.owner_of(entry["url"]) == owner:
                diagnostics.append(
                    _undeclared(
                        relpath,
                        entry["line"],
                        f"workflow clone {entry['url']!r} names undeclared node {target!r}",
                    )
                )
    return edges


def workflow_edges(facts: Facts, diagnostics: list) -> list[dict[str, Any]]:
    """``uses:`` and ``git clone`` references become ci edges into the impact graph.

    A reference owned by the configured ecosystem owner that names no policy node
    is a structural ``policy_node_mismatch``; third-party actions are ignored.
    """
    nodes = node_index(facts.policy)
    config = facts.policy.get("workflows") or {}
    owner = config.get("uses_owner", "ooxml-stack")
    scan_global = config.get("scan_global_uses", True)
    return _uses_edges(facts, nodes, owner, scan_global, diagnostics) + _clone_edges(
        facts, nodes, owner, diagnostics
    )


def _snapshot_edges(facts: Facts, source, owner: str, file_ref: str, diagnostics: list) -> list:
    nodes = node_index(facts.policy)
    edges = []
    for name, commit in (facts.environment.get("repositories") or {}).items():
        if name not in nodes:
            diagnostics.append(
                _error(
                    "policy_node_mismatch",
                    f"{file_ref}:repositories",
                    f"snapshot pins unknown node {name!r}",
                )
            )
            continue
        edges.append(
            {
                "from": owner,
                "to": name,
                "kind": "ci",
                "role": "ci",
                "group": None,
                "purpose": source.get("purpose"),
                "snapshot_owner": owner,
                "declared": {
                    "section": source.get("field"),
                    "url": None,
                    "ref_raw": commit,
                    "ref_declared_kind": "sha",
                    "version_spec": None,
                },
                "expected": {"version": None, "commit": commit, "source": file_ref},
                "source_file": file_ref,
            }
        )
    return edges


def _pinned_commit(facts: Facts, field: str | None) -> Any:
    pinned: Any = facts.environment
    for part in (field or "").split("."):
        pinned = pinned.get(part) if isinstance(pinned, dict) else None
    return pinned


def _corpus_edge(facts: Facts, source, owner: str, file_ref: str, diagnostics: list) -> list:
    nodes = node_index(facts.policy)
    target = "ooxml-native-corpus"
    if target not in nodes:
        diagnostics.append(
            _error(
                "policy_node_mismatch",
                f"{file_ref}:corpus.release_tag",
                f"data edge targets undeclared node {target!r}",
            )
        )
        return []
    corpus = facts.environment.get("corpus") or {}
    return [
        {
            "from": owner,
            "to": target,
            "kind": "data",
            "role": "data",
            "group": None,
            "purpose": source.get("purpose"),
            "declared": {
                "section": source.get("field"),
                "url": None,
                "release_tag": corpus.get("release_tag"),
                "tag_source": f"{file_ref}:{source.get('field')}",
                "ref_raw": corpus.get("release_tag"),
                "ref_declared_kind": "release_tag",
                "version_spec": None,
            },
            "expected": {
                "version": corpus.get("release_tag"),
                "commit": _pinned_commit(facts, source.get("pinned_commit_field")),
                "source": file_ref,
                "commit_field": source.get("pinned_commit_field"),
            },
            "source_file": file_ref,
        }
    ]


def environment_edges(facts: Facts, diagnostics: list) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for source in facts.policy.get("edge_sources", []):
        if source.get("from") != "environment_json" or not source.get("file"):
            continue
        file_ref = source["file"]
        owner = file_ref.split("/", 1)[0]
        field = source.get("field", "")
        if field == "repositories":
            edges.extend(_snapshot_edges(facts, source, owner, file_ref, diagnostics))
        elif field == "corpus.release_tag":
            edges.extend(_corpus_edge(facts, source, owner, file_ref, diagnostics))
    return edges