"""The committed plan: nodes, edges, graphs, full bindings and diagnostics."""

from __future__ import annotations

from typing import Any

from . import edges as edge_mod
from . import full as full_mod
from . import graphs, versions
from .facts import HOST_KEY, POLICY_RELPATH, Facts


def _nodes(facts: Facts) -> list[dict[str, Any]]:
    out = []
    for node in facts.policy["nodes"]:
        version, source = facts.versions.get(node["key"], (None, None))
        out.append(
            {
                "key": node["key"],
                "role": node["role"],
                "layer": node.get("layer"),
                "cadence": node.get("cadence"),
                "visibility": node.get("visibility"),
                "experimental": bool(node.get("experimental", False)),
                "release_participation": node.get("release_participation", False),
                "version": version,
                "version_source": source,
            }
        )
    return out


def counts(diagnostics: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in diagnostics:
        key = f"{item['level']}:{item['code']}"
        out[key] = out.get(key, 0) + 1
    return out


def _cycle_diagnostic(order: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": "release_order_cycle",
        "level": "error",
        "where": "partial release order",
        "detail": "cycle in runtime/codegen order graph: " + " -> ".join(order["cycle"]),
    }


EXCLUDED_FROM_PLAN = [
    {"item": "git HEAD of every repository", "where": "scan"},
    {"item": "worktrees, common-dir, checkout paths", "where": "scan"},
    {"item": "resolved ref kinds and current commit of floating refs", "where": "scan"},
    {"item": "remote reachability, timings, clock", "where": "scan"},
    {"item": "expected commits recorded by locks/environment (file facts)", "where": "plan"},
]


def build_plan(facts: Facts) -> dict[str, Any]:
    edge_list, diagnostics = edge_mod.build_edges(facts)
    groups = versions.version_groups(edge_list)
    diagnostics.extend(versions.skew_diagnostics(facts, groups))
    bindings, binding_diagnostics = full_mod.full_bindings(facts)
    diagnostics.extend(binding_diagnostics)
    diagnostics.extend(facts.workflow_errors)

    order = graphs.order_graph(edge_list)
    if order["cycle"]:
        diagnostics.append(_cycle_diagnostic(order))

    used = sorted({edge["to"] for edge in edge_list} | {edge["from"] for edge in edge_list})
    declared = sorted(node["key"] for node in facts.policy["nodes"])
    impact_roots = sorted(set(declared) | set(used))
    return {
        "schema_version": 1,
        "kind": "ecosystem-plan",
        "host": HOST_KEY,
        "policy_file": f"{HOST_KEY}/{POLICY_RELPATH}",
        "contract": (
            "Deterministic function of the selected input file paths and their bytes, "
            "read from the working tree (uncommitted edits included). Contains no HEAD, "
            "worktree, clock, network or resolved-ref fact; those live in the scan report."
        ),
        "nodes": _nodes(facts),
        "unreferenced_nodes": [key for key in declared if key not in used],
        "edge_sources": facts.policy.get("edge_sources", []),
        "edge_kinds_without_source": facts.policy.get("edge_kinds_without_source", []),
        "edges": edge_list,
        "full": bindings,
        "version_groups": groups,
        "graphs": {
            "impact": {root: graphs.impact_graph(edge_list, root) for root in impact_roots},
            "partial_release_order": order,
        },
        "diagnostics": sorted(
            diagnostics, key=lambda item: (item["code"], item["where"], item["detail"])
        ),
        "diagnostic_counts": counts(diagnostics),
        "inputs_digest": facts.digest,
        "inputs": facts.manifest,
        "excluded_from_plan": EXCLUDED_FROM_PLAN,
    }