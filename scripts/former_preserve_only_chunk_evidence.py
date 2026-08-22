"""Evidence helpers for exact-row chunk promotion replay."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def enrich_rows(rows: list[dict[str, Any]], chunk: dict[str, Any], label: str, office: dict[str, Any]) -> list[dict[str, Any]]:
    return [_enrich_row(dict(row), chunk, label, office) for row in rows]


def normalize_checkpoint(data: dict[str, Any] | None, plan_hash: str = "") -> dict[str, Any]:
    data = data or {}
    records = data.get("records", [])
    return {
        "schema_version": data.get("schema_version", "semantic-editability-chunk-checkpoint-v2"),
        "started_at_utc": data.get("started_at_utc") or _now(),
        "updated_at_utc": _now(),
        "plan_hash": data.get("plan_hash") or plan_hash,
        "completed_chunk_ids": _ids(records),
        "promoted_chunk_ids": _ids(records, "promoted"),
        "boundary_chunk_ids": _ids(records, "office_boundary"),
        "failed_audit_chunk_ids": _ids(records, "hard_audit_failed"),
        "skipped_chunk_ids": data.get("skipped_chunk_ids", []),
        "records": records,
    }


def append_checkpoint(path: str, record: dict[str, Any], plan_hash: str = "") -> dict[str, Any]:
    data = read_checkpoint(path, plan_hash)
    data["records"].append(record)
    data = normalize_checkpoint(data, plan_hash)
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return data


def read_checkpoint(path: str, plan_hash: str = "") -> dict[str, Any]:
    target = Path(path)
    data = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    return normalize_checkpoint(data, plan_hash)


def boundary_record(chunk: dict[str, Any], status: str, rows: list[dict[str, Any]], office: dict[str, Any]) -> dict[str, Any]:
    return {
        "chunk_id": chunk["chunk_id"],
        "package_id": chunk.get("package_id"),
        "family": chunk.get("family"),
        "status": status,
        "planned_row_count": chunk.get("planned_row_count"),
        "row_count": len(rows),
        "row_ids_hash": chunk.get("row_ids_hash"),
        "office_result_file": office.get("office_json", ""),
        "office_status": office.get("status", ""),
        "office_return_code": office.get("return_code"),
    }


def timing_summary(records: list[dict[str, Any]], cumulative: list[dict[str, Any]], started: float) -> dict[str, Any]:
    all_records = cumulative
    return {
        "schema_version": "semantic-editability-chunk-timing-v2",
        "run_elapsed_seconds": round(time.monotonic() - started, 3),
        "cumulative_chunk_elapsed_seconds": _elapsed_total(all_records),
        "records": records,
        "run_status_counts": _counts(records),
        "checkpoint_record_count": len(all_records),
        "checkpoint_status_counts": _counts(all_records),
        "per_chunk_elapsed_seconds": {r["chunk_id"]: r.get("duration_s", 0) for r in all_records},
        "slowest_chunks": _slowest(all_records, "chunk_id"),
        "slowest_packages": _slowest(all_records, "package_id"),
        "timed_out_chunks": [r["chunk_id"] for r in all_records if r.get("status") == "timeout"],
        "recommended_next_action": _next_action(all_records),
        **_stage_totals(all_records),
    }


def timing_markdown(summary: dict[str, Any]) -> str:
    lines = ["# Chunk Replay Timing", ""]
    lines += [f"- Run elapsed seconds: {summary['run_elapsed_seconds']}"]
    lines += [f"- Cumulative chunk elapsed seconds: {summary['cumulative_chunk_elapsed_seconds']}"]
    lines += [f"- Cumulative chunk records: {summary['checkpoint_record_count']}"]
    lines += [f"- Recommended next action: {summary['recommended_next_action']}", ""]
    lines += ["Stage timings are rounded; `0` means below measurement precision or unavailable.", ""]
    lines += ["## Status Counts", ""]
    lines += [f"- `{k}`: {v}" for k, v in summary["checkpoint_status_counts"].items()] or ["- none"]
    lines += ["", "## Slowest Chunks", "", "| Chunk | Seconds | Status |", "| --- | ---: | --- |"]
    for row in summary["slowest_chunks"][:10]:
        lines.append(f"| `{row['id']}` | {row['seconds']} | `{row['status']}` |")
    return "\n".join(lines).rstrip() + "\n"


def _enrich_row(row: dict[str, Any], chunk: dict[str, Any], label: str, office: dict[str, Any]) -> dict[str, Any]:
    requested = row.get("requested_semantic_change", {}).get("value")
    row["chunk_id"] = chunk.get("chunk_id")
    row["chunk_label"] = label
    row["cli_path"] = row.get("cli_output_file", "")
    row["mcp_path"] = row.get("mcp_output_file", "")
    row["requested_semantic_value"] = requested
    row["target_changed"] = row.get("target_semantic_changed") is True
    row["exact_after_value_hit"] = row.get("semantic_edit_pass") is True
    row["same_operation_sibling_unchanged"] = row.get("sibling_unexpected_semantic_mutation_count") == 0
    row["relationship_loss_count"] = int(row.get("relationship_loss_count", 0))
    row["missing_part_count"] = int(row.get("missing_part_count", 0))
    row["binary_mutation_count"] = int(row.get("binary_mutation_count", 0))
    row["native_office_status"] = row.get("native_office_result")
    row["native_office_result_file"] = row.get("office_result_id", office.get("office_json", ""))
    row.update(_office_dialog_counts(office))
    return row


def _office_dialog_counts(office: dict[str, Any]) -> dict[str, int]:
    summary = office.get("summary", {})
    status = str(office.get("status", ""))
    return {
        "repair_dialog_count": int(summary.get("repair_dialog_count", status == "repair_dialog")),
        "unreadable_content_count": int(summary.get("unreadable_content_count", status == "unreadable_content")),
        "security_dialog_count": int(summary.get("security_dialog_count", status == "security_dialog")),
        "macro_security_dialog_count": int(summary.get("macro_security_dialog_count", 0)),
        "office_crash_count": int(summary.get("office_crash_count", status == "crash")),
    }


def _ids(records: list[dict[str, Any]], status: str | None = None) -> list[str]:
    return sorted({r["chunk_id"] for r in records if status is None or r.get("status") == status})


def _counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        counts[record["status"]] = counts.get(record["status"], 0) + 1
    return counts


def _stage_totals(records: list[dict[str, Any]]) -> dict[str, float]:
    keys = ("plan_load", "row_selection", "api_replay", "cli_replay", "mcp_replay", "office_gate", "hard_audit", "ledger_refresh")
    return {f"{key}_seconds": round(sum(r.get("stage_timings", {}).get(key, 0) for r in records), 3) for key in keys}


def _elapsed_total(records: list[dict[str, Any]]) -> float:
    return round(sum(float(r.get("duration_s", 0)) for r in records), 3)


def _slowest(records: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    rows = [{"id": r.get(key, ""), "seconds": r.get("duration_s", 0), "status": r.get("status", "")} for r in records]
    return sorted(rows, key=lambda row: row["seconds"], reverse=True)


def _next_action(records: list[dict[str, Any]]) -> str:
    if not records:
        return "run_first_chunk"
    if any(r.get("status") == "promoted" for r in records[-3:]):
        return "continue_same_package_or_next_safe_chunk"
    return "replan_excluding_boundary_packages"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
