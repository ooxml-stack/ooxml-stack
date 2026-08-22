#!/usr/bin/env python3
"""Rank high-yield semantic editability buckets before replay."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

from former_preserve_only_math_policy import math_metadata_allowed
from former_preserve_only_promoted_index import promoted_index
from former_preserve_only_value_policy import checked_requested_value, next_requested_value
from semantic_editability_failed_rows import failed_source_ids
from semantic_editability_row_filter import eligible_rows
from semantic_editability_skip_packages import chunk_plan_skip_packages
from semantic_editability_unlock_common import read_json, read_jsonl, table, write_json, write_md

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "release-evidence/former-preserve-only-semantic-editability"
HYDRATED = EVIDENCE / "operation-hydration-ledger.jsonl"
REMAINING = EVIDENCE / "remaining-bucket-summary.json"
ROWS = EVIDENCE / "promotion-rows.jsonl"
CHECKPOINT = EVIDENCE / "chunk-promotion-checkpoint.json"
STAGED = EVIDENCE / "staged-rows"
OUT_JSON = EVIDENCE / "high-yield-candidates.json"
OUT_MD = EVIDENCE / "high-yield-candidates.md"

def main() -> int:
    promoted_sources, promoted_targets = promoted_index(ROWS)
    ranking = build_ranking(
        read_jsonl(HYDRATED),
        read_json(REMAINING),
        promoted_sources=promoted_sources,
        promoted_targets=promoted_targets,
        failed_sources=failed_source_ids(CHECKPOINT, STAGED),
    )
    write_json(OUT_JSON, ranking)
    write_md(OUT_MD, markdown(ranking))
    print(json.dumps({"ranking": str(OUT_JSON), "dashboard": str(OUT_MD)}, indent=2))
    return 0

def build_ranking(
    hydrated: list[dict[str, Any]],
    remaining: dict[str, Any],
    *,
    promoted_sources: set[str] | None = None,
    promoted_targets: set[tuple[str, str, str, str]] | None = None,
    failed_sources: set[str] | None = None,
    runner_planner: Callable[[list[dict[str, Any]]], dict[str, int]] | None = None,
) -> dict[str, Any]:
    promoted_sources = promoted_sources or set()
    promoted_targets = promoted_targets or set()
    failed_sources = failed_sources or set()
    runner_planner = runner_planner or fast_runner_counts
    normal_skips = chunk_plan_skip_packages(remaining, include_boundary=False)
    boundary_skips = chunk_plan_skip_packages(remaining, include_boundary=True)
    buckets = [
        _bucket(rows, promoted_sources, promoted_targets, failed_sources, normal_skips, boundary_skips, runner_planner)
        for rows in _groups(hydrated).values()
    ]
    buckets = sorted([row for row in buckets if row["potential_row_gain"]], key=_sort_key)
    classifications = Counter(row["classification"] for row in buckets)
    actionable = {"promotion_ready", "office_boundary_only", "schema_policy_blocked", "public_path_blocked"}
    yield_rows = [row for row in buckets if row["classification"] in actionable and row["potential_row_gain"] >= 50]
    return {
        "schema_version": "semantic-editability-high-yield-candidates-v1",
        "source_counts": {
            "starting_semantic_editable_count": remaining.get("starting_semantic_editable_count", 0),
            "starting_remaining_count": remaining.get("starting_remaining_count", 0),
            "bucket_count": len(buckets),
            "yield_50plus_count": len(yield_rows),
        },
        "classification_counts": dict(classifications.most_common()),
        "answers": {
            "yield_50plus": yield_rows[:50],
            "office_boundary_only": _top(buckets, "office_boundary_only", 50),
            "schema_policy_blocked": _top(buckets, "schema_policy_blocked", 25),
            "public_path_blocked": _top(buckets, "public_path_blocked", 25),
            "known_bad_or_timeout": _top(buckets, "known_bad_or_timeout", 25),
        },
        "top_buckets": buckets[:100],
    }

def _bucket(
    rows: list[dict[str, Any]],
    promoted_sources: set[str],
    promoted_targets: set[tuple[str, str, str, str]],
    failed_sources: set[str],
    normal_skips: dict[str, set[str]],
    boundary_skips: dict[str, set[str]],
    runner_planner: Callable[[list[dict[str, Any]]], dict[str, int]],
) -> dict[str, Any]:
    normal_rows, normal_counts = eligible_rows(rows, promoted_sources, promoted_targets, failed_sources, normal_skips, {})
    boundary_rows, boundary_counts = eligible_rows(rows, promoted_sources, promoted_targets, failed_sources, boundary_skips, {})
    normal_plan = _plan_counts(normal_rows, runner_planner)
    boundary_plan = _plan_counts(boundary_rows, runner_planner)
    classification = _classification(normal_counts, boundary_counts, normal_plan, boundary_plan)
    row = rows[0]
    return _base(row, rows, normal_counts, boundary_counts, normal_plan, boundary_plan) | {
        "classification": classification,
        "potential_row_gain": _potential(classification, normal_counts, boundary_counts, normal_plan, boundary_plan),
        "sample_row_ids": [str(item.get("row_id", "")) for item in rows[:5]],
    }


def _classification(
    normal_counts: Counter[str],
    boundary_counts: Counter[str],
    normal_plan: dict[str, int],
    boundary_plan: dict[str, int],
) -> str:
    if normal_plan.get("planned_safe_rows", 0):
        return "promotion_ready"
    if normal_counts.get("known_office_boundary", 0) and boundary_plan.get("planned_safe_rows", 0):
        return "office_boundary_only"
    if boundary_counts.get("known_replay_timeout", 0) or boundary_counts.get("known_row_level_failure", 0):
        return "known_bad_or_timeout"
    if boundary_counts.get("public_path_unsupported_part", 0):
        return "public_path_blocked"
    if _schema_policy_rows(normal_plan, boundary_plan):
        return "schema_policy_blocked"
    if boundary_counts.get("already_promoted", 0):
        return "already_promoted"
    return "other_blocked"


def _potential(
    classification: str,
    normal_counts: Counter[str],
    boundary_counts: Counter[str],
    normal_plan: dict[str, int],
    boundary_plan: dict[str, int],
) -> int:
    if classification == "promotion_ready":
        return int(normal_plan.get("planned_safe_rows", 0))
    if classification == "office_boundary_only":
        return int(boundary_plan.get("planned_safe_rows", 0))
    if classification == "schema_policy_blocked":
        return _schema_policy_rows(normal_plan, boundary_plan)
    if classification == "public_path_blocked":
        return int(boundary_counts.get("public_path_unsupported_part", 0))
    if classification == "known_bad_or_timeout":
        return int(boundary_counts.get("known_replay_timeout", 0) + boundary_counts.get("known_row_level_failure", 0))
    return int(sum(normal_counts.values()) + sum(boundary_counts.values()))


def _base(
    row: dict[str, Any],
    rows: list[dict[str, Any]],
    normal_counts: Counter[str],
    boundary_counts: Counter[str],
    normal_plan: dict[str, int],
    boundary_plan: dict[str, int],
) -> dict[str, Any]:
    return {
        "package_id": row.get("package_id", ""),
        "format": row.get("format", ""),
        "family": row.get("family", ""),
        "operation_id": row.get("operation_id", ""),
        "qname": row.get("qname", ""),
        "row_count": len(rows),
        "safe_planned_rows": int(normal_plan.get("planned_safe_rows", 0)),
        "boundary_included_planned_rows": int(boundary_plan.get("planned_safe_rows", 0)),
        "normal_skip_counts": dict(normal_counts.most_common()),
        "boundary_included_skip_counts": dict(boundary_counts.most_common()),
        "runner_counts": {key: value for key, value in boundary_plan.items() if key != "planned_safe_rows"},
    }


def _plan_counts(rows: list[dict[str, Any]], runner_planner: Callable[[list[dict[str, Any]]], dict[str, int]]) -> dict[str, int]:
    if not rows:
        return {"planned_safe_rows": 0}
    return {"planned_safe_rows": 0} | runner_planner(rows)


def fast_runner_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    planned, skipped_policy, skipped_overlap = 0, 0, 0
    seen: set[tuple[str, str]] = set()
    for index, row in enumerate(rows):
        if _runner_policy_blocked(row):
            skipped_policy += 1
            continue
        key = (str(row.get("part_name", "")), str(row.get("operation_target_selector", "")))
        if key in seen or _overlaps(key, seen):
            skipped_overlap += 1
            continue
        if not _requested_value_is_safe(row, index):
            skipped_policy += 1
            continue
        planned += 1
        seen.add(key)
    return {
        "planned_safe_rows": planned,
        "runner_policy_or_overlap_skipped_rows": skipped_overlap,
        "runner_schema_policy_skipped_rows": skipped_policy,
    }


def _runner_policy_blocked(row: dict[str, Any]) -> bool:
    selector = str(row.get("operation_target_selector", ""))
    unsafe_text = row.get("operation_id") == "math.run.set_text" and not selector.endswith("/m:r")
    return unsafe_text or not math_metadata_allowed(row)


def _requested_value_is_safe(row: dict[str, Any], index: int) -> bool:
    before = str(row.get("before_semantic_value", ""))
    try:
        requested = str(row.get("requested_semantic_value") or next_requested_value(before, index, row))
        checked_requested_value(before, requested, row)
    except ValueError as exc:
        if str(exc).startswith("schema_policy_unsafe_"):
            return False
        raise
    return requested != before


def _overlaps(key: tuple[str, str], seen: set[tuple[str, str]]) -> bool:
    part, selector = key
    return any(part == old_part and (selector.startswith(old + "/") or old.startswith(selector + "/")) for old_part, old in seen)


def _schema_policy_rows(normal_plan: dict[str, int], boundary_plan: dict[str, int]) -> int:
    return max(
        int(normal_plan.get("runner_schema_policy_skipped_rows", 0)),
        int(boundary_plan.get("runner_schema_policy_skipped_rows", 0)),
    )


def _groups(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str, str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (
            str(row.get("package_id", "")),
            str(row.get("format", "")),
            str(row.get("family", "")),
            str(row.get("operation_id", "")),
            str(row.get("qname", "")),
        )
        grouped[key].append(row)
    return dict(grouped)


def _top(buckets: list[dict[str, Any]], classification: str, limit: int) -> list[dict[str, Any]]:
    rows = [row for row in buckets if not classification or row["classification"] == classification]
    return rows[:limit]


def _sort_key(row: dict[str, Any]) -> tuple[int, int, str, str, str, str]:
    rank = {
        "promotion_ready": 0,
        "office_boundary_only": 1,
        "schema_policy_blocked": 2,
        "public_path_blocked": 3,
        "known_bad_or_timeout": 4,
    }.get(str(row["classification"]), 9)
    return (rank, -int(row["potential_row_gain"]), str(row["package_id"]), str(row["family"]), str(row["operation_id"]), str(row["qname"]))


def markdown(ranking: dict[str, Any]) -> str:
    counts = ranking["source_counts"]
    lines = [
        "# Semantic Editability High-Yield Candidates",
        "",
        f"- Starting semantic-editable: {counts['starting_semantic_editable_count']}",
        f"- Starting blockers: {counts['starting_remaining_count']}",
        f"- Buckets with 50+ row potential: {counts['yield_50plus_count']}",
        "",
    ]
    lines += _count_lines("Classifications", ranking["classification_counts"])
    lines += _table("50+ Row Buckets", ranking["answers"]["yield_50plus"][:25])
    lines += _table("Office Boundary Only", ranking["answers"]["office_boundary_only"][:25])
    lines += _table("Schema Policy Blocked", ranking["answers"]["schema_policy_blocked"][:25])
    lines += _table("Public Path Blocked", ranking["answers"]["public_path_blocked"][:25])
    lines += _table("Known Bad Or Timeout", ranking["answers"]["known_bad_or_timeout"][:25])
    return "\n".join(lines)


def _table(title: str, rows: list[dict[str, Any]]) -> list[str]:
    body = [
        (
            row["classification"],
            row["potential_row_gain"],
            row["row_count"],
            row["safe_planned_rows"],
            row["boundary_included_planned_rows"],
            row["package_id"],
            row["family"],
            row["qname"],
        )
        for row in rows
    ]
    return table(title, ("Class", "Potential", "Rows", "Safe", "Boundary", "Package", "Family", "QName"), body)


def _count_lines(title: str, counts: dict[str, int]) -> list[str]:
    return [f"## {title}", ""] + [f"- `{key}`: {value}" for key, value in counts.items()] + [""]

if __name__ == "__main__":
    raise SystemExit(main())
