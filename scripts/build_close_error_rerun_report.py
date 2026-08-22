#!/usr/bin/env python3
"""Classify close-error Office-only rerun results."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from semantic_editability_unlock_common import EVIDENCE, ROOT, table, write_json, write_md

DIAGNOSTIC = EVIDENCE / "close-error-diagnostic-summary.json"
RAW = EVIDENCE / "close-error-rerun-raw.json"
OUT_JSON = EVIDENCE / "close-error-rerun-summary.json"
OUT_MD = EVIDENCE / "close-error-rerun-dashboard.md"


def main() -> int:
    summary = build_report(ROOT, DIAGNOSTIC, RAW)
    write_json(OUT_JSON, summary)
    write_md(OUT_MD, markdown(summary))
    print(json.dumps({"summary": str(OUT_JSON), "dashboard": str(OUT_MD)}, indent=2))
    return 0


def build_report(root: Path, diagnostic_path: Path, raw_path: Path) -> dict[str, Any]:
    diagnostic = _read_json(diagnostic_path)
    raw = _read_json(raw_path)
    source = _source_index(root, diagnostic.get("records", []))
    records = [_record(root, row, source.get(_norm_path(root, row.get("file", "")), {})) for row in raw.get("results", [])]
    counts = _counts(records)
    return {
        "schema_version": "close-error-rerun-report-v1",
        "office_only_rerun_count": len(records),
        "automation_transient_count": counts["automation_transient"],
        "confirmed_boundary_count": counts["confirmed_boundary"],
        "prompt_or_dialog_boundary_count": counts["prompt_or_dialog_boundary"],
        "infra_failed_count": counts["infra_failed"],
        "ambiguous_count": counts["ambiguous"],
        "recovered_promoted_row_count": 0,
        "promotion_eligible_after_rerun_count": sum(row["promotion_eligible_after_rerun"] for row in records),
        "raw_office_summary": raw.get("summary", {}),
        "records": records,
    }


def markdown(summary: dict[str, Any]) -> str:
    lines = ["# Close Error Rerun Summary", ""]
    for key in (
        "office_only_rerun_count",
        "automation_transient_count",
        "confirmed_boundary_count",
        "prompt_or_dialog_boundary_count",
        "infra_failed_count",
        "ambiguous_count",
        "recovered_promoted_row_count",
    ):
        lines.append(f"- {key}: {summary[key]}")
    lines.append("")
    rows = [
        (
            row["package_id"],
            row["source_label"],
            row["office_rerun_status"],
            row["classification"],
            row["promotion_eligible_after_rerun"],
            row["reason"],
        )
        for row in summary["records"]
    ]
    lines += table("Rerun Records", ("Package", "Source", "Rerun status", "Classification", "Eligible", "Reason"), rows)
    return "\n".join(lines)


def _record(root: Path, rerun: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    status = str(rerun.get("status", "unknown"))
    classification, reason = _classification(status)
    return {
        "source_label": source.get("source_label", ""),
        "source_chunk_id": source.get("source_chunk_id", ""),
        "package_id": source.get("package_id", ""),
        "family": source.get("family", ""),
        "operation_ids": source.get("operation_ids", []),
        "planned_row_count": int(source.get("planned_row_count") or 0),
        "output_file": _norm_path(root, rerun.get("file", "")),
        "office_rerun_status": status,
        "office_rerun_stage": _stage(status),
        "office_rerun_message": str(rerun.get("message", ""))[:300],
        "elapsed_seconds": rerun.get("elapsed_seconds", 0),
        "automation_transient_suspected": classification == "automation_transient",
        "real_boundary_suspected": classification == "confirmed_boundary",
        "promotion_eligible_after_rerun": classification == "automation_transient",
        "classification": classification,
        "reason": reason,
    }


def _classification(status: str) -> tuple[str, str]:
    if status == "pass":
        return "automation_transient", "Office-only rerun passed; exact row replay is required before promotion"
    if status in {"pass_with_dialog", "pass_with_security_dialog", "security_dialog", "macro_security_dialog"}:
        return "prompt_or_dialog_boundary", "Office rerun produced a dialog and remains boundary evidence"
    if status in {"repair_dialog", "unreadable_content", "close_error", "office_crash"}:
        return "confirmed_boundary", f"Office-only rerun repeated blocking status {status}"
    if status in {"automation_denied", "office_missing", "open_error", "timeout"}:
        return "infra_failed", f"Office rerun failed through infrastructure/status {status}"
    return "ambiguous", f"Unhandled Office rerun status {status}"


def _stage(status: str) -> str:
    if status in {"repair_dialog", "unreadable_content", "open_error"}:
        return "open"
    if status in {"close_error", "pass", "pass_with_dialog", "pass_with_security_dialog"}:
        return "close"
    return "unknown"


def _counts(records: list[dict[str, Any]]) -> dict[str, int]:
    keys = ("automation_transient", "confirmed_boundary", "prompt_or_dialog_boundary", "infra_failed", "ambiguous")
    return {key: sum(row["classification"] == key for row in records) for key in keys}


def _source_index(root: Path, records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {_norm_path(root, row.get("output_file", "")): row for row in records if row.get("output_file")}


def _norm_path(root: Path, value: str) -> str:
    path = Path(value)
    if path.is_absolute() and path.is_relative_to(root):
        return str(path.relative_to(root))
    parts = path.parts
    if parts and parts[0] == "ooxml-stack":
        return str(Path(*parts[1:]))
    return str(path)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


if __name__ == "__main__":
    raise SystemExit(main())
