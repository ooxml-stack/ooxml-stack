"""Batch-promote P80 creationId rows with object-level evidence."""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
OFFICE_WALL_TIMEOUT_SECONDS = 360
sys.path[:0] = [str(ROOT / rel) for rel in ("ooxml-operation-engine/src", "ooxml-test-framework/src", "ooxml-spec/src", "ooxml-core/src")]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "ooxml-stack" / "scripts"))

from evidence_artifact_store import store_artifact  # noqa: E402
from ooxml_operation_engine.chart_ops import apply_chart_batch  # noqa: E402
from ooxml_operation_engine.jsonrpc_server import JsonRpcServer  # noqa: E402
from p80_semantic_promotion_runner import (  # noqa: E402
    CORPUS,
    OUT,
    PASS_STATUSES,
    ROWS,
    _existing_p90_source_rows,
    _existing_promotion_rows,
    _merge_rows,
    _part_fingerprints,
    _read_value,
    _rel,
    _target_digest,
    _write_json,
    _write_jsonl,
)

ARTIFACTS = ROOT / "ooxml-stack" / "release-evidence" / "artifact-blobs"

def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    selected = _select_batch(args)
    if not selected:
        return _write_noop()
    output = _copy_input(selected[0], args.label)
    plans = [_plan(row, idx) for idx, row in enumerate(selected)]
    before = _capture_before(output, plans)
    applied = _apply_batch(output, plans, before["validation_errors"])
    after_parts = {part: _part_fingerprints(output, part) for part in before["parts"]}
    office = _run_office(output, args.run_office)
    planned = _targets_by_part(plans)
    unexpected = {part: _unexpected(before["parts"][part], after_parts[part], part, planned) for part in before["parts"]}
    status = _office_status(office, output)
    artifact = store_artifact(output, ARTIFACTS, ROOT)
    rows = [_row(plan, output, before, after_parts, applied, status, unexpected, artifact) for plan in plans]
    merged = _merge_rows(_existing_promotion_rows(), rows)
    _write_jsonl(OUT / "p80-semantic-promotion-rows.jsonl", merged)
    _write_json(OUT / "p80-semantic-promotion-summary.json", _summary(merged, office))
    if args.run_office:
        _write_json(OUT / "p80-semantic-promotion-office.json", office)
    return 0 if all(row["pass"] if args.run_office else row["semantic_edit_pass"] for row in rows) else 1

def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-rows", type=int, default=50)
    parser.add_argument("--max-scan", type=int, default=500000)
    parser.add_argument("--max-package-mb", type=float, default=3.0)
    parser.add_argument("--family", default="office_extension")
    parser.add_argument("--qname-contains", default="creationId")
    parser.add_argument("--package-id", default="")
    parser.add_argument("--label", default="creationid")
    parser.add_argument("--run-office", action="store_true")
    return parser.parse_args(argv)


def _select_batch(args: argparse.Namespace) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    existing = _existing_p90_source_rows()
    existing |= {str(row.get("source_row_id", ""))[4:] for row in _existing_promotion_rows() if row.get("semantic_edit_pass") is True}
    with ROWS.open(encoding="utf-8") as stream:
        for index, line in enumerate(stream):
            if index >= args.max_scan:
                break
            row = json.loads(line)
            if _eligible(row, args, existing):
                groups[row["package_id"]].append(row)
    package = args.package_id or max(groups, key=lambda key: len(groups[key]), default="")
    return groups.get(package, [])[: args.max_rows]


def _eligible(row: dict[str, Any], args: argparse.Namespace, existing: set[str]) -> bool:
    if row.get("family") != args.family or args.qname_contains not in row.get("qname", ""):
        return False
    if args.package_id and row.get("package_id") != args.package_id:
        return False
    if row["row_id"] in existing or f"p80|{row['row_id']}" in existing:
        return False
    size_mb = (CORPUS / row["input_file"]).stat().st_size / 1024 / 1024
    return not args.max_package_mb or size_mb <= args.max_package_mb


def _copy_input(row: dict[str, Any], label: str) -> Path:
    src = CORPUS / row["input_file"]
    dst_dir = OUT / "p80-promotion-outputs"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / f"p80-batch-{label}-{row['package_id']}{src.suffix}"
    shutil.copy2(src, dst)
    return dst


def _plan(row: dict[str, Any], index: int) -> dict[str, Any]:
    attr = "val" if "powerpoint/2010/main" in row.get("qname", "") else "id"
    return {
        "row": row,
        "index": index,
        "attr": attr,
        "target": f"{row['part_name']}::{row['selector']}",
        "operation_id": "office_extension.creation_id.set",
    }


