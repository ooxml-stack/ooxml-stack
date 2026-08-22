#!/usr/bin/env python3
"""Build targeted replay plans after semantic-editability unlock analysis."""

from __future__ import annotations

from typing import Any

from semantic_editability_unlock_common import EVIDENCE, read_json, table, write_json, write_md

OUT_JSON = EVIDENCE / "targeted-unlock-replay-plan.json"
OUT_MD = EVIDENCE / "targeted-unlock-replay-plan.md"


def main() -> int:
    remaining = read_json(EVIDENCE / "remaining-bucket-summary.json")
    policy = read_json(EVIDENCE / "schema-policy-unlock-candidates.json")
    family = read_json(EVIDENCE / "family-model-unlock-candidates.json")
    audit = read_json(EVIDENCE / "target-queue-exclusion-audit.json")
    summary = build_plan(remaining, policy, family, audit)
    write_json(OUT_JSON, summary)
    write_md(OUT_MD, markdown(summary))
    print({"plan": str(OUT_JSON), "dashboard": str(OUT_MD)})
    return 0


def build_plan(
    remaining: dict[str, Any],
    policy: dict[str, Any],
    family: dict[str, Any],
    audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "targeted-unlock-replay-plan-v1",
        "source_counts": _source_counts(remaining),
        "plans": [
            _quick_proof_plan(remaining, audit or {}),
            _schema_policy_plan(policy),
            _family_model_plan(family),
        ],
    }


def _source_counts(remaining: dict[str, Any]) -> dict[str, Any]:
    return {
        "starting_semantic_editable_count": remaining.get("starting_semantic_editable_count", 0),
        "starting_remaining_count": remaining.get("starting_remaining_count", 0),
        "by_blocker": remaining.get("by_blocker", {}),
    }


def _quick_proof_plan(remaining: dict[str, Any], audit: dict[str, Any]) -> dict[str, Any]:
    candidates = [
        row
        for row in remaining.get("candidate_packages", [])
        if row.get("recommended_action") in {"promote_batch", "small_tail_batch"}
        and not row.get("has_prior_office_boundary_failure")
        and row.get("planned_safe_rows", 0) <= 25
    ][:10]
    if len(candidates) < 10:
        candidates += _target_level_quickproof_candidates(audit, 10 - len(candidates))
    return {
        "plan_id": "quick_proof_batch",
        "purpose": "prove low-risk already-hydrated rows without schema or family-model changes",
        "chunk_size": 25,
        "expected_runtime": "under 2 hours if native Office remains responsive",
        "requires_code_change": False,
        "candidate_count": len(candidates),
        "expected_row_count": sum(int(row.get("planned_safe_rows", 0)) for row in candidates),
        "selection_rule": "hydrated, not boundary, not replay-timeout, max 25 rows/package or target-level audit row",
        "candidates": candidates,
    }


