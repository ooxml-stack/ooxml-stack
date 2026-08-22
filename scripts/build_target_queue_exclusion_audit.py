#!/usr/bin/env python3
"""Explain why ranked target-queue rows are absent from quick-proof replay."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

from former_preserve_only_promoted_index import promoted_index, row_target_key
from semantic_editability_failed_rows import failed_source_ids
from semantic_editability_remaining_candidates import promotion_runner_counts

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "release-evidence/former-preserve-only-semantic-editability"
TARGET_QUEUE = EVIDENCE / "target-queue-summary.json"
REMAINING = EVIDENCE / "remaining-bucket-summary.json"
HYDRATED = EVIDENCE / "operation-hydration-ledger.jsonl"
ROWS = EVIDENCE / "promotion-rows.jsonl"
CHECKPOINT = EVIDENCE / "chunk-promotion-checkpoint.json"
STAGED = EVIDENCE / "staged-rows"
OUT_JSON = EVIDENCE / "target-queue-exclusion-audit.json"
OUT_MD = EVIDENCE / "target-queue-exclusion-audit.md"

RunnerPlanner = Callable[[list[dict[str, Any]]], dict[str, int]]


def main() -> int:
    promoted_sources, promoted_targets = promoted_index(ROWS)
    failed_sources = failed_source_ids(CHECKPOINT, STAGED)
    audit = build_audit(
        _read_json(TARGET_QUEUE),
        _read_json(REMAINING),
        _read_jsonl(HYDRATED),
        promoted_sources=promoted_sources,
        promoted_targets=promoted_targets,
        failed_sources=failed_sources,
    )
    _write_json(OUT_JSON, audit)
    OUT_MD.write_text(markdown(audit), encoding="utf-8")
    print({"audit": str(OUT_JSON), "dashboard": str(OUT_MD)})
    return 0


def build_audit(
    target_queue: dict[str, Any],
    remaining: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    limit: int = 100,
    runner_planner: RunnerPlanner = promotion_runner_counts,
    promoted_sources: set[str] | None = None,
    promoted_targets: set[tuple[str, str, str, str]] | None = None,
    failed_sources: set[str] | None = None,
) -> dict[str, Any]:
    context = _context(remaining) | {
        "promoted_sources": promoted_sources or set(),
        "promoted_targets": promoted_targets or set(),
        "failed_sources": failed_sources or set(),
    }
    candidate_actions = Counter(str(row.get("recommended_action", "")) for row in remaining.get("candidate_packages", []))
    row_index = _row_index(rows)
    audited = [_target_audit(target, row_index, context, runner_planner) for target in target_queue.get("ranked_targets", [])[:limit]]
    counts = Counter()
    for row in audited:
        counts.update(row["exclusion_counts"])
    return {
        "schema_version": "target-queue-exclusion-audit-v1",
        "source_counts": {
            "starting_semantic_editable_count": target_queue.get("starting_semantic_editable_count", 0),
            "starting_blocker_count": target_queue.get("starting_blocker_count", 0),
            "ranked_target_count": target_queue.get("ranked_target_count", 0),
            "remaining_candidate_package_count": len(remaining.get("candidate_packages", [])),
        },
        "audited_target_count": len(audited),
        "remaining_candidate_action_counts": dict(candidate_actions.most_common()),
        "exclusion_counts": dict(counts.most_common()),
        "targets": audited,
    }


def _context(remaining: dict[str, Any]) -> dict[str, Any]:
    replay_rows = remaining.get("known_replay_timeout_packages", [])
    slow = {
        _operation_key(row)
        for row in replay_rows
        if row.get("slow_replay_state") == "small_chunk_canary_passed" and row.get("operation_id")
    }
    candidates = {
        _candidate_key(row): row
        for row in remaining.get("candidate_packages", [])
    }
    return {
        "boundary": {str(row.get("package_id", "")) for row in remaining.get("known_boundary_packages", [])},
        "replay": {str(row.get("package_id", "")) for row in replay_rows},
        "slow": slow,
        "candidates": candidates,
    }


def _row_index(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str, str, str], list[dict[str, Any]]]:
    index: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        index[_target_key(row)].append(row)
    return dict(index)


def _target_audit(
    target: dict[str, Any],
    row_index: dict[tuple[str, str, str, str, str], list[dict[str, Any]]],
    context: dict[str, Any],
    runner_planner: RunnerPlanner,
) -> dict[str, Any]:
    rows = row_index.get(_target_key_from_target(target), [])
    groups = _groups(rows)
    details = [_group_audit(target, group_rows, context, runner_planner) for group_rows in groups.values()]
    counts = Counter()
    planned = 0
    for detail in details:
        counts[detail["reason"]] += detail["row_count"]
        planned += detail.get("planned_safe_rows", 0)
    return {
        "rank": target.get("rank", 0),
        "family": target.get("family", ""),
        "qname": target.get("qname", ""),
        "operation_id": target.get("operation_id", ""),
        "target_action": target.get("recommended_action", ""),
        "remaining_count": target.get("remaining_count", 0),
        "hydrated_count": target.get("hydrated_count", 0),
        "expected_row_gain": target.get("expected_row_gain", 0),
        "matching_row_count": len(rows),
        "planned_safe_rows_seen": planned,
        "dominant_exclusion": counts.most_common(1)[0][0] if counts else "no_matching_rows",
        "exclusion_counts": dict(counts.most_common()),
        "package_examples": sorted(details, key=lambda row: (-row["row_count"], row["package_id"]))[:5],
    }


def _group_audit(
    target: dict[str, Any],
    rows: list[dict[str, Any]],
    context: dict[str, Any],
    runner_planner: RunnerPlanner,
) -> dict[str, Any]:
    row = rows[0]
    package = str(row.get("package_id", ""))
    live = _live_rows(rows, context)
    if not live:
        reason = "known_row_level_failure" if any(row.get("source_row_id") in context["failed_sources"] for row in rows) else "already_promoted"
        return _detail_base(row, len(rows)) | {"reason": reason}
    row = live[0]
    base = _detail_base(row, len(live))
    if target.get("recommended_action") != "promote":
        return base | {"reason": "target_action_not_replayable"}
    if target.get("hydration_status") != "hydrated":
        return base | {"reason": "not_hydrated"}
    usable = [item for item in live if not str(item.get("part_name", "")).startswith(("customXml/", "docMetadata/"))]
    if not usable:
        return base | {"reason": "public_path_unsupported_part"}
    if package in context["boundary"]:
        return base | {"reason": "known_office_boundary"}
    if package in context["replay"] and _operation_key(row) not in context["slow"]:
        return base | {"reason": "known_replay_timeout"}
    plan = runner_planner(usable)
    planned = int(plan.get("planned_safe_rows", 0))
    if planned <= 0:
        return base | plan | {"reason": _runner_zero_reason(plan)}
    if planned > 25:
        return base | plan | {"reason": "quickproof_batch_too_large"}
    if _candidate_key(row) not in context["candidates"]:
        return base | plan | {"reason": "candidate_outside_remaining_top100"}
    return base | plan | {"reason": "eligible_quick_proof"}


def _runner_zero_reason(plan: dict[str, int]) -> str:
    if plan.get("runner_plan_error_rows", 0):
        return "runner_plan_error"
    if plan.get("runner_schema_policy_skipped_rows", 0):
        return "runner_schema_policy"
    if plan.get("runner_policy_or_overlap_skipped_rows", 0):
        return "runner_policy_or_overlap"
    return "runner_zero_rows"


def _live_rows(rows: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row.get("source_row_id") not in context["promoted_sources"]
        and row_target_key(row) not in context["promoted_targets"]
        and row.get("source_row_id") not in context["failed_sources"]
    ]


def _groups(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_candidate_key(row)].append(row)
    return dict(grouped)


def _detail_base(row: dict[str, Any], count: int) -> dict[str, Any]:
    return {
        "package_id": row.get("package_id", ""),
        "format": row.get("format", ""),
        "family": row.get("family", ""),
        "operation_id": row.get("operation_id", ""),
        "row_count": count,
    }


def _target_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(row.get("family", "")),
        str(row.get("qname", "")),
        str(row.get("blocker_type", "")),
        str(row.get("operation_id", "")),
        str(row.get("operation_hydration_status", "")),
    )


def _target_key_from_target(target: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(target.get("family", "")),
        str(target.get("qname", "")),
        str(target.get("blocker_reason", "")),
        str(target.get("operation_id", "")),
        str(target.get("hydration_status", "")),
    )


def _candidate_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (str(row.get("package_id", "")), str(row.get("format", "")), str(row.get("family", "")), str(row.get("operation_id", "")))


def _operation_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (str(row.get("package_id", "")), str(row.get("family", "")), str(row.get("operation_id", "")))


def markdown(audit: dict[str, Any]) -> str:
    lines = ["# Target Queue Exclusion Audit", ""]
    counts = audit["source_counts"]
    lines += [f"- Starting semantic-editable: {counts['starting_semantic_editable_count']}"]
    lines += [f"- Starting blockers: {counts['starting_blocker_count']}"]
    lines += [f"- Audited targets: {audit['audited_target_count']}", ""]
    lines += _count_lines("Remaining Candidate Actions", audit["remaining_candidate_action_counts"])
    lines += _count_lines("Exclusion Counts", audit["exclusion_counts"])
    rows = audit["targets"][:25]
    lines += ["## Top Target Exclusions", ""]
    lines += ["| Rank | Family | Rows | Planned | Dominant exclusion | QName |"]
    lines += ["| ---: | --- | ---: | ---: | --- | --- |"]
    for row in rows:
        qname = str(row["qname"]).replace("|", "\\|")
        lines.append(f"| {row['rank']} | `{row['family']}` | {row['matching_row_count']} | {row['planned_safe_rows_seen']} | `{row['dominant_exclusion']}` | `{qname}` |")
    return "\n".join(lines) + "\n"


def _count_lines(title: str, counts: dict[str, int]) -> list[str]:
    lines = [f"## {title}", ""]
    return lines + [f"- `{key}`: {value}" for key, value in counts.items()] + [""]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