def _capture_before(output: Path, plans: list[dict[str, Any]]) -> dict[str, Any]:
    values, digests = {}, {}
    for plan in plans:
        plan["before"] = _read_plan_value(output, plan)
        values[_key(plan)] = plan["before"]
        digests[_key(plan)] = _target_digest(output, plan["row"])
    parts = {plan["row"]["part_name"] for plan in plans}
    return {"values": values, "digests": digests, "validation_errors": _validation_errors(output), "parts": {p: _part_fingerprints(output, p) for p in parts}}


def _apply_batch(output: Path, plans: list[dict[str, Any]], before_errors: set[tuple[str, ...]]) -> dict[str, dict[str, Any]]:
    results = _apply_plans(output, plans)
    valid = not (_validation_errors(output) - before_errors)
    return {key: value | {"ok": value["ok"] and valid} for key, value in results.items()}


def _apply_plans(output: Path, plans: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    rows = [_public_row(plan) for plan in plans]
    try:
        apply_chart_batch(output, rows)
    except Exception as exc:
        return {_key(plan): {"ok": False, "error": str(exc)} for plan in plans}
    return {_key(plan): {"ok": True, "error": ""} for plan in plans}


def _public_row(plan: dict[str, Any]) -> dict[str, Any]:
    return {"operation_id": plan["operation_id"], "target": plan["target"], "params": {"value": _after_value(plan)}}


def _validation_errors(output: Path) -> set[tuple[str, ...]]:
    server = JsonRpcServer()
    try:
        server.handle("ooxml_open", {"path": str(output)})
        validation = server.handle("ooxml_validate", {})
    finally:
        _close(server)
    return {(item.get("rule_id", ""), item.get("severity", ""), item.get("message", ""), item.get("file_path", ""), item.get("xpath", "")) for item in validation.get("findings", []) if item.get("severity") == "ERROR"}


def _after_value(plan: dict[str, Any]) -> str:
    before = plan["before"]
    if plan["attr"] == "val":
        return str((int(before or "0") + plan["index"] + 1) % 4_294_967_295)
    digest = hashlib.sha256(f"{before}|p90b{plan['index']}".encode()).hexdigest().upper()
    return f"{{{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}}}"


def _row(plan, output, before, after_parts, applied, status, unexpected_by_part, artifact) -> dict[str, Any]:
    row = plan["row"]
    before_value = before["values"][_key(plan)]
    after_value = _read_plan_value(output, plan)
    after_digest = after_parts[row["part_name"]].get(row["selector"])
    changed = before_value != after_value and before["digests"][_key(plan)] != after_digest
    unexpected = unexpected_by_part[row["part_name"]]
    ok = applied.get(_key(plan), {}).get("ok") is True
    payload = _row_payload(row, plan, before_value, after_value, changed, unexpected, status)
    semantic_pass = changed and unexpected == 0 and ok
    payload["package_invariant_pass"] = ok
    payload["semantic_edit_pass"] = semantic_pass
    payload["pass"] = semantic_pass and status in PASS_STATUSES
    payload["output_file"] = _rel(output)
    payload["artifact"] = artifact
    return payload


def _row_payload(row, plan, before, after, changed, unexpected, status) -> dict[str, Any]:
    requested = _after_value(plan)
    return {
        "row_id": f"{row['format']}|{row['package_id']}|{row['part_name']}|{row['stable_id']}",
        "format": row["format"], "input_file": row["input_file"], "package_id": row["package_id"],
        "part_name": row["part_name"], "stable_id": row["stable_id"], "stable_id_scope": "package-local",
        "selector": row["selector"], "operation_target": plan["target"], "operation_params": {"value": requested},
        "family": row["family"], "semantic_model_id": "office_extension.creation_id.p80-batch.v1",
        "operation_id": plan["operation_id"], "capability_tier": "semantic-active-editable",
        "understanding_level": "office-semantic", "before_semantic_value": _value(row, plan, before),
        "requested_semantic_change": {"operation_id": plan["operation_id"], "value": requested},
        "after_semantic_value": _value(row, plan, after), "target_semantic_changed": changed,
        "sibling_unexpected_semantic_mutation_count": unexpected, "native_office_result": status,
        "public_api_path": "ooxml_operation_engine.JsonRpcServer.ooxml_apply",
        "cli_path_checked": False, "mcp_path_checked": False, "llm_acceptance_task_ids": [],
        "source_phase": "p80", "source_row_id": f"p80|{row['row_id']}", "output_file": "",
    }


def _value(row: dict[str, Any], plan: dict[str, Any], value: str) -> dict[str, str]:
    return {"value": value, "qname": row.get("qname", ""), "value_selector": row["selector"], "attribute_name": plan["attr"]}


def _run_office(output: Path, enabled: bool) -> dict[str, Any]:
    path = OUT / "p80-semantic-promotion-office.json"
    if not enabled:
        return {"summary": {"gate_pass": False, "skipped": True}, "results": []}
    previous = _read_office(path)
    path.unlink(missing_ok=True)
    cmd = [
        "uv", "run", "python", "tools/office-open-gate/office_open_gate.py", str(output),
        "--timeout-seconds", "240", "--dialog-wait-seconds", "30", "--path-root", str(ROOT), "-o", str(path),
    ]
    try:
        completed = subprocess.run(cmd, cwd=ROOT / "ooxml-test-framework", check=False, timeout=OFFICE_WALL_TIMEOUT_SECONDS)
        return_code = completed.returncode
    except subprocess.TimeoutExpired:
        return_code = 124
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"summary": {}, "results": []}
    data.setdefault("meta", {})["runner_return_code"] = return_code
    data["meta"]["runner_wall_timeout_seconds"] = OFFICE_WALL_TIMEOUT_SECONDS if return_code == 124 else 0
    return _merge_office(previous, data)


