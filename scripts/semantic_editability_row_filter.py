"""Row filters for semantic editability chunk planning."""
from __future__ import annotations

from collections import Counter
from typing import Any

from former_preserve_only_promoted_index import row_target_key
from semantic_editability_skip_packages import package_skip_reason


def eligible_rows(
    rows: list[dict[str, Any]],
    promoted_sources: set[str],
    promoted_targets: set[tuple[str, str, str, str]],
    failed_sources: set[str],
    package_skips: dict[str, set[str]],
    filters: dict[str, Any],
) -> tuple[list[dict[str, Any]], Counter[str]]:
    selected, skipped = [], Counter()
    for row in rows:
        reason = skip_reason(row, promoted_sources, promoted_targets, failed_sources, package_skips, filters)
        if reason:
            skipped[reason] += 1
        else:
            selected.append(row)
    return selected, skipped


def skip_reason(
    row: dict[str, Any],
    promoted_sources: set[str],
    promoted_targets: set[tuple[str, str, str, str]],
    failed_sources: set[str],
    package_skips: dict[str, set[str]],
    filters: dict[str, Any],
) -> str:
    if row.get("operation_hydration_status") != "hydrated":
        return "not_hydrated"
    if row.get("source_row_id") in promoted_sources or row_target_key(row) in promoted_targets:
        return "already_promoted"
    if row.get("source_row_id") in failed_sources:
        return "known_row_level_failure"
    if reason := package_skip_reason(
        str(row.get("package_id", "")), package_skips, str(row.get("family", "")), str(row.get("operation_id", ""))
    ):
        return reason
    if str(row.get("part_name", "")).startswith(("customXml/", "docMetadata/")):
        return "public_path_unsupported_part"
    return _filter_reason(row, filters)


def _filter_reason(row: dict[str, Any], filters: dict[str, Any]) -> str:
    for key, reason in (("package_id", "package_filter"), ("family", "family_filter"), ("operation_id", "operation_filter")):
        if filters.get(key) and row.get(key) != filters[key]:
            return reason
    if filters.get("qname") and row.get("qname") != filters["qname"]:
        return "qname_filter"
    if filters.get("fmt") and row.get("format") != filters["fmt"]:
        return "format_filter"
    if filters.get("max_package_mb"):
        package_mb = filters["package_mb_fn"](str(row.get("input_file", ""))) or 0
        if package_mb > filters["max_package_mb"]:
            return "package_size_filter"
    return ""