def _target_level_quickproof_candidates(audit: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    rows = []
    seen = set()
    for target in audit.get("targets", []):
        for example in target.get("package_examples", []):
            if example.get("reason") != "candidate_outside_remaining_top100":
                continue
            count = int(example.get("planned_safe_rows", 0))
            key = (example.get("package_id"), example.get("family"), example.get("operation_id"), target.get("qname"))
            if not 0 < count <= 25 or key in seen:
                continue
            seen.add(key)
            rows.append(_target_level_row(target, example, count))
            if len(rows) >= limit:
                return rows
    return rows


def _target_level_row(target: dict[str, Any], example: dict[str, Any], count: int) -> dict[str, Any]:
    return {
        "package_id": example.get("package_id", ""),
        "format": example.get("format", ""),
        "family": example.get("family", ""),
        "operation_id": example.get("operation_id", ""),
        "qname": target.get("qname", ""),
        "target_rank": target.get("rank", 0),
        "planned_safe_rows": count,
        "total_remaining_rows": example.get("row_count", count),
        "recommended_action": "target_level_quickproof",
        "reason": "outside package top100; selected by target queue audit",
        "selection_source": "target_queue_exclusion_audit",
    }


def _schema_policy_plan(policy: dict[str, Any]) -> dict[str, Any]:
    rows = [
        row
        for row in policy.get("candidates", [])
        if row.get("recommended_action") in {"unlock_now", "needs_spec_check"}
    ][:5]
    return {
        "plan_id": "schema_policy_unlock_batch",
        "purpose": "add a small allowlist or spec-backed classifier before targeted replay",
        "chunk_size": 10,
        "requires_code_change": True,
        "candidate_count": len(rows),
        "expected_row_count": sum(int(row.get("expected_candidate_row_count", 0)) for row in rows),
        "required_tests": ["policy accepts only allowlisted values", "policy rejects identity/reference/binary fields", "runner hard audit still passes"],
        "candidates": rows,
    }


def _family_model_plan(family: dict[str, Any]) -> dict[str, Any]:
    candidates = [row for row in family.get("candidates", []) if row.get("current_remaining_count", 0)]
    chosen = _choose_family(candidates)
    return {
        "plan_id": "family_model_implementation_batch",
        "purpose": "implement one family and one operation with explicit semantic oracle",
        "chunk_size": 5,
        "requires_code_change": True,
        "candidate_count": 1 if chosen else 0,
        "expected_row_count": chosen.get("first_small_batch_target", {}).get("row_count", 0) if chosen else 0,
        "canary_rule": "start with 5-row canary and expand only after API/CLI/MCP/Office/hard audit pass",
        "candidates": [chosen] if chosen else [],
    }


def _choose_family(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    preferred = {"math_object", "vml_drawing", "custom_xml_payload", "chart_drawing"}
    eligible = [row for row in candidates if row.get("first_small_batch_target", {}).get("semantic_value_source") != "no_descendant_value"]
    for row in eligible:
        target = row.get("first_small_batch_target", {})
        if row.get("family_id") in preferred and target.get("row_count", 0):
            return row
    return next((row for row in eligible if row.get("first_small_batch_target", {}).get("row_count", 0)), {})


def markdown(summary: dict[str, Any]) -> str:
    lines = ["# Targeted Unlock Replay Plan", ""]
    counts = summary.get("source_counts", {})
    lines += [f"- Starting semantic-editable: {counts.get('starting_semantic_editable_count', 0)}"]
    lines += [f"- Starting remaining: {counts.get('starting_remaining_count', 0)}", ""]
    for plan in summary["plans"]:
        lines += _plan_section(plan)
    return "\n".join(lines)


def _plan_section(plan: dict[str, Any]) -> list[str]:
    lines = [f"## {plan['plan_id']}", ""]
    lines += [f"- Purpose: {plan['purpose']}"]
    lines += [f"- Chunk size: {plan['chunk_size']}"]
    lines += [f"- Requires code change: {plan['requires_code_change']}"]
    lines += [f"- Candidate count: {plan['candidate_count']}"]
    lines += [f"- Expected row count: {plan['expected_row_count']}", ""]
    lines += _candidate_table(plan)
    return lines


def _candidate_table(plan: dict[str, Any]) -> list[str]:
    rows = []
    for row in plan.get("candidates", [])[:15]:
        target = row.get("first_small_batch_target", {})
        count = row.get("planned_safe_rows", row.get("expected_candidate_row_count", target.get("row_count", "")))
        operation = row.get("operation_id") or target.get("operation_id") or row.get("attribute_name", "")
        owner = row.get("package_id") or row.get("family_id") or row.get("qname") or row.get("attribute_name", "")
        rows.append((owner, row.get("family", row.get("family_id", "")), operation, count))
    return table("Candidates", ("Package/Family", "Family", "Operation", "Rows"), rows)


if __name__ == "__main__":
    raise SystemExit(main())
