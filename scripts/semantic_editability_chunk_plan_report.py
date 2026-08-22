"""Chunk plan summary and markdown rendering."""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from replay_timeout_metrics import replay_timeout_counts


def build_summary(
    chunks: list[dict[str, Any]],
    row_sets: list[dict[str, Any]],
    skipped: dict[str, int],
    *,
    chunk_size: int,
    package_limit: int,
    include_boundary: bool,
    remaining: dict[str, Any],
    remaining_path: Path,
    row_ids_path: Path,
    root: Path,
    plan_filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selected_rows = sum(chunk["planned_row_count"] for chunk in chunks)
    known_boundaries = remaining.get("known_boundary_packages", [])
    replay_timeouts = remaining.get("known_replay_timeout_packages", [])
    replay_counts = replay_timeout_counts(replay_timeouts)
    filters = plan_filters or {}
    return {
        "schema_version": "semantic-editability-chunk-plan-v2",
        "plan_scope": _plan_scope(filters),
        "plan_filters": filters,
        "source_remaining_bucket_summary": _rel(remaining_path, root),
        "starting_semantic_editable_count": remaining.get("starting_semantic_editable_count"),
        "starting_remaining_count": remaining.get("starting_remaining_count"),
        "chunk_size": chunk_size,
        "package_limit": package_limit,
        "include_boundary": include_boundary,
        "chunk_count": len(chunks),
        "planned_chunk_count": len(chunks),
        "selected_row_count": selected_rows,
        "selected_package_count": len({chunk["package_id"] for chunk in chunks}),
        "known_boundary_package_count": len(known_boundaries),
        **replay_counts,
        "skipped_known_boundary_count": int(skipped.get("known_office_boundary", 0)),
        "skipped_known_replay_timeout_count": int(skipped.get("known_replay_timeout", 0)),
        "skipped_counts": dict(skipped),
        "row_ids_artifact": _rel(row_ids_path, root),
        "row_ids_artifact_hash": _row_ids_artifact_hash(row_sets),
        "packages": _packages(chunks, remaining),
        "chunks": chunks,
    }


def markdown(summary: dict[str, Any]) -> str:
    lines = ["# Semantic Editability Chunk Plan", ""]
    lines += [
        f"- Plan scope: `{summary.get('plan_scope', 'global_next_plan')}`",
        f"- Plan filters: `{json.dumps(summary.get('plan_filters', {}), sort_keys=True)}`",
        f"- Starting semantic-editable: {summary.get('starting_semantic_editable_count')}",
        f"- Starting remaining: {summary.get('starting_remaining_count')}",
        f"- Selected rows: {summary['selected_row_count']}",
        f"- Planned chunks: {summary['planned_chunk_count']}",
        f"- Packages: {summary['selected_package_count']}",
        f"- Known boundary packages: {summary['known_boundary_package_count']}",
        f"- Known replay timeout packages: {summary['known_replay_timeout_package_count']}",
        f"- Known replay timeout entries: {summary.get('known_replay_timeout_entry_count', 0)}",
        f"- Known replay timeout package-scope entries: {summary.get('known_replay_timeout_package_scope_count', 0)}",
        f"- Known replay timeout operation-scope entries: {summary.get('known_replay_timeout_operation_scope_count', 0)}",
        f"- Row IDs artifact: `{summary['row_ids_artifact']}`",
        "",
    ]
    lines += ["## Skipped Counts", ""]
    lines += [f"- `{key}`: {value}" for key, value in summary["skipped_counts"].items()] or ["- none"]
    lines += ["", "## Packages", "", "| Package | Family | Operation(s) | Chunks | Rows | MB | Risk |", "| --- | --- | --- | ---: | ---: | ---: | --- |"]
    for pkg in summary["packages"][:50]:
        lines.append(
            f"| `{pkg['package_id']}` | `{pkg['family']}` | `{', '.join(pkg['operation_ids'])}` | {pkg['chunk_count']} | "
            f"{pkg['planned_row_count']} | {pkg.get('estimated_package_mb')} | {pkg['estimated_risk']} |"
        )
    lines += ["", "## First 50 Chunks", "", "| Chunk | Package | Family | Rows | Risk |", "| --- | --- | --- | ---: | --- |"]
    for chunk in summary["chunks"][:50]:
        lines.append(
            f"| `{chunk['chunk_id']}` | `{chunk['package_id']}` | "
            f"`{chunk['family']}` | {chunk['planned_row_count']} | {chunk['estimated_risk']} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def _packages(chunks: list[dict[str, Any]], remaining: dict[str, Any]) -> list[dict[str, Any]]:
    by_candidate = {
        (str(row.get("package_id", "")), str(row.get("family", "")), str(row.get("operation_id", ""))): row
        for row in remaining.get("candidate_packages", [])
    }
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    order: list[tuple[str, str]] = []
    for chunk in chunks:
        key = (chunk["package_id"], chunk["family"])
        if key not in grouped:
            order.append(key)
        grouped[key].append(chunk)
    packages = []
    for package_id, family in order:
        items = grouped[(package_id, family)]
        operations = _operations(items)
        candidate = by_candidate.get((package_id, family, operations[0]), {}) if len(operations) == 1 else {}
        packages.append(_package_row(package_id, family, items, candidate))
    return packages


def _package_row(package_id: str, family: str, items: list[dict[str, Any]], candidate: dict[str, Any]) -> dict[str, Any]:
    rows = sum(int(item.get("planned_row_count", 0)) for item in items)
    return {
        "package_id": package_id,
        "format": items[0].get("format", ""),
        "family": family,
        "operation_ids": _operations(items),
        "chunk_count": len(items),
        "planned_row_count": rows,
        "first_chunk_id": items[0]["chunk_id"],
        "last_chunk_id": items[-1]["chunk_id"],
        "estimated_package_mb": items[0].get("estimated_package_mb"),
        "estimated_risk": _max_risk(items),
        "candidate_planned_safe_rows": candidate.get("planned_safe_rows"),
        "candidate_total_remaining_rows": candidate.get("total_remaining_rows"),
        "candidate_recommended_action": candidate.get("recommended_action", ""),
    }


def _operations(items: list[dict[str, Any]]) -> list[str]:
    return sorted({str(op) for item in items for op in item.get("operation_ids", []) if op})


def _plan_scope(filters: dict[str, Any]) -> str:
    keys = ("package_id", "family", "format", "operation_id")
    return "exact_replan" if any(filters.get(key) for key in keys) else "global_next_plan"


def _max_risk(items: list[dict[str, Any]]) -> str:
    return "medium" if any(item.get("estimated_risk") == "medium" for item in items) else "low"


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _row_ids_artifact_hash(rows: list[dict[str, Any]]) -> str:
    payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    return hashlib.sha256(payload.encode()).hexdigest()
