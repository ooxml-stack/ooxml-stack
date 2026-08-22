#!/usr/bin/env python3
"""Batch-level counters for former preserve-only promotion evidence."""
from __future__ import annotations

import json
from pathlib import Path


def promotion_metrics(rows_path: Path, out_dir: Path, labels: list[str]) -> dict[str, int]:
    rows = _rows_for_labels(rows_path, labels)
    office = _office_counts(out_dir / "office-results", labels)
    return {
        "api_path_pass_count": sum(row.get("semantic_edit_pass") is True for row in rows),
        "cli_path_pass_count": sum(row.get("cli_path_checked") is True and row.get("cli_return_code") == 0 for row in rows),
        "mcp_path_pass_count": sum(row.get("mcp_path_checked") is True and row.get("mcp_return_code") == 0 for row in rows),
        "native_office_pass_count": sum(row.get("native_office_result") == "pass" for row in rows),
        **office,
    }


def _rows_for_labels(path: Path, labels: list[str]) -> list[dict]:
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [row for row in rows if any(_row_has_label(row, label) for label in labels)]


def _row_has_label(row: dict, label: str) -> bool:
    tokens = (f"api-{label}-", f"cli-{label}-", f"mcp-{label}-", f"cli-{label}.jsonl")
    fields = ("office_result_id", "output_file", "cli_output_file", "mcp_output_file")
    return any(token in str(row.get(field, "")) for field in fields for token in tokens)


def _office_counts(folder: Path, labels: list[str]) -> dict[str, int]:
    counts = {"repair_dialog_count": 0, "unreadable_content_count": 0, "close_error_count": 0, "security_dialog_count": 0}
    for path in folder.glob("*.json"):
        if not any(f"api-{label}-" in path.name for label in labels):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        summary = data.get("summary", {})
        counts["repair_dialog_count"] += int(summary.get("repair_dialog_count", 0))
        counts["unreadable_content_count"] += int(summary.get("unreadable_content_count", 0))
        counts["security_dialog_count"] += int(summary.get("security_dialog_count", 0))
        counts["close_error_count"] += sum(item.get("status") == "close_error" for item in data.get("results", []))
    return counts
