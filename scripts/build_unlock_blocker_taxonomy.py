#!/usr/bin/env python3
"""Build a blocker taxonomy for remaining semantic-editability rows."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from semantic_editability_unlock_common import (
    EVIDENCE,
    blocker_why,
    boundary_package_ids,
    counts,
    joined_remaining_rows,
    nested_counts,
    read_json,
    replay_timeout_package_ids,
    table,
    why_remaining,
    write_json,
    write_md,
)

OUT_JSON = EVIDENCE / "unlock-blocker-taxonomy.json"
OUT_MD = EVIDENCE / "unlock-blocker-taxonomy.md"


def main() -> int:
    remaining = read_json(EVIDENCE / "remaining-bucket-summary.json")
    policy = read_json(EVIDENCE / "schema-policy-audit.json")
    plan = read_json(EVIDENCE / "chunk-plan-summary.json")
    rows = joined_remaining_rows()
    summary = build_taxonomy(rows, remaining, policy, plan)
    write_json(OUT_JSON, summary)
    write_md(OUT_MD, markdown(summary))
    print({"taxonomy": str(OUT_JSON), "dashboard": str(OUT_MD)})
    return 0


def build_taxonomy(rows: list[dict[str, Any]], remaining: dict, policy: dict, plan: dict) -> dict:
    office = boundary_package_ids(remaining)
    timeout = replay_timeout_package_ids(remaining)
    return {
        "schema_version": "semantic-editability-unlock-blocker-taxonomy-v1",
        "source_remaining_count": remaining.get("starting_remaining_count", len(rows)),
        "row_count": len(rows),
        "by_blocker_reason": _with_why(counts(rows, "blocker_type"), rows, office, timeout, "blocker_type"),
        "by_family": _with_why(counts(rows, "family"), rows, office, timeout, "family"),
        "by_family_blocker_reason": nested_counts(rows, "family", "blocker_type"),
        "by_operation_id": _with_why(counts(rows, "operation_id"), rows, office, timeout, "operation_id"),
        "by_qname": _with_why(counts(rows, "qname"), rows, office, timeout, "qname"),
        "by_attribute_name": _with_why(counts(rows, "attribute_name"), rows, office, timeout, "attribute_name"),
        "by_package_id": _with_why(counts(rows, "package_id"), rows, office, timeout, "package_id"),
        "by_format": _with_why(counts(rows, "format"), rows, office, timeout, "format"),
        "top100_family_qname_attribute_operation": _top_combos(rows, office, timeout),
        "metrics": _metrics(rows, remaining, policy, plan, office, timeout),
    }


def _with_why(counts_by_key: dict[str, int], rows: list[dict], office: set[str], timeout: set[str], field: str) -> list[dict]:
    buckets = _rows_by_field(rows, field)
    return [
        {"key": key, "count": count, "why_remaining": _group_why(key, buckets.get(key, []), office, timeout, field)}
        for key, count in counts_by_key.items()
    ]


def _rows_by_field(rows: list[dict], field: str) -> dict[str, list[dict]]:
    result: defaultdict[str, list[dict]] = defaultdict(list)
    for row in rows:
        result[str(row.get(field) or "<none>")].append(row)
    return result


def _group_why(key: str, rows: list[dict], office: set[str], timeout: set[str], field: str) -> str:
    if field == "blocker_type" and key != "semantic_value_available_pending_proof":
        return blocker_why(key)
    pieces = _group_reason_counts(rows, office, timeout)
    if not pieces:
        return why_remaining(rows[0], office, timeout) if rows else "no rows in bucket"
    return "; ".join(f"{count} {reason}" for reason, count in pieces)


def _group_reason_counts(rows: list[dict], office: set[str], timeout: set[str]) -> list[tuple[str, int]]:
    counts_by_reason: Counter[str] = Counter()
    for row in rows:
        package = str(row.get("package_id", ""))
        if package in office:
            counts_by_reason["native Office boundary package"] += 1
        elif package in timeout:
            counts_by_reason["replay-timeout package"] += 1
        elif row.get("operation_hydration_status") == "hydrated":
            counts_by_reason["hydrated row missing full proof"] += 1
        elif row.get("blocker_type") == "semantic_value_available_pending_proof":
            counts_by_reason["semantic value exists but no hydrated operation row yet"] += 1
        else:
            counts_by_reason[blocker_why(str(row.get("blocker_type", "")))] += 1
    return counts_by_reason.most_common(3)


def _top_combos(rows: list[dict], office: set[str], timeout: set[str]) -> list[dict]:
    grouped: defaultdict[tuple[str, str, str, str, str], list[dict]] = defaultdict(list)
    for row in rows:
        key = (
            str(row.get("family", "")),
            str(row.get("qname", "")),
            str(row.get("attribute_name", "")),
            str(row.get("operation_id", "")),
            str(row.get("blocker_type", "")),
        )
        grouped[key].append(row)
    items = sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0]))[:100]
    return [_combo_row(key, bucket, office, timeout) for key, bucket in items]


def _combo_row(key: tuple[str, str, str, str, str], rows: list[dict], office: set[str], timeout: set[str]) -> dict:
    family, qname, attr, operation, blocker = key
    return {
        "family": family,
        "qname": qname,
        "attribute_name": attr,
        "operation_id": operation,
        "blocker_type": blocker,
        "count": len(rows),
        "why_remaining": why_remaining(rows[0], office, timeout),
        "sample_row_ids": [row.get("row_id", "") for row in rows[:3]],
    }


def _metrics(rows: list[dict], remaining: dict, policy: dict, plan: dict, office: set[str], timeout: set[str]) -> dict:
    blockers = Counter(str(row.get("blocker_type", "")) for row in rows)
    return {
        "hydrated_not_promoted_count": sum(row.get("operation_hydration_status") == "hydrated" for row in rows),
        "schema_policy_rejected_count": policy.get("rejected_count", 0),
        "planner_schema_policy_skipped_count": plan.get("skipped_counts", {}).get("runner_schema_policy", 0),
        "office_boundary_package_blocked_count": sum(row.get("package_id") in office for row in rows),
        "replay_timeout_package_blocked_count": sum(row.get("package_id") in timeout for row in rows),
        "requires_new_family_model_count": _family_model_opportunity_count(remaining),
        "must_remain_unsupported_for_now_count": _must_remain_count(remaining, blockers),
    }

def _family_model_opportunity_count(remaining: dict) -> int:
    return sum(int(row.get("count", 0)) for row in remaining.get("family_model_opportunities", []))


def _must_remain_count(remaining: dict, blockers: Counter[str]) -> int:
    rows = remaining.get("must_remain_unsupported", [])
    if rows:
        return sum(int(row.get("count", 0)) for row in rows)
    return blockers["relationship_identity_like"] + blockers["binary_payload_reference"]


def markdown(summary: dict) -> str:
    lines = ["# Semantic Editability Unlock Blocker Taxonomy", ""]
    lines += [f"- Row count: {summary['row_count']}"]
    lines += [f"- Source remaining count: {summary['source_remaining_count']}", ""]
    lines += _metrics_md(summary["metrics"])
    lines += _summary_table("By Blocker Reason", summary["by_blocker_reason"][:20])
    lines += _summary_table("By Family", summary["by_family"][:20])
    lines += _summary_table("By Operation ID", summary["by_operation_id"][:20])
    lines += _summary_table("By QName", summary["by_qname"][:25])
    lines += _summary_table("By Attribute Name", summary["by_attribute_name"][:25])
    lines += _summary_table("By Package ID", summary["by_package_id"][:25])
    lines += _summary_table("By Format", summary["by_format"])
    lines += _combo_table(summary["top100_family_qname_attribute_operation"][:30])
    return "\n".join(lines)


def _metrics_md(metrics: dict[str, Any]) -> list[str]:
    return ["## Required Metrics", ""] + [f"- `{key}`: {value}" for key, value in metrics.items()] + [""]


def _summary_table(title: str, rows: list[dict]) -> list[str]:
    data = [(row["key"], row["count"], row["why_remaining"]) for row in rows]
    return table(title, ("Key", "Count", "Why remaining"), data)


def _combo_table(rows: list[dict]) -> list[str]:
    data = [
        (row["family"], row["qname"], row["attribute_name"], row["operation_id"], row["blocker_type"], row["count"], row["why_remaining"])
        for row in rows
    ]
    return table("Top Family / QName / Attribute / Operation Combos", ("Family", "QName", "Attribute", "Operation", "Blocker", "Count", "Why"), data)


if __name__ == "__main__":
    raise SystemExit(main())
