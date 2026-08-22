#!/usr/bin/env python3
"""Build the machine OOXML element capability ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_former_preserve_only_semantic_campaign import build_campaign
from campaign_office_boundary_summary import summarize_boundaries
from chunk_replay_status import chunk_replay_summary
from former_preserve_only_promoted_index import alias_operation_count
from semantic_blocker_reasons import is_explicit_unsupported


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "artifacts/ooxml-element-capability-ledger.json"
SOURCE_PATHS = {
    "semantic_inventory": "release-evidence/p43/ooxml-semantic-status-summary.json",
    "surface_editability": "release-evidence/p80",
    "surface_source_summary": "release-evidence/p77/public-api-object-edit-summary.json",
    "surface_source_shards": "release-evidence/p77/public-api-object-edit-rows-shards",
    "semantic_summary": "release-evidence/p90/sh-semantic-editability-summary.json",
    "anti_false_pass_audit": "release-evidence/p90/anti-false-pass-audit.json",
    "semantic_feasibility": "release-evidence/p90/p80-semantic-promotion-feasibility.json",
    "campaign_promotion_rows": "release-evidence/former-preserve-only-semantic-editability/promotion-rows.jsonl",
    "campaign_alias_operation_rows": "release-evidence/former-preserve-only-semantic-editability/alias-operation-rows.jsonl",
    "campaign_promotion_summary": "release-evidence/former-preserve-only-semantic-editability/promotion-summary.json",
    "campaign_office_results": "release-evidence/former-preserve-only-semantic-editability/office-results",
    "campaign_public_paths": "release-evidence/former-preserve-only-semantic-editability/public-paths",
    "operation_hydration": "release-evidence/former-preserve-only-semantic-editability/operation-hydration-summary.json",
    "schema_policy": "release-evidence/former-preserve-only-semantic-editability/schema-policy-audit.json",
    "remaining_bucket_summary": "release-evidence/former-preserve-only-semantic-editability/remaining-bucket-summary.json",
    "chunk_plan": "release-evidence/former-preserve-only-semantic-editability/chunk-plan-summary.json",
    "chunk_checkpoint": "release-evidence/former-preserve-only-semantic-editability/chunk-promotion-checkpoint.json",
    "chunk_timing": "release-evidence/former-preserve-only-semantic-editability/replay-timing-summary.json",
    "chunk_boundary": "release-evidence/former-preserve-only-semantic-editability/chunk-boundary-summary.json",
    "close_error_diagnostic": "release-evidence/former-preserve-only-semantic-editability/close-error-diagnostic-summary.json",
    "close_error_rerun": "release-evidence/former-preserve-only-semantic-editability/close-error-rerun-summary.json",
}


def read_json(source_id: str) -> dict[str, Any]:
    path = ROOT / SOURCE_PATHS[source_id]
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() and path.is_file() else {}


def section(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    return value if isinstance(value, dict) else {}


def intval(value: Any, default: int = 0) -> int:
    return value if isinstance(value, int) else default


def build_ledger() -> dict[str, Any]:
    _, gaps, campaign = build_campaign()
    p43 = section(read_json("semantic_inventory"), "summary")
    semantic_summary = read_json("semantic_summary")
    audit = read_json("anti_false_pass_audit")
    metrics = section(audit, "metrics")
    feasibility = read_json("semantic_feasibility")
    hydration = read_json("operation_hydration")
    schema_policy = read_json("schema_policy")
    remaining = read_json("remaining_bucket_summary")
    levels = build_levels(p43, semantic_summary, metrics, campaign)
    blockers = build_blockers(campaign, schema_policy)
    gates = code_gate_summary(audit)
    boundaries = summarize_boundaries(ROOT)
    return {
        "schema_version": "ooxml-element-capability-ledger-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "unit_definitions": unit_definitions(),
        "claim_summary": claim_summary(levels, blockers, gates),
        "full_claim_proven": full_claim_proven(levels, blockers, gates),
        "levels": levels,
        "tier_counts": {key: value["count"] for key, value in levels.items()},
        "blockers": blockers,
        "families": build_families(feasibility, campaign, hydration, gaps),
        "evidence_refs": list(SOURCE_PATHS.values()),
        "source_integrity": source_integrity(),
        "code_gate_summary": gates,
        "office_boundary_summary": boundaries,
        "close_error_diagnostic_summary": read_json("close_error_diagnostic"),
        "close_error_rerun_summary": read_json("close_error_rerun"),
        "remaining_bucket_summary": remaining,
        "chunk_replay_summary": chunk_replay_summary(read_json("campaign_promotion_summary"), read_json("chunk_checkpoint"), read_json("chunk_plan"), read_json("chunk_timing")),
        "raw_sources": SOURCE_PATHS,
    }


def build_levels(p43: dict[str, Any], summary: dict[str, Any], metrics: dict[str, Any], campaign: dict[str, Any]) -> dict[str, Any]:
    baseline = intval(campaign.get("former_preserve_only_denominator"), intval(metrics.get("p80_former_preserve_only_baseline_count")))
    semantic = intval(campaign.get("semantic_editable_count"), intval(metrics.get("p90_p80_semantic_promoted_count")))
    remaining = max(baseline - semantic, 0)
    return {
        "xml_element_instances": level(intval(p43.get("element_instance_count")), "xml element instances", "raw_xml", "Counted inventory only.", ["semantic_inventory"], "Raw XML tags are not object rows.", "原始 XML 标签不是对象行。"),
        "object_candidates": level(intval(p43.get("object_candidate_count")), "object rows", "semantic_inventory", "Classified inventory only.", ["semantic_inventory"], "Object rows selected from XML/package structures.", "从 XML/包结构归一化出的对象候选。"),
        "readable_inspectable": level(intval(p43.get("inspectable_count")), "object rows", "semantic_inventory", "Inspectable object inventory.", ["semantic_inventory"], "Readable does not imply writable.", "可读不等于可写。"),
        "semantic_handle_object_denominator": level(intval(summary.get("sh_object_count")), "object rows", "semantic_handle_inventory", "Semantic handle denominator only.", ["semantic_summary"], "This is not the former preserve-only campaign denominator.", "这是 SH 分母，不是原 preserve-only campaign 分母。"),
        "opaque_binary_package_dependencies": level(0, "package dependency rows", "opc_dependency_inventory", "Tracked separately when generated.", ["semantic_inventory"], "Binary payload semantics are not claimed.", "二进制 payload 语义没有被声明支持。"),
        "surface_editable": level(baseline, "object rows", "former_preserve_only_campaign", "Safe object-bound write under measured denominator.", ["surface_editability"], "Surface-editable is not semantic-editable.", "surface 可编辑不等于语义可编辑。"),
        "semantic_editable": level(semantic, "object rows", "former_preserve_only_campaign", "Rows with exact semantic proof.", ["semantic_summary", "anti_false_pass_audit", "campaign_promotion_rows", "campaign_promotion_summary", "campaign_office_results", "campaign_public_paths"], "Semantic rows need exact before/requested/after proof.", "语义行需要 before/requested/after 精确证明。"),
        "full_write": level(0, "object rows", "family_operation_claim", "No global full-write claim.", [], "Full-write must be proven per family and operation.", "full-write 必须按 family 和 operation 证明。"),
        "unsupported_or_not_proven": level(remaining, "object rows", "former_preserve_only_campaign", "Not proven at semantic tier.", ["surface_source_summary", "surface_source_shards", "anti_false_pass_audit", "semantic_feasibility", "campaign_promotion_rows"], "Rows blocked by missing value, resolution, or proof gaps.", "这些对象仍被缺语义值、定位或证明缺口阻断。"),
        "office_output_files": level(intval(metrics.get("p80_office_result_file_count")), "Office output files", "native_office_file_gate", "Office file gate only.", ["anti_false_pass_audit"], "Office files are not object rows.", "Office 文件数不是对象行数。"),
    }


def level(count: int, unit: str, kind: str, claim: str, refs: list[str], notes: str, zh_notes: str) -> dict[str, Any]:
    return {
        "count": count,
        "unit": unit,
        "denominator_kind": kind,
        "strict_claim": claim,
        "evidence_refs": refs,
        "notes": notes,
        "zh_notes": zh_notes,
    }


def build_blockers(campaign: dict[str, Any], schema_policy: dict[str, Any]) -> dict[str, Any]:
    by_reason = {key: intval(value) for key, value in section(campaign, "remaining_by_blocker").items()}
    by_family = {key: intval(value) for key, value in section(campaign, "remaining_by_family").items()}
    return {
        "total": sum(by_reason.values()),
        "by_reason": by_reason,
        "by_family": by_family,
        "schema_policy_rejections": dict(section(schema_policy, "rejection_by_reason")),
    }


def build_families(feasibility: dict[str, Any], campaign: dict[str, Any], hydration: dict[str, Any], gaps: list[dict[str, Any]]) -> dict[str, Any]:
    families: dict[str, Any] = {}
    remaining = section(campaign, "remaining_by_family")
    hydrated = section(hydration, "hydrated_by_family")
    blockers = family_blockers(gaps)
    for name, counts in section(feasibility, "family_counts").items():
        if isinstance(counts, dict):
            families[name] = family_summary(counts, name, remaining, hydrated, blockers[name])
    return families


def family_summary(counts: dict[str, Any], name: str, remaining: dict[str, Any], hydrated: dict[str, Any], blockers: Counter[str]) -> dict[str, int]:
    total = sum(intval(value) for value in counts.values())
    missing = blockers["no_semantic_value"]
    resolve = blockers["resolve_failure"]
    return {
        "total": total,
        "semantic_value_available": max(total - intval(counts.get("no_descendant_value")) - intval(counts.get("resolve_fail")), 0),
        "no_semantic_value": missing,
        "resolve_failure": resolve,
        "pending_proof": blockers["semantic_value_available_pending_proof"],
        "explicit_unsupported": sum(count for reason, count in blockers.items() if is_explicit_unsupported(reason)),
        "remaining": intval(remaining.get(name)),
        "hydrated": intval(hydrated.get(name)),
    }


def family_blockers(gaps: list[dict[str, Any]]) -> defaultdict[str, Counter[str]]:
    blockers: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for row in gaps:
        blockers[str(row.get("family", ""))][str(row.get("blocker_type", ""))] += intval(row.get("count"), 1)
    return blockers


def code_gate_summary(audit: dict[str, Any]) -> dict[str, Any]:
    metrics = section(audit, "metrics")
    office = section(audit, "office_freshness")
    mcp = section(audit, "mcp_protocol")
    live_alias_count = alias_operation_count(ROOT / SOURCE_PATHS["campaign_promotion_rows"])
    alias_evidence_count = alias_evidence_row_count()
    return {
        "anti_false_pass_gate": bool(audit.get("gate_pass")) and live_alias_count == 0,
        "exact_after_value_oracle_fail_count": intval(metrics.get("p90_exact_after_value_oracle_fail_count")),
        "aggregate_replay_object_row_count": intval(metrics.get("p90_rows_with_aggregate_replay_count")),
        "marker_only_mutation_row_count": intval(metrics.get("p90_rows_with_marker_only_mutation_count")),
        "alias_operation_row_count": intval(metrics.get("p90_alias_operation_row_count")) + live_alias_count,
        "alias_operation_evidence_row_count": alias_evidence_count,
        "package_only_office_pass_row_count": intval(metrics.get("p90_rows_with_package_only_office_pass_count")),
        "office_expected_output_file_count": intval(office.get("p80_office_expected_output_file_count")),
        "office_result_file_count": intval(office.get("p80_office_result_file_count")),
        "office_missing_result_file_count": intval(office.get("p80_office_missing_result_file_count")),
        "repair_dialog_count": intval(office.get("repair_dialog_count")),
        "security_dialog_count": intval(office.get("security_dialog_count")),
        "unreadable_content_count": intval(office.get("unreadable_content_count")),
        "real_mcp_protocol_replay_pass": bool(mcp.get("real_mcp_protocol_replay_pass")),
        "mcp_list_tools_pass": bool(mcp.get("mcp_list_tools_pass")),
        "mcp_call_tool_replay_pass": bool(mcp.get("mcp_call_tool_replay_pass")),
        "direct_mcp_function_call_count": intval(mcp.get("direct_mcp_function_call_count")),
    }


def alias_evidence_row_count() -> int:
    path = ROOT / SOURCE_PATHS["campaign_alias_operation_rows"]
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def full_claim_proven(levels: dict[str, Any], blockers: dict[str, Any], gates: dict[str, Any]) -> bool:
    return (
        blockers["total"] == 0
        and levels["semantic_editable"]["count"] == levels["surface_editable"]["count"]
        and gates["anti_false_pass_gate"]
        and gate_zero_failures(gates)
    )


def gate_zero_failures(gates: dict[str, Any]) -> bool:
    allowed_nonzero = {
        "alias_operation_evidence_row_count",
        "office_result_file_count",
        "office_expected_output_file_count",
    }
    zero_keys = [key for key in gates if key.endswith("_count") and key not in allowed_nonzero]
    return all(gates[key] == 0 for key in zero_keys) and gates["real_mcp_protocol_replay_pass"]


def claim_summary(levels: dict[str, Any], blockers: dict[str, Any], gates: dict[str, Any]) -> dict[str, Any]:
    return {
        "allowed": f"Measured surface-editable rows: {levels['surface_editable']['count']}; measured row-level semantic-editable rows: {levels['semantic_editable']['count']}.",
        "forbidden": "No full OOXML compatibility, full Office compatibility, all-elements fully editable, or global full-write claim.",
        "current": "Full semantic editability is not proven while blockers or anti-false-pass gates remain.",
        "surface_editable_count": levels["surface_editable"]["count"],
        "semantic_editable_count": levels["semantic_editable"]["count"],
        "semantic_blocker_count": blockers["total"],
        "anti_false_pass_gate": gates["anti_false_pass_gate"],
    }


def unit_definitions() -> dict[str, dict[str, str]]:
    return {
        "xml_element_instances": {"unit": "raw XML elements", "meaning": "Every XML tag occurrence in measured packages.", "zh": "样本包里的每一个 XML 标签出现次数。"},
        "object_rows": {"unit": "object rows", "meaning": "Normalized object-candidate rows; not raw XML tags.", "zh": "归一化对象行，不是原始 XML 标签。"},
        "office_output_files": {"unit": "files", "meaning": "Edited packages opened by native Office.", "zh": "真实 Office 打开的输出文件数。"},
        "package_dependency_rows": {"unit": "dependency rows", "meaning": "Non-XML OPC dependencies tracked outside XML element counts.", "zh": "XML 元素之外的 OPC 依赖行。"},
    }


def source_integrity() -> dict[str, Any]:
    rows = [source_state(source_id, rel) for source_id, rel in SOURCE_PATHS.items()]
    return {
        "source_count": len(rows),
        "missing_count": sum(1 for row in rows if not row["exists"]),
        "sources": rows,
    }


def source_state(source_id: str, rel: str) -> dict[str, Any]:
    path = ROOT / rel
    row: dict[str, Any] = {"source_id": source_id, "exists": path.exists()}
    if path.exists() and path.is_file():
        data = path.read_bytes()
        row.update({"size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    return row


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    out = Path(args.out)
    write_json(out, build_ledger())
    print(out)


if __name__ == "__main__":
    main()