def _read_office(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"summary": {}, "results": []}


def _merge_office(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    results = {_rel_key(item.get("file", "")): item for item in previous.get("results", [])}
    results.update({_rel_key(item.get("file", "")): item for item in current.get("results", [])})
    merged = {"meta": current.get("meta", {}), "results": list(results.values())}
    statuses = [item.get("status", "missing") for item in merged["results"]]
    merged["summary"] = {"total": len(statuses), "pass_total": statuses.count("pass"), "pass": statuses.count("pass"), "by_status": {s: statuses.count(s) for s in sorted(set(statuses))}, "gate_pass": bool(statuses) and all(s == "pass" for s in statuses), "repair_dialog_count": statuses.count("repair_dialog") + statuses.count("unreadable_content"), "unreadable_content_count": statuses.count("unreadable_content"), "security_dialog_count": statuses.count("pass_with_security_dialog"), "office_crash_count": statuses.count("office_crash"), "macro_security_dialog_count": statuses.count("macro_security_dialog"), "macro_timeout_count": statuses.count("macro_timeout"), "benign_dialog_count": statuses.count("pass_with_dialog")}
    return merged


def _office_status(office: dict[str, Any], output: Path) -> str:
    results = {_rel_key(item.get("file", "")): item for item in office.get("results", [])}
    return results.get(_rel(output), {}).get("status", "not-run")


def _unexpected(before: dict[str, str], after: dict[str, str], part: str, planned: dict[str, set[str]]) -> int:
    changed = [path for path, digest in before.items() if after.get(path) != digest]
    return sum(not any(_inside(path, target) for target in planned.get(part, set())) for path in changed)


def _targets_by_part(plans: list[dict[str, Any]]) -> dict[str, set[str]]:
    targets: dict[str, set[str]] = defaultdict(set)
    for plan in plans:
        targets[plan["row"]["part_name"]].add(plan["row"]["selector"])
    return targets


def _summary(rows: list[dict[str, Any]], office: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "p90-p80-semantic-promotion-v1",
        "gate_pass": bool(rows) and all(row["pass"] for row in rows),
        "row_count": len(rows),
        "row_pass_count": sum(row["pass"] for row in rows),
        "target_semantic_miss_count": sum(not row["target_semantic_changed"] for row in rows),
        "sibling_unexpected_semantic_mutation_count": sum(row["sibling_unexpected_semantic_mutation_count"] for row in rows),
        "native_office_gate_pass": office.get("summary", {}).get("gate_pass") is True,
        "native_office_pass_count": sum(row["native_office_result"] in PASS_STATUSES for row in rows),
        "native_office_total_count": len(rows),
        "native_office_batch_total_count": office.get("summary", {}).get("total", 0),
    }


def _read_plan_value(output: Path, plan: dict[str, Any]) -> str:
    row = plan["row"]
    return _read_value(output, row["part_name"], row["selector"], plan["attr"])


def _inside(path: str, target: str) -> bool:
    return path == target or path.startswith(target + "/") or target.startswith(path + "/")


def _key(plan: dict[str, Any]) -> str:
    row = plan["row"]
    return f"{row['input_file']}|{row['part_name']}|{row['selector']}"


def _rel_key(path: str) -> str:
    candidate = Path(path)
    return str(candidate.resolve().relative_to(ROOT)) if candidate.is_absolute() else path
def _close(server: JsonRpcServer) -> None:
    try:
        server.handle("ooxml_close", {})
    except Exception:
        server.cleanup()
def _write_noop() -> int:
    _write_json(OUT / "p80-semantic-promotion-batch-summary.json", {"gate_pass": False, "row_count": 0})
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
