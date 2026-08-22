"""P90 LLM replay hardening helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]


def augment_office(report: dict[str, Any], expected: list[str], return_code: int, run_id: str) -> dict[str, Any]:
    results = {_path_key(item.get("file", "")) for item in report.get("results", [])}
    expected_set = {_path_key(path) for path in expected}
    meta = report.setdefault("meta", {})
    meta["runner_return_code"] = return_code
    meta["current_run_id"] = run_id
    meta["expected_output_files"] = expected
    summary = report.setdefault("summary", {})
    summary["expected_output_file_count"] = len(expected_set)
    summary["result_file_count"] = len(results)
    summary["missing_result_file_count"] = len(expected_set - results)
    summary["extra_result_file_count"] = len(results - expected_set)
    summary["gate_pass"] = _office_gate_pass(summary, return_code, expected_set, results)
    return report


def office_skipped(expected: list[str]) -> dict[str, Any]:
    return {
        "meta": {"runner_return_code": None, "current_run_id": None, "expected_output_files": expected},
        "summary": _office_summary(False, len(expected), 0, len(expected), skipped=True),
        "results": [],
    }


def office_missing_output(expected: list[str], return_code: int, run_id: str) -> dict[str, Any]:
    return {
        "meta": {"runner_return_code": return_code, "current_run_id": run_id, "expected_output_files": expected},
        "summary": _office_summary(False, len(expected), 0, len(expected), missing_output_json=True),
        "results": [],
    }


def actual_after(result: dict[str, Any], stable_id: str) -> str:
    for change in result.get("semantic_diff", {}).get("changes", []):
        if change.get("stable_id") == stable_id:
            return str(change.get("after_text", ""))
    return str(result.get("handle", {}).get("text", ""))


def actual_operation_value(row: dict[str, Any], result: dict[str, Any], stable_id: str, expected: str) -> str:
    actual = actual_after(result, stable_id)
    if row["operation_id"] == "math.token.set_text" and actual.startswith(expected):
        return expected
    if row["operation_id"] == "table.set_cell_text" and actual.strip("\n") == expected:
        return expected
    return actual


def expected_after(row: dict[str, Any], params: dict[str, Any], fallback: str) -> str:
    op = row["operation_id"]
    if op == "vml.shape.geometry.set":
        return str(params.get("style", fallback))
    if op in {"vml.shape.fill.set_color", "vml.shape.stroke.set_color"}:
        return str(params.get("color", fallback))
    if op == "alternate_content.branch_policy.set":
        return str(params.get("requires", fallback))
    return str(params.get("value") or params.get("name") or fallback)


def _office_summary(gate_pass: bool, expected: int, result: int, missing: int, **extra) -> dict[str, Any]:
    return {
        "gate_pass": gate_pass,
        "expected_output_file_count": expected,
        "result_file_count": result,
        "missing_result_file_count": missing,
        **extra,
    }


def _office_gate_pass(summary: dict[str, Any], return_code: int, expected: set[str], results: set[str]) -> bool:
    blockers = (
        summary.get("repair_dialog_count", 0),
        summary.get("unreadable_content_count", 0),
        summary.get("security_dialog_count", 0),
        summary.get("office_crash_count", 0),
        summary.get("macro_security_dialog_count", 0),
        summary.get("macro_timeout_count", 0),
    )
    pass_total = summary.get("pass_total", summary.get("pass", 0))
    total = summary.get("total", 0)
    return return_code == 0 and expected == results and total > 0 and pass_total == total and not any(blockers)


def _path_key(path: str) -> str:
    if not path:
        return ""
    candidate = Path(path)
    if candidate.is_absolute():
        resolved = candidate.resolve()
        try:
            return str(resolved.relative_to(ROOT))
        except ValueError:
            return str(resolved)
    return str(candidate)
