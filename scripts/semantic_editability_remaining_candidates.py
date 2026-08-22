"""Candidate package accounting for semantic-editability burn-down."""
from __future__ import annotations

from collections import Counter
from types import SimpleNamespace
from typing import Any, Callable

import former_preserve_only_promote_hydrated as promote
from former_preserve_only_promoted_index import row_target_key

TargetKey = tuple[str, str, str, str]
RunnerPlanner = Callable[[list[dict[str, Any]]], dict[str, int]]


def candidate_packages(
    hydrated: list[dict[str, Any]],
    office: dict[str, dict[str, Any]],
    replay_timeouts: list[dict[str, Any]],
    size_lookup: Callable[[str], float | None],
    *,
    promoted_sources: set[str] | None = None,
    promoted_targets: set[TargetKey] | None = None,
    failed_sources: set[str] | None = None,
    runner_planner: RunnerPlanner | None = None,
) -> list[dict[str, Any]]:
    promoted_sources = promoted_sources or set()
    promoted_targets = promoted_targets or set()
    failed_sources = failed_sources or set()
    groups: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    replay_packages = {str(row.get("package_id", "")) for row in replay_timeouts}
    slow_replay = {_operation_key(row): row for row in replay_timeouts if row.get("slow_replay_state") == "small_chunk_canary_passed"}
    for row in hydrated:
        if _row_level_skip(row, promoted_sources, promoted_targets, failed_sources):
            continue
        key = (str(row.get("package_id", "")), str(row.get("format", "")), str(row.get("family", "")), str(row.get("operation_id", "")))
        item = groups.setdefault(key, _candidate_base(row, office, size_lookup))
        if row.get("operation_hydration_status") == "hydrated":
            item["_runner_rows"].append(row)
        else:
            item["skipped_policy_rows"] += 1
        item["total_remaining_rows"] += 1
    _apply_runner_planner(groups.values(), runner_planner)
    candidates = [_replay_decision(_candidate_decision(item), replay_packages, slow_replay) for item in groups.values() if item["planned_safe_rows"]]
    return sorted(candidates, key=_candidate_sort)[:100]


def promotion_runner_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    package = str(rows[0].get("package_id", "")) if rows else ""
    opts = SimpleNamespace(package_id=package, requested_value="", max_rows=len(rows), skipped_policy_rows=0)
    try:
        plans = promote._plans(rows, opts)
    except Exception:  # noqa: BLE001
        return {"planned_safe_rows": 0, "runner_plan_error_rows": len(rows)}
    return {
        "planned_safe_rows": len(plans),
        "runner_policy_or_overlap_skipped_rows": len(rows) - len(plans),
        "runner_schema_policy_skipped_rows": int(getattr(opts, "skipped_policy_rows", 0)),
    }


def _apply_runner_planner(items, runner_planner: RunnerPlanner | None) -> None:
    for item in items:
        rows = item.pop("_runner_rows", [])
        if not runner_planner:
            item["planned_safe_rows"] = len(rows)
            continue
        item.update(runner_planner(rows))


def _row_level_skip(row: dict[str, Any], promoted_sources: set[str], promoted_targets: set[TargetKey], failed_sources: set[str]) -> bool:
    if row.get("source_row_id") in promoted_sources or row_target_key(row) in promoted_targets:
        return True
    if row.get("source_row_id") in failed_sources:
        return True
    return str(row.get("part_name", "")).startswith(("customXml/", "docMetadata/"))


def _candidate_base(row: dict[str, Any], office: dict[str, dict[str, Any]], size_lookup: Callable[[str], float | None]) -> dict[str, Any]:
    package = str(row.get("package_id", ""))
    status = office.get(package, {}).get("status", "")
    return {
        "package_id": package,
        "format": row.get("format", ""),
        "family": str(row.get("family", "")),
        "operation_id": str(row.get("operation_id", "")),
        "planned_safe_rows": 0,
        "total_remaining_rows": 0,
        "skipped_policy_rows": 0,
        "runner_policy_or_overlap_skipped_rows": 0,
        "runner_schema_policy_skipped_rows": 0,
        "runner_plan_error_rows": 0,
        "estimated_package_mb": size_lookup(str(row.get("input_file", ""))),
        "has_prior_office_pass": status == "pass",
        "has_prior_office_boundary_failure": bool(status and status != "pass"),
        "_runner_rows": [],
    }


def _candidate_decision(item: dict[str, Any]) -> dict[str, Any]:
    if item["has_prior_office_boundary_failure"]:
        action, reason = "skip_boundary", "prior native Office boundary failure"
    elif item["planned_safe_rows"] >= 10 or item["has_prior_office_pass"]:
        action, reason = "promote_batch", "hydrated safe rows with acceptable prior Office profile"
    else:
        action, reason = "small_tail_batch", "hydrated rows should be batched across packages"
    return item | {"recommended_action": action, "reason": reason}


def _replay_decision(item: dict[str, Any], replay_packages: set[str], slow_replay: dict[tuple[str, str, str], dict[str, Any]]) -> dict[str, Any]:
    if (item["package_id"], item["family"], item["operation_id"]) in slow_replay:
        return item | {"recommended_action": "slow_replay_eligible", "reason": "small 5-row canary passed; continue same package/family/op with 900s timeout"}
    if item["package_id"] not in replay_packages:
        return item
    return item | {"recommended_action": "skip_replay_timeout", "reason": "prior chunk replay timeout; use smaller chunks"}


def _candidate_sort(item: dict[str, Any]) -> tuple[int, int, str]:
    boundary = 1 if item["has_prior_office_boundary_failure"] else 0
    return (boundary, -int(item["planned_safe_rows"]), str(item["package_id"]))


def _operation_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (str(row.get("package_id", "")), str(row.get("family", "")), str(row.get("operation_id", "")))
