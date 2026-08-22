#!/usr/bin/env python3
"""Run Office-only reruns for close-error diagnostic candidates."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from build_close_error_rerun_report import DIAGNOSTIC, OUT_JSON, OUT_MD, RAW, build_report, markdown
from former_preserve_only_promote_batch import PROJECTS, _office_json, _run_office
from semantic_editability_unlock_common import ROOT, write_json, write_md


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    diagnostic = _read_json(DIAGNOSTIC)
    raw = _read_json(RAW)
    candidates = _select_candidates(diagnostic.get("records", []), raw, args)
    if args.dry_run:
        print(json.dumps({"planned": len(candidates), "candidates": candidates}, indent=2))
        return 0
    if not candidates:
        print(json.dumps({"planned": 0, "results": []}, indent=2))
        return 1
    results = _existing_results(raw) + [_run_record(row) for row in candidates]
    write_json(RAW, _raw_payload(raw, results))
    summary = build_report(ROOT, DIAGNOSTIC, RAW)
    write_json(OUT_JSON, summary)
    write_md(OUT_MD, markdown(summary))
    print(json.dumps({"planned": len(candidates), "summary": str(OUT_JSON), "raw": str(RAW)}, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--priority", default="high")
    parser.add_argument("--candidate-class", default="small_replay_candidate")
    parser.add_argument("--package-id", default="")
    parser.add_argument("--include-existing", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def _select_candidates(records: list[dict[str, Any]], raw: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    seen = set() if args.include_existing else _raw_files(raw)
    selected = [row for row in records if _matches(row, args, seen)]
    selected.sort(key=lambda row: (int(row.get("planned_row_count") or 0), row.get("package_id", ""), row.get("source_label", "")))
    return selected[: args.limit]


def _matches(row: dict[str, Any], args: argparse.Namespace, seen: set[str]) -> bool:
    if not row.get("rerun_allowed"):
        return False
    if args.priority and row.get("diagnostic_priority") != args.priority:
        return False
    if args.candidate_class and row.get("candidate_class") != args.candidate_class:
        return False
    if args.package_id and row.get("package_id") != args.package_id:
        return False
    return _norm(row.get("output_file", "")) not in seen


def _run_record(row: dict[str, Any]) -> dict[str, Any]:
    path = _output_path(row.get("output_file", ""))
    office = _run_office_preserving_source(path)
    result = dict(next(iter(office.get("results", [])), {}))
    result.setdefault("file", _display_path(path))
    result.setdefault("status", office.get("status", "missing"))
    result["source_label"] = row.get("source_label", "")
    result["source_chunk_id"] = row.get("source_chunk_id", "")
    result["source_office_result_file"] = row.get("office_result_file", "")
    result["rerun_office_json"] = office.get("office_json", "")
    result["package_id"] = row.get("package_id", "")
    result["family"] = row.get("family", "")
    result["operation_ids"] = row.get("operation_ids", [])
    result["planned_row_count"] = row.get("planned_row_count", 0)
    return result


def _run_office_preserving_source(path: Path) -> dict[str, Any]:
    office_json = _office_json(path)
    before = office_json.read_bytes() if office_json.exists() else None
    try:
        return _run_office(path, True)
    finally:
        if before is None:
            office_json.unlink(missing_ok=True)
        else:
            office_json.write_bytes(before)


def _raw_payload(previous: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "meta": _meta(),
        "summary": _summary(results),
        "results": results,
    }


def _meta() -> dict[str, Any]:
    return {
        "tool": "run_close_error_office_rerun",
        "timestamp": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "timeout_seconds": 240,
        "dialog_wait_seconds": 30,
    }


def _summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(row.get("status", "unknown")) for row in results)
    return {
        "total": len(results),
        "pass": statuses.get("pass", 0),
        "pass_total": statuses.get("pass", 0) + statuses.get("pass_with_dialog", 0),
        "repair_dialog_count": statuses.get("repair_dialog", 0),
        "unreadable_content_count": statuses.get("unreadable_content", 0),
        "security_dialog_count": statuses.get("security_dialog", 0),
        "benign_dialog_count": statuses.get("pass_with_dialog", 0),
        "office_crash_count": statuses.get("office_crash", 0),
        "macro_security_dialog_count": statuses.get("macro_security_dialog", 0),
        "macro_timeout_count": statuses.get("macro_timeout", 0),
        "by_status": dict(statuses),
        "gate_pass": bool(results) and all(row.get("status") == "pass" for row in results),
    }


def _raw_files(raw: dict[str, Any]) -> set[str]:
    return {_norm(row.get("file", "")) for row in _existing_results(raw)}


def _existing_results(raw: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in raw.get("results", [])]


def _output_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    if path.parts and path.parts[0] == ROOT.name:
        return ROOT.parent / path
    return ROOT / path


def _display_path(path: Path) -> str:
    if path.is_relative_to(PROJECTS):
        return str(path.relative_to(PROJECTS))
    if path.is_relative_to(ROOT):
        return str(path.relative_to(ROOT))
    return str(path)


def _norm(value: str) -> str:
    path = Path(value)
    if path.parts and path.parts[0] == ROOT.name:
        path = Path(*path.parts[1:])
    return str(path)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


if __name__ == "__main__":
    raise SystemExit(main())
