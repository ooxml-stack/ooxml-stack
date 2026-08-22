"""P90 anti-false-pass audit."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonl_artifacts import read_jsonl as _read_jsonl_artifact

ROOT = Path(__file__).resolve().parents[3]
STACK = ROOT / "ooxml-stack"
OUT = Path(__file__).resolve().parent
P80_FORMER_PRESERVE_ONLY = 296_144
MANDATORY_FIELDS = (
    "row_id", "format", "input_file", "package_id", "part_name",
    "stable_id", "stable_id_scope", "selector", "family",
    "semantic_model_id", "operation_id", "capability_tier",
    "understanding_level", "before_semantic_value",
    "requested_semantic_change", "after_semantic_value",
    "target_semantic_changed", "sibling_unexpected_semantic_mutation_count",
    "package_invariant_pass", "native_office_result", "public_api_path",
    "cli_path_checked", "mcp_path_checked", "llm_acceptance_task_ids",
)

def main() -> int:
    audit = build_audit()
    write_json(OUT / "anti-false-pass-audit.json", audit)
    return 0 if audit["gate_pass"] else 1


def build_audit(lock_status: dict[str, bool] | None = None) -> dict[str, Any]:
    lock_status = lock_status or {}
    p82 = read_json("release-evidence/p82/sh-semantic-denominator-summary.json")
    p90_rows = read_jsonl("release-evidence/p90/sh-semantic-editability-rows.jsonl")
    row_audit = audit_rows(p90_rows)
    office_audit = audit_office()
    mcp_audit = audit_mcp_protocol()
    p80_feasibility = read_json("release-evidence/p90/p80-semantic-promotion-feasibility.json")
    metrics = collect_metrics(p82, p90_rows, row_audit, office_audit, mcp_audit, p80_feasibility)
    metrics.update(lock_status)
    failures = failure_reasons(metrics)
    return {
        "schema_version": "p90-anti-false-pass-audit-v1",
        "gate_pass": not failures,
        "failures": failures,
        "metrics": metrics,
        "row_schema": row_audit,
        "office_freshness": office_audit,
        "mcp_protocol": mcp_audit,
    }

def audit_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    missing = {field: 0 for field in MANDATORY_FIELDS}
    stable_scopes: dict[str, int] = {}
    for row in rows:
        for field in MANDATORY_FIELDS:
            if field not in row:
                missing[field] += 1
        scope = row.get("stable_id_scope", "<missing>")
        stable_scopes[scope] = stable_scopes.get(scope, 0) + 1
    return {
        "row_count": len(rows),
        "missing_field_counts": {k: v for k, v in missing.items() if v},
        "stable_id_scope_counts": stable_scopes,
        "aggregate_replay_row_count": count_matching(rows, "aggregate"),
        "package_only_office_pass_row_count": count_package_only(rows),
        "marker_only_mutation_row_count": count_matching(rows, "marker"),
        "exact_after_value_oracle_fail_count": count_after_oracle_failures(rows),
        "cli_path_unchecked_count": count_unchecked(rows, "cli_path_checked"),
        "mcp_path_unchecked_count": count_unchecked(rows, "mcp_path_checked"),
    }


def audit_office() -> dict[str, Any]:
    cli = read_jsonl("release-evidence/p90/llm-acceptance/cli-results.jsonl")
    mcp = read_jsonl("release-evidence/p90/llm-acceptance/mcp-results.jsonl")
    office = read_json("release-evidence/p90/llm-acceptance/native-office-gate.json")
    p80_office = read_json("release-evidence/p90/p80-semantic-promotion-office.json")
    expected = {_path_key(row["output_file"]) for row in [*cli, *mcp] if row.get("output_file")}
    results = {_path_key(item.get("file", "")) for item in office.get("results", [])}
    summary = office.get("summary", {})
    p80_summary = p80_office.get("summary", {})
    p80_expected = {_path_key(row["output_file"]) for row in read_jsonl("release-evidence/p90/p80-semantic-promotion-rows.jsonl") if row.get("output_file")}
    p80_results = {_path_key(item.get("file", "")) for item in p80_office.get("results", [])}
    return {
        "office_expected_output_file_count": len(expected),
        "office_result_file_count": len(results),
        "office_missing_result_file_count": len(expected - results),
        "office_extra_result_file_count": len(results - expected),
        "office_runner_return_code": office.get("meta", {}).get("runner_return_code"),
        "office_timeout_seconds": office.get("meta", {}).get("timeout_seconds", 0),
        "office_dialog_wait_seconds": office.get("meta", {}).get("dialog_wait_seconds", 0),
        "p80_office_timeout_seconds": p80_office.get("meta", {}).get("timeout_seconds", 0),
        "p80_office_dialog_wait_seconds": p80_office.get("meta", {}).get("dialog_wait_seconds", 0),
        "p80_office_gate_pass": p80_summary.get("gate_pass") is True,
        "p80_office_blocker_count": sum(p80_summary.get(k, 0) for k in ("repair_dialog_count", "unreadable_content_count", "security_dialog_count", "office_crash_count", "macro_security_dialog_count", "macro_timeout_count")),
        "p80_office_unreadable_content_count": _unreadable_count(p80_office),
        "p80_office_expected_output_file_count": len(p80_expected),
        "p80_office_result_file_count": len(p80_results),
        "p80_office_missing_result_file_count": len(p80_expected - p80_results),
        "office_json_fresh": bool(office.get("meta", {}).get("current_run_id")),
        "security_dialog_count": summary.get("security_dialog_count", 0),
        "repair_dialog_count": summary.get("repair_dialog_count", 0),
        "unreadable_content_count": _unreadable_count(office),
        "crash_count": summary.get("office_crash_count", 0),
        "timeout_count": summary.get("macro_timeout_count", 0),
    }


def audit_mcp_protocol() -> dict[str, Any]:
    replay = stack_path("release-evidence/p90/run_llm_acceptance_replay.py")
    text = replay.read_text(encoding="utf-8") if replay.exists() else ""
    direct_calls = sum(text.count(name) for name in (
        "ooxml_open(", "ooxml_apply(", "ooxml_validate(",
        "ooxml_read(", "ooxml_enumerate(", "ooxml_semantic_handles(",
    ))
    verifier = read_json("release-evidence/p90/llm-acceptance/verifier-summary.json")
    rows = read_jsonl("release-evidence/p90/llm-acceptance/mcp-results.jsonl")
    protocol = [row.get("mcp_protocol", {}) for row in rows]
    real_mcp = bool(protocol) and all(item.get("real_mcp_protocol_replay_pass") is True for item in protocol)
    listed = bool(protocol) and all(item.get("mcp_list_tools_pass") is True for item in protocol)
    called = bool(protocol) and all(item.get("mcp_call_tool_replay_pass") is True for item in protocol)
    return {
        "real_mcp_protocol_replay_pass": verifier.get("real_mcp_protocol_replay_pass") is True or real_mcp,
        "mcp_list_tools_pass": verifier.get("mcp_list_tools_pass") is True or listed,
        "mcp_call_tool_replay_pass": verifier.get("mcp_call_tool_replay_pass") is True or called,
        "direct_mcp_function_call_count": direct_calls,
    }


def collect_metrics(p82, rows, row_audit, office, mcp, feasibility) -> dict[str, Any]:
    p80_rows = [row for row in rows if is_p80_row(row)]
    p80_semantic = [row for row in p80_rows if _semantic_pass(row)]
    metrics = {
        "p90_claim_denominator_matches_goal": False,
        "p90_claim_includes_locked_p80_population": False,
        "sh_object_count": p82.get("row_count", 0),
        "p90_object_row_count": len(rows),
        "p90_p80_former_preserve_only_rows": len(p80_rows),
        "p90_p80_semantic_promoted_count": len(p80_semantic),
        "p90_narrowed_denominator_smoke_count": len(rows),
        "p90_missing_mandatory_row_field_count": sum(row_audit["missing_field_counts"].values()),
        "p90_rows_with_snapshot_local_stable_id_count": row_audit["stable_id_scope_counts"].get("snapshot-local", 0),
        "p90_rows_with_package_only_office_pass_count": row_audit["package_only_office_pass_row_count"],
        "p90_rows_with_aggregate_replay_count": row_audit["aggregate_replay_row_count"],
        "p90_rows_with_marker_only_mutation_count": row_audit["marker_only_mutation_row_count"],
        "p90_exact_after_value_oracle_fail_count": row_audit["exact_after_value_oracle_fail_count"],
        "p90_cli_path_unchecked_count": row_audit["cli_path_unchecked_count"],
        "p90_mcp_path_unchecked_count": row_audit["mcp_path_unchecked_count"],
        "p80_former_preserve_only_baseline_count": p82.get("p80_joined_count", 0),
        "p80_surface_remaining_count": p82.get("surface_editable_count", 0),
        "p80_semantic_value_available_count": feasibility.get("semantic_value_available_count", 0),
        "p80_semantic_value_missing_count": feasibility.get("semantic_value_missing_count", 0),
        "p80_semantic_value_resolve_or_parse_failure_count": feasibility.get("resolve_or_parse_failure_count", 0),
        **office,
        **mcp,
    }
    metrics.update(_p90_metric_aliases(metrics))
    return metrics


def _p90_metric_aliases(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "p90_real_mcp_protocol_replay_pass": metrics.get("real_mcp_protocol_replay_pass"),
        "p90_mcp_list_tools_pass": metrics.get("mcp_list_tools_pass"),
        "p90_mcp_call_tool_replay_pass": metrics.get("mcp_call_tool_replay_pass"),
        "p90_direct_mcp_function_call_count": metrics.get("direct_mcp_function_call_count"),
        "p90_office_runner_return_code": metrics.get("office_runner_return_code"),
        "p90_office_timeout_seconds": metrics.get("office_timeout_seconds"),
        "p90_office_dialog_wait_seconds": metrics.get("office_dialog_wait_seconds"),
        "p90_p80_office_timeout_seconds": metrics.get("p80_office_timeout_seconds"),
        "p90_p80_office_dialog_wait_seconds": metrics.get("p80_office_dialog_wait_seconds"),
        "p90_p80_office_unreadable_content_count": metrics.get("p80_office_unreadable_content_count"),
        "p90_office_json_stale_artifact_count": 0 if metrics.get("office_json_fresh") is True else 1,
        "p90_office_expected_output_file_count": metrics.get("office_expected_output_file_count"),
        "p90_office_result_file_count": metrics.get("office_result_file_count"),
        "p90_office_missing_result_file_count": metrics.get("office_missing_result_file_count"),
        "p90_office_extra_result_file_count": metrics.get("office_extra_result_file_count"),
        "p90_native_office_security_dialog_count": metrics.get("security_dialog_count"),
        "p90_native_office_unreadable_content_count": metrics.get("unreadable_content_count"),
    }


def failure_reasons(metrics: dict[str, Any]) -> list[str]:
    checks = {
        "claim_denominator": metrics.get("p90_claim_denominator_matches_goal") is True,
        "locked_p80_claim": metrics.get("p90_claim_includes_locked_p80_population") is True,
        "row_count": metrics.get("p90_object_row_count") == metrics.get("sh_object_count"),
        "p80_rows": metrics.get("p90_p80_former_preserve_only_rows") == P80_FORMER_PRESERVE_ONLY,
        "p80_semantic": metrics.get("p90_p80_semantic_promoted_count") == P80_FORMER_PRESERVE_ONLY,
        "p80_semantic_values": metrics.get("p80_semantic_value_missing_count") == 0,
        "p80_semantic_value_resolution": metrics.get("p80_semantic_value_resolve_or_parse_failure_count") == 0,
        "mandatory_fields": metrics.get("p90_missing_mandatory_row_field_count") == 0,
        "after_value_oracle": metrics.get("p90_exact_after_value_oracle_fail_count") == 0,
        "cli_path_evidence": metrics.get("p90_cli_path_unchecked_count") == 0,
        "mcp_path_evidence": metrics.get("p90_mcp_path_unchecked_count") == 0,
        "real_mcp": metrics.get("p90_real_mcp_protocol_replay_pass") is True,
        "mcp_list_tools": metrics.get("p90_mcp_list_tools_pass") is True,
        "mcp_call_tool": metrics.get("p90_mcp_call_tool_replay_pass") is True,
        "no_direct_mcp_calls": metrics.get("p90_direct_mcp_function_call_count") == 0,
        "office_return_code": metrics.get("p90_office_runner_return_code") == 0,
        "office_timeout_budget": metrics.get("p90_office_timeout_seconds", 0) >= 180,
        "office_dialog_wait": metrics.get("p90_office_dialog_wait_seconds", 0) >= 30,
        "p80_office_timeout_budget": metrics.get("p90_p80_office_timeout_seconds", 0) >= 180,
        "p80_office_dialog_wait": metrics.get("p90_p80_office_dialog_wait_seconds", 0) >= 30,
        "p80_office_gate_pass": metrics.get("p80_office_gate_pass") is True,
        "p80_office_blockers": metrics.get("p80_office_blocker_count") == 0,
        "p80_office_file_set": metrics.get("p80_office_missing_result_file_count") == 0,
        "p80_office_exact_file_set": metrics.get("p80_office_result_file_count") == metrics.get("p80_office_expected_output_file_count"),
        "p80_office_nonempty_file_set": metrics.get("p80_office_expected_output_file_count", 0) > 0,
        "office_fresh_json": metrics.get("p90_office_json_stale_artifact_count") == 0,
        "office_file_set": metrics.get("p90_office_missing_result_file_count") == 0,
        "office_exact_file_set": metrics.get("p90_office_result_file_count") == metrics.get("p90_office_expected_output_file_count"),
        "office_nonempty_file_set": metrics.get("p90_office_expected_output_file_count", 0) > 0,
        "security_dialogs": metrics.get("p90_native_office_security_dialog_count") == 0,
        "unreadable_content": metrics.get("p90_native_office_unreadable_content_count") == 0,
        "p80_unreadable_content": metrics.get("p90_p80_office_unreadable_content_count") == 0,
        "audit_exists": metrics.get("p90_anti_false_pass_audit_exists") is True,
        "audit_manifest": metrics.get("p90_anti_false_pass_audit_in_manifest") is True,
        "audit_hash": metrics.get("p90_anti_false_pass_audit_hash_locked") is True,
    }
    return [name for name, passed in checks.items() if not passed]


def is_p80_row(row: dict[str, Any]) -> bool:
    return row.get("source_phase") == "p80"


def _semantic_pass(row: dict[str, Any]) -> bool:
    return row.get("capability_tier") == "semantic-active-editable" and row.get("pass") is True


def count_matching(rows: list[dict[str, Any]], needle: str) -> int:
    return sum(needle in str(row.get("operation_id", "")) for row in rows)


def count_package_only(rows: list[dict[str, Any]]) -> int:
    return sum(bool(row.get("office_gate_pass")) and not row.get("office_result_id") for row in rows)


def count_after_oracle_failures(rows: list[dict[str, Any]]) -> int:
    return sum(_after_oracle_failed(row) for row in rows)


def count_unchecked(rows: list[dict[str, Any]], key: str) -> int:
    return sum(row.get(key) is not True for row in rows)


def _unreadable_count(office: dict[str, Any]) -> int:
    summary = office.get("summary", {})
    rows = office.get("results", [])
    raw_rows = sum("unreadable" in json.dumps(row, ensure_ascii=False).lower() for row in rows)
    return max(summary.get("unreadable_content_count", 0), raw_rows)


def _after_oracle_failed(row: dict[str, Any]) -> bool:
    before = row.get("before_semantic_value")
    request = row.get("requested_semantic_change")
    after = row.get("after_semantic_value")
    if not isinstance(before, dict) or not isinstance(request, dict) or not isinstance(after, dict):
        return True
    if row.get("target_semantic_changed") is not True:
        return True
    return before.get("value") == after.get("value") or request.get("value") != after.get("value")


def read_json(rel: str) -> dict[str, Any]:
    path = stack_path(rel)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def read_jsonl(rel: str) -> list[dict[str, Any]]:
    return _read_jsonl_artifact(stack_path(rel))


def stack_path(rel: str) -> Path:
    return STACK / rel


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


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
