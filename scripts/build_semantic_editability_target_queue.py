#!/usr/bin/env python3
"""Build a ranked target queue for semantic-editability burn-down."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "release-evidence/former-preserve-only-semantic-editability"
GAP_LEDGER = EVIDENCE / "gap-ledger.jsonl"
HYDRATION_LEDGER = EVIDENCE / "operation-hydration-ledger.jsonl"
TARGET_OUT = EVIDENCE / "target-queue-summary.json"
BLOCKER_OUT = EVIDENCE / "blocker-summary.json"
DASHBOARD_OUT = EVIDENCE / "target-queue-dashboard.md"


def main() -> int:
    gaps = list(_read_jsonl(GAP_LEDGER))
    hydration = list(_read_jsonl(HYDRATION_LEDGER))
    gap_summary = _gap_summary_from_rows(gaps, _read_json(EVIDENCE / "gap-summary.json"))
    hydration_summary = _hydration_summary_from_rows(hydration, _read_json(EVIDENCE / "operation-hydration-summary.json"))
    queue = _ranked_queue(hydration)
    blockers = _blocker_summary(gaps, gap_summary, hydration_summary)
    target = _target_summary(queue, gap_summary, hydration_summary)
    _write_json(TARGET_OUT, target)
    _write_json(BLOCKER_OUT, blockers)
    DASHBOARD_OUT.write_text(_markdown(target, blockers), encoding="utf-8")
    print(json.dumps({"target_queue": str(TARGET_OUT), "blockers": str(BLOCKER_OUT)}, indent=2))
    return 0


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"missing {path}; run make campaign-ledgers")
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _gap_summary_from_rows(rows: list[dict[str, Any]], stored: dict[str, Any]) -> dict[str, Any]:
    by_blocker = Counter(str(row.get("blocker_type", "")) for row in rows)
    by_family = Counter(str(row.get("family", "")) for row in rows)
    by_qname = Counter(str(row.get("qname", "")) for row in rows)
    blocker_count = len(rows)
    denominator = _int(stored.get("former_preserve_only_denominator"))
    semantic = max(denominator - blocker_count, 0) if denominator else _int(stored.get("semantic_editable_count"))
    return stored | {
        "semantic_editable_count": semantic,
        "semantic_editable_remaining": blocker_count,
        "object_level_gap_row_count": blocker_count,
        "remaining_by_blocker": dict(by_blocker.most_common()),
        "remaining_by_family": dict(by_family.most_common()),
        "remaining_by_qname_top20": dict(by_qname.most_common(20)),
        "object_level_gap_rows_materialized": bool(denominator) and denominator - semantic == blocker_count,
        "aggregate_gap_row_count": 0,
    }


def _hydration_summary_from_rows(rows: list[dict[str, Any]], stored: dict[str, Any]) -> dict[str, Any]:
    statuses = Counter(str(row.get("operation_hydration_status", "")) for row in rows)
    hydrated = sum(1 for row in rows if row.get("operation_hydration_status") == "hydrated")
    return stored | {"hydrated_count": hydrated, "status_counts": dict(sorted(statuses.items()))}


def _int(value: Any) -> int:
    return value if isinstance(value, int) else 0


def _ranked_queue(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    packages: defaultdict[tuple[str, str, str, str, str], set[str]] = defaultdict(set)
    for row in rows:
        key = _queue_key(row)
        item = grouped.setdefault(key, _queue_item(row))
        item["remaining_count"] += 1
        if row.get("operation_hydration_status") == "hydrated":
            item["hydrated_count"] += 1
        packages[key].add(str(row.get("package_id", "")))
    for key, item in grouped.items():
        item["package_count"] = len(packages[key])
        item.update(_queue_decision(item))
    ranked = sorted(grouped.values(), key=_sort_key)
    for index, item in enumerate(ranked, start=1):
        item["rank"] = index
    return ranked


def _queue_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(row.get("family", "")),
        str(row.get("qname", "")),
        str(row.get("blocker_type", "")),
        str(row.get("operation_id", "")),
        str(row.get("operation_hydration_status", "")),
    )


def _queue_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "family": row.get("family", ""),
        "qname": row.get("qname", ""),
        "blocker_reason": row.get("blocker_type", ""),
        "operation_id": row.get("operation_id", ""),
        "hydration_status": row.get("operation_hydration_status", "gap_only"),
        "semantic_value_kind": row.get("semantic_value_kind", ""),
        "remaining_count": 0,
        "hydrated_count": 0,
        "policy_safe_count": None,
        "package_count": 0,
    }


def _queue_decision(item: dict[str, Any]) -> dict[str, Any]:
    blocker = item["blocker_reason"]
    hydrated = item["hydration_status"] == "hydrated"
    if _identity_like(item):
        action = "identity_policy_split"
    elif _binary_like(item):
        action = "reference_model_or_binary_blocker"
    elif blocker == "semantic_value_available_pending_proof" and hydrated:
        action = "promote"
    elif blocker == "semantic_value_available_pending_proof":
        action = "operation_mapping"
    elif blocker == "needs_family_model":
        action = "model"
    elif blocker == "needs_vendor_family_model":
        action = "vendor_model_or_unsupported_reason"
    elif blocker == "relationship_identity_like":
        action = "identity_policy_split"
    elif blocker == "binary_payload_reference":
        action = "reference_model_or_binary_blocker"
    else:
        action = "unsupported_reason"
    return {
        "recommended_action": action,
        "office_risk": _office_risk(item, action),
        "public_surface_risk": _public_surface_risk(item, action),
        "expected_row_gain": _expected_gain(item, action),
    }


def _identity_like(item: dict[str, Any]) -> bool:
    local = _local_name(item["qname"]).lower()
    identity_names = {"rowid", "colid", "sldid", "modid", "uniqueid", "creationid"}
    return local in identity_names or local.endswith("id") and local not in {"grid"}


def _binary_like(item: dict[str, Any]) -> bool:
    local = _local_name(item["qname"]).lower()
    return "blip" in local or "img" in local or "ole" in local


def _local_name(qname: str) -> str:
    return qname.rsplit("}", 1)[-1] if "}" in qname else qname.rsplit(":", 1)[-1]


def _office_risk(item: dict[str, Any], action: str) -> str:
    family = item["family"]
    if "binary" in item["blocker_reason"] or action.endswith("blocker"):
        return "high"
    if action == "identity_policy_split":
        return "high"
    if family in {"chart_drawing", "vml_drawing", "math_object", "alternate_content"}:
        return "medium"
    if "vendor" in family or "vendor" in action:
        return "high"
    return "low"


def _public_surface_risk(item: dict[str, Any], action: str) -> str:
    if action == "promote" and item["operation_id"]:
        return "low"
    if action in {"model", "operation_mapping", "identity_policy_split"}:
        return "medium"
    return "high"


def _expected_gain(item: dict[str, Any], action: str) -> int:
    if action == "promote" and _office_risk(item, action) != "high":
        return int(item["hydrated_count"])
    if action in {"model", "operation_mapping"}:
        return int(item["remaining_count"])
    return 0


def _sort_key(item: dict[str, Any]) -> tuple[int, int, str, str]:
    action_order = {"promote": 0, "model": 1, "operation_mapping": 2}
    order = action_order.get(item["recommended_action"], 3)
    return (order, -int(item["expected_row_gain"]), item["family"], item["qname"])


def _target_summary(queue: list[dict[str, Any]], gaps: dict[str, Any], hydration: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "semantic-editability-target-queue-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "starting_semantic_editable_count": gaps.get("semantic_editable_count", 0),
        "starting_blocker_count": gaps.get("object_level_gap_row_count", 0),
        "hydrated_count": hydration.get("hydrated_count", 0),
        "ranked_target_count": len(queue),
        "ranked_targets": queue[:100],
    }


def _blocker_summary(rows: list[dict[str, Any]], gaps: dict[str, Any], hydration: dict[str, Any]) -> dict[str, Any]:
    by_family = Counter(str(row.get("family", "")) for row in rows)
    by_reason = Counter(str(row.get("blocker_type", "")) for row in rows)
    by_qname = Counter(str(row.get("qname", "")) for row in rows)
    return {
        "schema_version": "semantic-editability-blocker-summary-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_blocker_count": sum(by_reason.values()),
        "by_family": dict(by_family.most_common()),
        "by_reason": dict(by_reason.most_common()),
        "by_qname_top50": dict(by_qname.most_common(50)),
        "hydration_status_counts": hydration.get("status_counts", {}),
        "source_gap_summary_count": gaps.get("object_level_gap_row_count", 0),
    }


def _markdown(target: dict[str, Any], blockers: dict[str, Any]) -> str:
    rows = target["ranked_targets"][:25]
    lines = ["# Semantic Editability Target Queue", ""]
    lines += [f"- Starting semantic-editable: {target['starting_semantic_editable_count']}"]
    lines += [f"- Starting blockers: {target['starting_blocker_count']}"]
    lines += [f"- Hydrated rows: {target['hydrated_count']}", ""]
    lines += ["## Top Targets", ""]
    lines += ["| Rank | Family | Count | Action | Risk | QName |"]
    lines += ["| ---: | --- | ---: | --- | --- | --- |"]
    for row in rows:
        lines.append(_target_line(row))
    lines += ["", "## Blockers By Reason", ""]
    for reason, count in blockers["by_reason"].items():
        lines.append(f"- `{reason}`: {count}")
    return "\n".join(lines) + "\n"


def _target_line(row: dict[str, Any]) -> str:
    qname = str(row["qname"]).replace("|", "\\|")
    return (
        f"| {row['rank']} | `{row['family']}` | {row['remaining_count']} | "
        f"`{row['recommended_action']}` | {row['office_risk']} | `{qname}` |"
    )


if __name__ == "__main__":
    raise SystemExit(main())
