"""Chunk replay status summaries for the capability ledger."""
from __future__ import annotations

from collections import Counter
from typing import Any


def chunk_replay_summary(
    promotion: dict[str, Any],
    checkpoint: dict[str, Any],
    plan: dict[str, Any],
    timing: dict[str, Any],
) -> dict[str, Any]:
    records = checkpoint.get("records", [])
    counts = Counter(str(row.get("status", "")) for row in records)
    promoted = [row for row in records if row.get("status") == "promoted"]
    current = _current_plan_records(records, plan)
    current_counts = Counter(str(row.get("status", "")) for row in current)
    next_pkg = next(iter(plan.get("packages", [])), {})
    return {
        "chunk_record_count": len(records),
        "promoted_chunk_count": counts["promoted"],
        "promoted_row_count": sum(_intval(row.get("promoted_row_count"), _intval(row.get("rows"))) for row in promoted),
        "slow_replay_promoted_chunk_count": len(_slow_replay_records(promoted)),
        "slow_replay_promoted_row_count": sum(_intval(row.get("promoted_row_count")) for row in _slow_replay_records(promoted)),
        "status_counts": dict(sorted(counts.items())),
        "current_plan_status_counts": dict(sorted(current_counts.items())),
        "current_plan_failure_count": sum(1 for row in current if row.get("status") != "promoted"),
        "current_plan_pending_chunk_count": _pending_count(records, plan),
        "legacy_or_superseded_failure_counts": _legacy_failures(records, plan),
        "latest_label": promotion.get("latest_label", ""),
        "promotion_row_count": _intval(promotion.get("row_count")),
        "next_plan_scope": plan.get("plan_scope", "global_next_plan"),
        "next_plan_filters": plan.get("plan_filters", {}),
        "next_plan_chunk_count": len(plan.get("chunks", [])),
        "next_plan_row_count": sum(_intval(row.get("planned_row_count")) for row in plan.get("chunks", [])),
        "next_package_id": next_pkg.get("package_id", ""),
        "recommended_next_action": timing.get("recommended_next_action", ""),
        "run_elapsed_seconds": timing.get("run_elapsed_seconds", 0),
        "cumulative_chunk_elapsed_seconds": timing.get("cumulative_chunk_elapsed_seconds", 0),
        "slowest_chunks": timing.get("slowest_chunks", [])[:3],
    }


def _slow_replay_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in records if str(row.get("label", "")).startswith(("canary-", "slow-replay-"))]


def _current_plan_records(records: list[dict[str, Any]], plan: dict[str, Any]) -> list[dict[str, Any]]:
    chunk_ids = {str(row.get("chunk_id", "")) for row in plan.get("chunks", [])}
    return [row for row in records if row.get("chunk_id") in chunk_ids]


def _pending_count(records: list[dict[str, Any]], plan: dict[str, Any]) -> int:
    done = {str(row.get("chunk_id", "")) for row in records}
    return sum(1 for row in plan.get("chunks", []) if row.get("chunk_id") not in done)


def _legacy_failures(records: list[dict[str, Any]], plan: dict[str, Any]) -> dict[str, int]:
    current = {str(row.get("chunk_id", "")) for row in plan.get("chunks", [])}
    counts = Counter(
        str(row.get("status", ""))
        for row in records
        if row.get("status") != "promoted" and row.get("chunk_id") not in current
    )
    return dict(sorted(counts.items()))


def _intval(value: Any, default: int = 0) -> int:
    return value if isinstance(value, int) else default
