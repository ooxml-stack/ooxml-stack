#!/usr/bin/env python3
"""Build the human OOXML capability dashboard from the machine ledger."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from build_ooxml_element_capability_ledger import DEFAULT_OUT, build_ledger, write_json
from replay_timeout_metrics import replay_timeout_counts
def fmt(value: int | float | str | bool | None) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return "n/a" if value is None else str(value)
def table(headers: list[str], rows: list[list[object]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |"]
    out.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        out.append("| " + " | ".join(fmt(value) for value in row) + " |")
    return out
def evidence(refs: list[str], ledger: dict[str, Any]) -> str:
    sources = ledger.get("raw_sources", {})
    return ", ".join(sources.get(ref, ref) for ref in refs) or "none"
def level_rows(ledger: dict[str, Any]) -> list[list[object]]:
    rows = []
    order = [
        "xml_element_instances",
        "object_candidates",
        "readable_inspectable",
        "semantic_handle_object_denominator",
        "opaque_binary_package_dependencies",
        "surface_editable",
        "semantic_editable",
        "full_write",
        "unsupported_or_not_proven",
        "office_output_files",
    ]
    for key in order:
        info = ledger["levels"][key]
        rows.append([
            key,
            info["count"],
            info["unit"],
            info["denominator_kind"],
            info["strict_claim"],
            evidence(info["evidence_refs"], ledger),
        ])
    return rows
def unit_rows(ledger: dict[str, Any]) -> list[list[object]]:
    return [[key, info["unit"], info["meaning"], info["zh"]] for key, info in ledger["unit_definitions"].items()]


def blocker_rows(ledger: dict[str, Any]) -> list[list[object]]:
    rows = [[key, value] for key, value in ledger["blockers"]["by_reason"].items()]
    rows.sort(key=lambda row: (-int(row[1]), str(row[0])))
    return rows
def family_rows(ledger: dict[str, Any]) -> list[list[object]]:
    rows = []
    for family, info in ledger["families"].items():
        rows.append([
            family,
            info["total"],
            info["semantic_value_available"],
            info["hydrated"],
            info["remaining"],
            info["pending_proof"],
            info["explicit_unsupported"],
            info["no_semantic_value"],
            info["resolve_failure"],
        ])
    rows.sort(key=lambda row: (-int(row[4]), str(row[0])))
    return rows
def remaining_bucket_rows(ledger: dict[str, Any]) -> list[list[object]]:
    summary = ledger.get("remaining_bucket_summary", {})
    candidate = next(iter(summary.get("candidate_packages", [])), {})
    replay = replay_timeout_counts(summary.get("known_replay_timeout_packages", []))
    return [
        ["remaining_bucket_schema", summary.get("schema_version", "missing")],
        ["candidate_package_count", len(summary.get("candidate_packages", []))],
        ["known_boundary_package_count", len(summary.get("known_boundary_packages", []))],
        ["known_replay_timeout_package_count", replay["known_replay_timeout_package_count"]],
        ["known_replay_timeout_entry_count", replay["known_replay_timeout_entry_count"]],
        ["known_replay_timeout_package_scope_count", replay["known_replay_timeout_package_scope_count"]],
        ["known_replay_timeout_operation_scope_count", replay["known_replay_timeout_operation_scope_count"]],
        ["policy_expansion_opportunity_count", len(summary.get("safe_policy_expansion_opportunities", []))],
        ["family_model_opportunity_count", len(summary.get("family_model_opportunities", []))],
        ["top_candidate_package", candidate.get("package_id", "")],
        ["top_candidate_family", candidate.get("family", "")],
        ["top_candidate_planned_rows", candidate.get("planned_safe_rows", 0)],
        ["top_candidate_action", candidate.get("recommended_action", "")],
    ]
def chunk_replay_rows(ledger: dict[str, Any]) -> list[list[object]]:
    summary = ledger.get("chunk_replay_summary", {})
    statuses = ", ".join(f"{key}: {value}" for key, value in summary.get("status_counts", {}).items())
    current = ", ".join(f"{key}: {value}" for key, value in summary.get("current_plan_status_counts", {}).items())
    legacy = ", ".join(f"{key}: {value}" for key, value in summary.get("legacy_or_superseded_failure_counts", {}).items())
    slow = "; ".join(f"{row.get('id')} ({row.get('status')}, {row.get('seconds')}s)" for row in summary.get("slowest_chunks", []))
    return [
        ["scope", "cumulative chunk campaign; not a single-commit delta"],
        ["promoted_row_count", summary.get("promoted_row_count", 0)],
        ["promoted_chunk_count", summary.get("promoted_chunk_count", 0)],
        ["slow_replay_promoted_row_count", summary.get("slow_replay_promoted_row_count", 0)],
        ["slow_replay_promoted_chunk_count", summary.get("slow_replay_promoted_chunk_count", 0)],
        ["chunk_record_count", summary.get("chunk_record_count", 0)],
        ["raw_status_counts", statuses],
        ["current_plan_status_counts", current or "none"],
        ["current_plan_failure_count", summary.get("current_plan_failure_count", 0)],
        ["current_plan_pending_chunk_count", summary.get("current_plan_pending_chunk_count", 0)],
        ["legacy_or_superseded_failure_counts", legacy or "none"],
        ["promotion_row_count_total", summary.get("promotion_row_count", 0)],
        ["run_elapsed_seconds", summary.get("run_elapsed_seconds", 0)],
        ["cumulative_chunk_elapsed_seconds", summary.get("cumulative_chunk_elapsed_seconds", 0)],
        ["next_plan_scope", summary.get("next_plan_scope", "")],
        ["next_plan_filters", json.dumps(summary.get("next_plan_filters", {}), sort_keys=True)],
        ["next_plan_chunk_count", summary.get("next_plan_chunk_count", 0)],
        ["next_plan_row_count", summary.get("next_plan_row_count", 0)],
        ["next_package_id", summary.get("next_package_id", "")],
        ["recommended_next_action", summary.get("recommended_next_action", "")],
        ["slowest_chunks", slow],
    ]
def close_error_rows(ledger: dict[str, Any]) -> list[list[object]]:
    diag = ledger.get("close_error_diagnostic_summary", {})
    rerun = ledger.get("close_error_rerun_summary", {})
    return [
        ["close_error_office_result_count", diag.get("close_error_office_result_count", 0)],
        ["close_error_package_count", diag.get("close_error_package_count", 0)],
        ["close_error_candidate_rows", diag.get("candidate_row_count", 0)],
        ["rerun_allowed_count", diag.get("rerun_allowed_count", 0)],
        ["office_only_rerun_count", rerun.get("office_only_rerun_count", 0)],
        ["automation_transient_count", rerun.get("automation_transient_count", 0)],
        ["confirmed_boundary_count", rerun.get("confirmed_boundary_count", 0)],
        ["recovered_promoted_row_count", rerun.get("recovered_promoted_row_count", 0)],
    ]
def gate_rows(ledger: dict[str, Any]) -> list[list[object]]:
    return [[key, value] for key, value in ledger["code_gate_summary"].items()]


def office_boundary_rows(ledger: dict[str, Any]) -> list[list[object]]:
    summary = ledger["office_boundary_summary"]
    statuses = sorted(set(summary["files_by_status"]) | set(summary["candidate_rows_by_status"]))
    return [
        [
            status,
            summary["files_by_status"].get(status, 0),
            summary["candidate_rows_by_status"].get(status, 0),
            "Office pass evidence; promotion rules decide count" if status == "pass" else "boundary evidence only",
        ]
        for status in statuses
    ]


def office_boundary_detail_rows(ledger: dict[str, Any]) -> list[list[object]]:
    return [
        [
            row.get("package_id", ""),
            row.get("status", ""),
            row.get("candidate_rows", 0),
            row.get("excluded_from_future_selection", False),
            row.get("office_result_path", ""),
            row.get("message_excerpt", ""),
        ]
        for row in ledger["office_boundary_summary"].get("failed_details", [])
    ]
def source_rows(ledger: dict[str, Any]) -> list[list[object]]:
    rows = []
    for row in ledger["source_integrity"]["sources"]:
        rows.append([row["source_id"], row["exists"], row.get("size", "n/a"), row.get("sha256", "n/a")])
    return rows
def claim_rows(ledger: dict[str, Any]) -> list[list[object]]:
    claim = ledger["claim_summary"]
    return [
        ["allowed", claim["allowed"]],
        ["forbidden", claim["forbidden"]],
        ["current", claim["current"]],
        ["surface_editable_count", claim["surface_editable_count"]],
        ["semantic_editable_count", claim["semantic_editable_count"]],
        ["full_claim_proven", ledger["full_claim_proven"]],
        ["semantic_blocker_count", claim["semantic_blocker_count"]],
        ["anti_false_pass_gate", claim["anti_false_pass_gate"]],
    ]
def add_section(lines: list[str], title: str, body: list[str]) -> None:
    lines.extend(["", f"## {title}", "", *body])


def purpose_section() -> list[str]:
    return [
        "This is the long-lived human and agent entry point for OOXML capability claims.",
        "",
        "It answers one question:",
        "",
        "> For the measured corpus, how many OOXML things are counted, readable,",
        "> safely writable, semantically writable, fully writable, or not proven?",
        "",
        "Use capability names and measured denominators here. Historical run",
        "directories such as `release-evidence/p*/` are audit inputs, not the public",
        "claim surface.",
    ]
def command_section() -> list[str]:
    return [
        "- `make ledger` writes `artifacts/ooxml-element-capability-ledger.json`.",
        "- `make dashboard` writes and opens `artifacts/OOXML-ELEMENT-CAPABILITY-DASHBOARD.html`.",
        "- `make dashboard OPEN=0` writes the same HTML without opening it.",
        "- `make dashboard-md OUT=artifacts/ooxml-ledger-dashboard.md` writes a Markdown snapshot.",
        "- `make campaign-ledgers` regenerates local ignored burn-down cache JSONL files.",
        "",
        "`artifacts/` is ignored by git. Commit generated evidence only when a",
        "capability-based release bundle is intentionally frozen. Large campaign",
        "cache JSONL files are ignored and should be regenerated locally.",
    ]
def how_to_read_rows() -> list[list[object]]:
    return [
        ["XML element instances", "raw XML elements", "total XML scale", "object support or editability"],
        ["object candidates", "object rows", "normalized possible objects", "readable or writable support"],
        ["readable / inspectable", "object rows", "can be classified and inspected", "safe write"],
        ["surface-editable", "object rows", "safe bounded object-level mutation", "semantic understanding"],
        ["semantic-editable", "object rows", "modeled semantic edit with exact oracle", "full object creation"],
        ["Office output files", "files", "edited files opened by native Office", "per-object semantic pass"],
    ]
def claim_boundary_section() -> list[str]:
    return [
        "- Raw XML element counts are not editable object counts.",
        "- Readable / inspectable rows are not automatically writable.",
        "- Surface-editable rows prove safe bounded writes, not semantic understanding.",
        "- Semantic-editable rows require exact before/requested/after value proof.",
        "- Office output file pass is a file-level gate, not an object-row pass.",
        "- No full OOXML compatibility, full Office compatibility, or global full-write claim is proven.",
        "- Anti-false-pass gate counts and campaign Office boundary counts use different evidence scopes.",
    ]


def build_dashboard(ledger: dict[str, Any] | None = None) -> str:
    data = ledger or build_ledger()
    lines = [
        "# OOXML Element Capability Ledger",
        "",
        "Source: current working-tree ledger. This is a live dashboard, not a release freeze.",
        f"Generated: {data['generated_at']}",
    ]
    add_section(lines, "Purpose", purpose_section())
    add_section(lines, "Commands", command_section())
    add_section(lines, "How To Read The Numbers", table(["Metric", "Unit", "Meaning", "What it does not prove"], how_to_read_rows()))
    add_section(lines, "Claim Summary", table(["Field", "Value"], claim_rows(data)))
    add_section(lines, "Unit Definitions", table(["Level", "Unit", "Meaning", "中文"], unit_rows(data)))
    add_section(lines, "Capability Levels", table(["Level", "Count", "Unit", "Denominator", "Strict claim", "Evidence"], level_rows(data)))
    add_section(lines, "Semantic Blockers", table(["Reason", "Count"], blocker_rows(data)))
    add_section(lines, "Families", table(["Family", "Total", "Semantic value available", "Hydrated", "Remaining", "Pending proof", "Explicit unsupported", "No semantic value", "Resolve failure"], family_rows(data)))
    add_section(lines, "Remaining Bucket Acceleration", table(["Field", "Value"], remaining_bucket_rows(data)))
    add_section(lines, "Chunk Replay Campaign", table(["Field", "Value"], chunk_replay_rows(data)))
    add_section(lines, "Close Error Diagnostics", table(["Field", "Value"], close_error_rows(data)))
    add_section(lines, "Anti-False-Pass Gate Scope", table(["Gate", "Value"], gate_rows(data)))
    add_section(lines, "Campaign Office Boundary Scope", table(["Office status", "Files", "Candidate rows", "Ledger treatment"], office_boundary_rows(data)))
    add_section(lines, "Campaign Office Boundary Details", table(["Package", "Status", "Candidate rows", "Excluded", "Office result", "Message"], office_boundary_detail_rows(data)))
    add_section(lines, "Source Integrity", table(["Source", "Exists", "Size", "SHA-256"], source_rows(data)))
    add_section(lines, "Claim Boundary", claim_boundary_section())
    return "\n".join(lines) + "\n"


def load_or_build_ledger(path: str | None) -> dict[str, Any]:
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    data = build_ledger()
    write_json(DEFAULT_OUT, data)
    return data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", help="Machine ledger JSON path")
    parser.add_argument("--out", help="Optional markdown output path")
    args = parser.parse_args()
    dashboard = build_dashboard(load_or_build_ledger(args.ledger))
    if args.out:
        Path(args.out).write_text(dashboard, encoding="utf-8")
    print(dashboard, end="")


if __name__ == "__main__":
    main()
