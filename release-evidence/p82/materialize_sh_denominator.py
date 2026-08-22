#!/usr/bin/env python3
"""Materialize the P82 SH semantic denominator."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from ooxml_operation_engine.semantic import scan_text_handles

REQUIRED_FAMILIES = {
    "text_container", "table_cell_text", "custom_xml_payload", "custom_xml_property",
    "custom_xml_schema", "math_object", "vml_drawing", "chart_drawing",
    "office_extension", "office_chart_extension", "drawing_extension",
    "alternate_content", "wps_extension", "vendor_private_extension",
}

FAMILY_MAP = {
    "sharepoint_property": "custom_xml_property",
    "legacy_office_drawing": "vml_drawing",
    "office_drawing_sketch_extension": "drawing_extension",
}


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    counters: Counter[str] = Counter()
    family_counts: Counter[str] = Counter()
    format_counts: Counter[str] = Counter()
    with args.output.open("w", encoding="utf-8") as out:
        _write_p80_rows(args.p80_rows, out, counters, family_counts, format_counts)
        _write_text_rows(args.manifest, args.corpus_root, out, counters, family_counts, format_counts)
    summary = _summary(counters, family_counts, format_counts)
    args.summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0 if summary["gate_pass"] else 1


def _write_p80_rows(path: Path, out, counters: Counter, family_counts: Counter, format_counts: Counter) -> None:
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            source = json.loads(line)
            row = _p80_row(source)
            _write_row(row, out, counters, family_counts, format_counts)


def _p80_row(source: dict[str, Any]) -> dict[str, Any]:
    family = _normalize_family(source.get("family", ""))
    return {
        "row_id": f"p80|{source['row_id']}",
        "source_phase": "p80",
        "source_row_id": source["row_id"],
        "source_family": source.get("family", ""),
        "family": family,
        "format": source.get("format", ""),
        "input_file": source.get("input_file", ""),
        "package_id": source.get("package_id", ""),
        "part_name": source.get("part_name", ""),
        "stable_id": source.get("stable_id", ""),
        "selector": source.get("selector", ""),
        "qname": source.get("qname", ""),
        "status": "semantic-ready" if source.get("edit_depth") == "semantic-editable" else "surface-ready",
        "edit_depth": source.get("edit_depth", "surface-editable"),
        "operation_id": source.get("operation_id", ""),
        "operations": [source.get("operation_id", "")],
        "aggregate_or_package_only": _is_aggregate_or_package_only(source),
        "claimable_as_object_level": bool(source.get("claimable_as_object_level_active_editable")),
        "evidence": {
            "public_api_edit_pass": bool(source.get("public_api_edit_pass")),
            "public_api_locate_pass": bool(source.get("public_api_locate_pass")),
            "office_gate_status": source.get("office_gate_status", ""),
            "target_changed": bool(source.get("target_changed")),
            "sibling_unexpected_mutation_count": source.get("sibling_unexpected_mutation_count", 0),
        },
    }


def _write_text_rows(manifest: Path, corpus_root: Path, out, counters: Counter, family_counts: Counter, format_counts: Counter) -> None:
    for item in _selected_manifest_rows(manifest):
        path = corpus_root / item["path"]
        try:
            handles = scan_text_handles(path, item["format"])
        except Exception as exc:
            counters["text_scan_failure_count"] += 1
            counters[f"text_scan_failure:{type(exc).__name__}"] += 1
            continue
        counters["text_scan_package_count"] += 1
        for handle in handles:
            row = _text_row(item, handle)
            _write_row(row, out, counters, family_counts, format_counts)


def _selected_manifest_rows(manifest: Path) -> Iterable[dict[str, str]]:
    with manifest.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if (row.get("expected_status") or "pass") != "pass":
                continue
            if row.get("format") not in {"docx", "pptx"}:
                continue
            yield row


def _text_row(item: dict[str, str], handle: Any) -> dict[str, Any]:
    family = "table_cell_text" if handle.kind == "cell" else "text_container"
    return {
        "row_id": f"p82-text|{item['id']}|{handle.stable_id}",
        "source_phase": "p82-native-text-scan",
        "source_row_id": "",
        "source_family": handle.kind,
        "family": family,
        "format": handle.format,
        "input_file": item["path"],
        "package_id": item["id"],
        "part_name": "document" if handle.format == "docx" else "presentation",
        "stable_id": handle.stable_id,
        "selector": handle.target,
        "qname": "",
        "status": "semantic-ready",
        "edit_depth": "semantic-editable",
        "operation_id": handle.operations[0] if handle.operations else "",
        "operations": list(handle.operations),
        "text_preview": handle.text[:120],
        "aggregate_or_package_only": False,
        "claimable_as_object_level": True,
        "evidence": {"scanner": "ooxml_operation_engine.semantic.scan_text_handles"},
    }


def _write_row(row: dict[str, Any], out, counters: Counter, family_counts: Counter, format_counts: Counter) -> None:
    counters["row_count"] += 1
    family_counts[row["family"]] += 1
    format_counts[row["format"]] += 1
    if row["source_phase"] == "p80":
        counters["p80_joined_count"] += 1
    if row["edit_depth"] == "semantic-editable":
        counters["semantic_editable_count"] += 1
    if row["edit_depth"] == "surface-editable":
        counters["surface_editable_count"] += 1
    if row["aggregate_or_package_only"]:
        counters["aggregate_or_package_only_rejected_count"] += 1
        return
    out.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _summary(counters: Counter, family_counts: Counter, format_counts: Counter) -> dict[str, Any]:
    missing = sorted(REQUIRED_FAMILIES - set(family_counts))
    return {
        "schema_version": "p82-sh-semantic-denominator-summary-v1",
        "gate_pass": not missing and counters["p80_joined_count"] == 296144 and counters["aggregate_or_package_only_rejected_count"] == 0 and counters["text_scan_failure_count"] == 0,
        "required_family_count": len(REQUIRED_FAMILIES),
        "required_family_present_count": len(REQUIRED_FAMILIES - set(missing)),
        "missing_required_families": missing,
        "row_count": counters["row_count"],
        "p80_joined_count": counters["p80_joined_count"],
        "semantic_editable_count": counters["semantic_editable_count"],
        "surface_editable_count": counters["surface_editable_count"],
        "aggregate_or_package_only_rejected_count": counters["aggregate_or_package_only_rejected_count"],
        "text_scan_package_count": counters["text_scan_package_count"],
        "text_scan_failure_count": counters["text_scan_failure_count"],
        "family_counts": dict(sorted(family_counts.items())),
        "format_counts": dict(sorted(format_counts.items())),
    }


def _normalize_family(family: str) -> str:
    return FAMILY_MAP.get(family, family)


def _is_aggregate_or_package_only(row: dict[str, Any]) -> bool:
    return row.get("package_id") == "aggregate" or row.get("part_name") == "aggregate" or str(row.get("stable_id", "")).startswith("aggregate:")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--p80-rows", type=Path, default=Path("release-evidence/p77/public-api-object-edit-rows.jsonl"))
    parser.add_argument("--manifest", type=Path, default=Path("../ooxml-native-corpus/manifests/corpus.csv"))
    parser.add_argument("--corpus-root", type=Path, default=Path("../ooxml-native-corpus"))
    parser.add_argument("--output", type=Path, default=Path("release-evidence/p82/sh-semantic-denominator.jsonl"))
    parser.add_argument("--summary", type=Path, default=Path("release-evidence/p82/sh-semantic-denominator-summary.json"))
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
