#!/usr/bin/env python3
"""Build close-error diagnostics for semantic-editability Office boundaries."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from campaign_office_boundary_summary import matching_label, primary_status, public_row_count, redacted_message
from semantic_editability_unlock_common import EVIDENCE, ROOT, table, write_json, write_md

OUT_JSON = EVIDENCE / "close-error-diagnostic-summary.json"
OUT_MD = EVIDENCE / "close-error-diagnostic-dashboard.md"


def main() -> int:
    summary = build_diagnostics(ROOT)
    write_json(OUT_JSON, summary)
    write_md(OUT_MD, markdown(summary))
    print(json.dumps({"summary": str(OUT_JSON), "dashboard": str(OUT_MD)}, indent=2))
    return 0


def build_diagnostics(root: Path) -> dict[str, Any]:
    evidence = root / "release-evidence/former-preserve-only-semantic-editability"
    checkpoint = _checkpoint_index(evidence / "chunk-promotion-checkpoint.json", root)
    public_paths = {path.stem.removeprefix("cli-"): path for path in (evidence / "public-paths").glob("cli-*.jsonl")}
    records = []
    for office_path in sorted((evidence / "office-results").glob("api-*.json")):
        data = _read_json(office_path)
        if primary_status(data) != "close_error":
            continue
        records.append(_record(root, evidence, office_path, data, public_paths, checkpoint))
    return _summary(records)


def _record(root: Path, evidence: Path, office_path: Path, data: dict[str, Any], public_paths: dict[str, Path], checkpoint: dict[str, dict[str, Any]]) -> dict[str, Any]:
    result = next(iter(data.get("results", [])), {})
    label = matching_label(public_paths, office_path)
    source = checkpoint.get(_rel(root, office_path), {})
    output = _output_path(root, result.get("file", ""))
    package_id = str(source.get("package_id") or _package_from_output(output))
    row_count = public_row_count(public_paths, office_path)
    message = redacted_message(str(result.get("message", "")), root)
    operation_ids = source.get("operation_ids") or []
    return {
        "source_label": source.get("label") or label,
        "source_chunk_id": source.get("chunk_id", ""),
        "package_id": package_id,
        "format": output.suffix.lstrip(".").lower(),
        "family": source.get("family", ""),
        "operation_ids": operation_ids,
        "planned_row_count": int(source.get("planned_row_count") or row_count),
        "promoted_row_count": int(source.get("promoted_row_count") or 0),
        "office_status": "close_error",
        "office_message": message,
        "office_result_file": _rel(root, office_path),
        "public_path_file": _rel(root, public_paths[label]) if label in public_paths else "",
        "staged_rows_file": _staged_file(root, evidence, source),
        "output_file": _rel(root, output) if output.exists() else str(result.get("file", "")),
        "output_package_hash": _sha256(output) if output.exists() else "",
        "stage": source.get("stage", ""),
        "stage_timings": source.get("stage_timings", {}),
        "candidate_class": _candidate_class(source, output, row_count),
        "diagnostic_priority": _priority(source, output, row_count),
        "rerun_allowed": _rerun_allowed(source, output, row_count),
    }


def _summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    packages = {row["package_id"] for row in records if row["package_id"]}
    return {
        "schema_version": "close-error-diagnostic-v1",
        "close_error_office_result_count": len(records),
        "close_error_package_count": len(packages),
        "candidate_row_count": sum(row["planned_row_count"] for row in records),
        "rerun_allowed_count": sum(row["rerun_allowed"] for row in records),
        "by_package_top20": dict(Counter(row["package_id"] for row in records).most_common(20)),
        "by_family": dict(Counter(row["family"] or "<unknown>" for row in records).most_common()),
        "by_priority": dict(Counter(row["diagnostic_priority"] for row in records).most_common()),
        "records": records,
    }


def markdown(summary: dict[str, Any]) -> str:
    lines = ["# Close Error Diagnostic Summary", ""]
    for key in ("close_error_office_result_count", "close_error_package_count", "candidate_row_count", "rerun_allowed_count"):
        lines.append(f"- {key}: {summary[key]}")
    lines.append("")
    rows = [
        (
            row["package_id"],
            row["family"],
            ",".join(row["operation_ids"]),
            row["planned_row_count"],
            row["diagnostic_priority"],
            row["candidate_class"],
            row["rerun_allowed"],
            row["office_message"][:100],
        )
        for row in summary["records"][:80]
    ]
    lines += table("Close Error Records", ("Package", "Family", "Operations", "Rows", "Priority", "Class", "Rerun", "Message"), rows)
    return "\n".join(lines)


def _checkpoint_index(path: Path, root: Path) -> dict[str, dict[str, Any]]:
    records = _read_json(path).get("records", [])
    return {str(row.get("office_result_file", "")): row for row in records if row.get("office_result_file")}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _output_path(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    parts = path.parts
    if parts and parts[0] == "ooxml-stack":
        return root / Path(*parts[1:])
    if parts and parts[0] == root.name:
        return root.parent / path
    return root / path


def _package_from_output(path: Path) -> str:
    name = path.stem
    for prefix in ("api-",):
        if name.startswith(prefix):
            name = name[len(prefix) :]
    bits = name.split("-")
    for index, bit in enumerate(bits):
        if bit.startswith(("docx_", "pptx_", "xlsx_")):
            return "-".join(bits[index:])
    return ""


def _staged_file(root: Path, evidence: Path, source: dict[str, Any]) -> str:
    chunk_id = source.get("chunk_id")
    path = evidence / "staged-rows" / f"{chunk_id}.jsonl"
    return _rel(root, path) if chunk_id and path.exists() else ""


def _candidate_class(source: dict[str, Any], output: Path, rows: int) -> str:
    if not source:
        return "orphan_office_result"
    if not output.exists():
        return "missing_output"
    return "small_replay_candidate" if rows <= 10 else "large_boundary_candidate"


def _priority(source: dict[str, Any], output: Path, rows: int) -> str:
    if not source or not output.exists():
        return "low"
    if rows <= 10 and source.get("public_path_file"):
        return "high"
    return "medium" if rows <= 25 else "low"


def _rerun_allowed(source: dict[str, Any], output: Path, rows: int) -> bool:
    return bool(source and output.exists() and rows > 0 and source.get("public_path_file"))


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _rel(root: Path, path: Path) -> str:
    return str(path.relative_to(root)) if path.is_relative_to(root) else str(path)


if __name__ == "__main__":
    raise SystemExit(main())
