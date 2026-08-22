#!/usr/bin/env python3
"""Build native Office boundary analysis for semantic editability."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from campaign_office_boundary_summary import primary_status
from semantic_editability_unlock_common import EVIDENCE, read_json, read_jsonl, table, write_json, write_md

OUT_JSON = EVIDENCE / "office-boundary-analysis.json"
OUT_MD = EVIDENCE / "office-boundary-analysis.md"


def main() -> int:
    checkpoint = read_json(EVIDENCE / "chunk-promotion-checkpoint.json")
    hydrated = read_jsonl(EVIDENCE / "operation-hydration-ledger.jsonl")
    summary = build_analysis(checkpoint.get("records", []), hydrated)
    write_json(OUT_JSON, summary)
    write_md(OUT_MD, markdown(summary))
    print({"analysis": str(OUT_JSON), "dashboard": str(OUT_MD)})
    return 0


def build_analysis(records: list[dict[str, Any]], hydrated: list[dict[str, Any]]) -> dict[str, Any]:
    boundaries = [row for row in records if row.get("status") == "office_boundary"]
    enriched = [_record(row, hydrated) for row in boundaries]
    repeated = _repeated(enriched)
    for row in enriched:
        key = (row["package_id"], row["family"], row["operation_id"])
        row["repeated_for_same_package_family_operation"] = repeated[key] > 1
    return {
        "schema_version": "office-boundary-analysis-v1",
        "boundary_record_count": len(enriched),
        "by_status": dict(Counter(row["edited_package_native_office_status"] for row in enriched).most_common()),
        "by_app": dict(Counter(row["app"] for row in enriched).most_common()),
        "by_family_operation": _by_family_operation(enriched),
        "records": enriched,
    }


def _record(row: dict[str, Any], hydrated: list[dict[str, Any]]) -> dict[str, Any]:
    office = _office_data(row)
    package = str(row.get("package_id", ""))
    family = str(row.get("family", ""))
    operation = _operation(row, hydrated)
    relevant = _relevant_rows(hydrated, package, family, operation)
    status = _office_status(row, office)
    return {
        "original_package_native_office_status": "unknown_not_measured_in_this_artifact",
        "edited_package_native_office_status": status,
        "app": _app(office),
        "package_id": package,
        "family": family,
        "operation_id": operation,
        "candidate_row_count": int(row.get("planned_row_count") or row.get("rows") or 0),
        "part_name_summary": dict(Counter(item.get("part_name", "") for item in relevant).most_common(10)),
        "qname_summary": dict(Counter(item.get("qname", "") for item in relevant).most_common(10)),
        "api_cli_mcp_passed_before_office_failed": bool(row.get("public_path_file") and row.get("office_result_file")),
        "smaller_chunk_size_recommended": _smaller_chunk(row, status),
        "remain_boundary_only": status in {"repair_dialog", "unreadable_content", "close_error", "security_dialog", "timeout"},
        "operation_should_be_blacklisted": False,
        "looks_like_office_close_behavior": status == "close_error",
        "office_result_file": row.get("office_result_file", ""),
        "chunk_id": row.get("chunk_id", ""),
    }


def _office_data(row: dict[str, Any]) -> dict[str, Any]:
    path = row.get("office_result_file", "")
    if not path:
        return {}
    full = Path(path)
    if not full.is_absolute():
        full = EVIDENCE.parents[1] / path
    return json.loads(full.read_text(encoding="utf-8")) if full.exists() else {}


def _office_status(row: dict[str, Any], office: dict[str, Any]) -> str:
    return str(row.get("office", {}).get("status") or primary_status(office))


def _app(office: dict[str, Any]) -> str:
    result = next(iter(office.get("results", [])), {})
    return str(result.get("app") or "unknown")


def _operation(row: dict[str, Any], hydrated: list[dict[str, Any]]) -> str:
    operations = row.get("operation_ids") or []
    if operations:
        return str(operations[0])
    package, family = row.get("package_id"), row.get("family")
    counter = Counter(item.get("operation_id", "") for item in hydrated if item.get("package_id") == package and item.get("family") == family)
    return str(counter.most_common(1)[0][0]) if counter else ""


def _relevant_rows(rows: list[dict[str, Any]], package: str, family: str, operation: str) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("package_id") == package and row.get("family") == family and (not operation or row.get("operation_id") == operation)]


def _smaller_chunk(row: dict[str, Any], status: str) -> bool:
    count = int(row.get("planned_row_count") or row.get("rows") or 0)
    return count > 5 and status in {"close_error", "timeout", "unreadable_content"}


def _repeated(rows: list[dict[str, Any]]) -> Counter[tuple[str, str, str]]:
    return Counter((row["package_id"], row["family"], row["operation_id"]) for row in rows)


def _by_family_operation(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: defaultdict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["family"], row["operation_id"], row["edited_package_native_office_status"])].append(row)
    return [
        {"family": key[0], "operation_id": key[1], "office_status": key[2], "count": len(bucket)}
        for key, bucket in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0]))
    ]


def markdown(summary: dict[str, Any]) -> str:
    lines = ["# Office Boundary Analysis", ""]
    lines += [f"- Boundary record count: {summary['boundary_record_count']}"]
    lines += [f"- By status: {summary['by_status']}", ""]
    lines += table("By Family / Operation", ("Family", "Operation", "Office status", "Count"), [(r["family"], r["operation_id"], r["office_status"], r["count"]) for r in summary["by_family_operation"][:30]])
    lines += table("Boundary Records", ("Package", "Family", "Operation", "Status", "Rows", "Smaller chunk", "Close behavior"), [(r["package_id"], r["family"], r["operation_id"], r["edited_package_native_office_status"], r["candidate_row_count"], r["smaller_chunk_size_recommended"], r["looks_like_office_close_behavior"]) for r in summary["records"][:50]])
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
