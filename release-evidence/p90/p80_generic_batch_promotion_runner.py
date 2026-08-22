"""Batch-promote generic P80 rows with object-level semantic evidence."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
for rel in ("ooxml-operation-engine/src", "ooxml-test-framework/src", "ooxml-spec/src", "ooxml-core/src"):
    sys.path.insert(0, str(ROOT / rel))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "ooxml-stack" / "scripts"))

from evidence_artifact_store import store_artifact  # noqa: E402
from ooxml_operation_engine.jsonrpc_server import JsonRpcServer  # noqa: E402
from ooxml_operation_engine.chart_ops import apply_chart_batch, is_chart_operation  # noqa: E402
from ooxml_operation_engine.structural_ops import apply_structural_batch, is_structural_operation  # noqa: E402
from p80_semantic_promotion_runner import (  # noqa: E402
    CORPUS,
    OUT,
    ROWS,
    _after_value,
    _existing_promotion_rows,
    _merge_rows,
    _params as _base_params,
    _part_fingerprints,
    _plan,
    _read_value,
    _rel,
    _target_digest,
    _understanding,
    _write_json,
    _write_jsonl,
)
from p80_extra_plans import extra_params, extra_plan, extra_request_value  # noqa: E402

ARTIFACTS = ROOT / "ooxml-stack" / "release-evidence" / "artifact-blobs"

def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    selected = _select_rows(args)
    plans = _planned(selected)
    if not plans:
        return _write_noop()
    output = _copy_input(plans[0]["row"], args.label)
    before = _before(output, plans)
    applied = _apply_batch(output, plans, before["validation_errors"])
    planned_targets = _targets_by_part(plans)
    after_parts = {part: _part_fingerprints(output, part) for part in before["parts"]}
    artifact = store_artifact(output, ARTIFACTS, ROOT)
    rows = [_result_row(plan, output, before, applied, planned_targets, after_parts, artifact) for plan in plans]
    merged = _merge_rows(_existing_promotion_rows(), rows)
    _write_jsonl(OUT / "p80-semantic-promotion-rows.jsonl", merged)
    _write_json(OUT / "p80-semantic-promotion-summary.json", _summary(merged))
    return 0 if all(row["semantic_edit_pass"] for row in rows) else 1


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-rows", type=int, default=500)
    parser.add_argument("--max-scan", type=int, default=500000)
    parser.add_argument("--max-package-mb", type=float, default=15.0)
    parser.add_argument("--family", default="office_extension")
    parser.add_argument("--qname-contains", nargs="*", default=())
    parser.add_argument("--package-id", default="")
    parser.add_argument("--label", default="generic")
    return parser.parse_args(argv)


def _select_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    existing = _existing_source_ids()
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
    if row.get("family") != args.family or row.get("row_id") in existing:
        return False
    if args.qname_contains and not any(token in row.get("qname", "") for token in args.qname_contains):
        return False
    if args.package_id and row.get("package_id") != args.package_id:
        return False
    size_mb = (CORPUS / row["input_file"]).stat().st_size / 1024 / 1024
    return not args.max_package_mb or size_mb <= args.max_package_mb


def _planned(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    planned, seen = [], set()
    for index, row in enumerate(rows):
        plan = _plan(row) or extra_plan(row)
        key = (row["part_name"], plan["value_selector"], plan.get("attribute_name")) if plan else None
        if plan is not None and key not in seen:
            planned.append({"index": index, "row": row, "plan": plan})
            seen.add(key)
    return planned


def _before(output: Path, plans: list[dict[str, Any]]) -> dict[str, Any]:
    values, digests = {}, {}
    for item in plans:
        values[_key(item)] = _value(output, item)
        digests[_key(item)] = _target_digest(output, item["row"])
    parts = {item["row"]["part_name"] for item in plans}
    return {"values": values, "digests": digests, "parts": {p: _part_fingerprints(output, p) for p in parts}, "validation_errors": _validation_errors(output)}


def _apply_batch(output: Path, plans: list[dict[str, Any]], before_errors: set[tuple[str, ...]]) -> dict[str, Any]:
    errors = []
    if _chart_batch(plans):
        try:
            apply_chart_batch(output, [_payload(item) for item in plans])
        except Exception as exc:  # noqa: BLE001
            errors.append(f"direct-batch:{exc}")
        return {"errors": errors, "new_validation_errors": sorted(_validation_errors(output) - before_errors)}
    if _structural_batch(plans):
        try:
            apply_structural_batch(output, [_payload(item) for item in plans])
        except Exception as exc:  # noqa: BLE001
            errors.append(f"direct-batch:{exc}")
        return {"errors": errors, "new_validation_errors": sorted(_validation_errors(output) - before_errors)}
    server = JsonRpcServer()
    server.handle("ooxml_open", {"path": str(output)})
    try:
        for item in plans:
            try:
                server.handle("ooxml_apply", _payload(item))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{_key(item)}:{exc}")
        validation = server.handle("ooxml_validate", {})
        server.handle("ooxml_save", {})
    finally:
        _close(server)
    return {"errors": errors, "new_validation_errors": sorted(_error_set(validation) - before_errors)}


def _chart_batch(plans: list[dict[str, Any]]) -> bool:
    return bool(plans) and all(is_chart_operation(item["plan"]["operation_id"]) for item in plans)


def _structural_batch(plans: list[dict[str, Any]]) -> bool:
    return bool(plans) and all(is_structural_operation(item["plan"]["operation_id"]) for item in plans)


def _result_row(item: dict[str, Any], output: Path, before: dict[str, Any], applied: dict[str, Any], targets, after_parts, artifact) -> dict[str, Any]:
    row, plan = item["row"], item["plan"]
    before_value, after_value = before["values"][_key(item)], _value(output, item)
    requested = _request_value(before_value, plan, item["index"])
    changed = before_value != after_value and before["digests"][_key(item)] != _target_digest(output, row)
    outside = _outside(before["parts"][row["part_name"]], after_parts[row["part_name"]], targets[row["part_name"]])
    semantic_pass = changed and after_value == requested and outside == 0 and not applied["errors"] and not applied["new_validation_errors"]
    payload = _row_payload(item, output, before_value, after_value, outside, semantic_pass)
    payload["artifact"] = artifact
    return payload


def _row_payload(item, output, before, after, outside, semantic_pass) -> dict[str, Any]:
    row, plan = item["row"], item["plan"]
    requested = _request_value(before, plan, item["index"])
    return {
        "row_id": f"{row['format']}|{row['package_id']}|{row['part_name']}|{row['stable_id']}",
        "format": row["format"], "input_file": row["input_file"], "package_id": row["package_id"],
        "part_name": row["part_name"], "stable_id": row["stable_id"], "stable_id_scope": "package-local",
        "selector": row["selector"], "operation_target": plan["target"], "operation_params": _params(plan, requested),
        "family": row["family"], "semantic_model_id": f"{row['family']}.p80-generic-batch.v1",
        "operation_id": plan["operation_id"], "capability_tier": "semantic-active-editable",
        "understanding_level": _understanding(row["family"]), "before_semantic_value": _semantic(row, plan, before),
        "requested_semantic_change": {"operation_id": plan["operation_id"], "value": requested},
        "after_semantic_value": _semantic(row, plan, after), "target_semantic_changed": before != after,
        "sibling_unexpected_semantic_mutation_count": outside, "package_invariant_pass": semantic_pass,
        "semantic_edit_pass": semantic_pass, "native_office_result": "not-run", "public_api_path": "ooxml_operation_engine.JsonRpcServer.ooxml_apply",
        "cli_path_checked": False, "mcp_path_checked": False, "llm_acceptance_task_ids": [],
        "source_phase": "p80", "source_row_id": f"p80|{row['row_id']}", "output_file": _rel(output), "pass": False,
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "p90-p80-semantic-promotion-v1", "gate_pass": bool(rows) and all(row.get("pass") for row in rows),
        "row_count": len(rows), "row_pass_count": sum(row.get("pass") is True for row in rows),
        "semantic_edit_pass_count": sum(row.get("semantic_edit_pass") is True for row in rows),
        "native_office_pass_count": sum(row.get("native_office_result") == "pass" for row in rows),
        "pending_native_office_count": sum(row.get("native_office_result") == "not-run" for row in rows),
        "by_family": dict(Counter(row.get("family", "") for row in rows)),
    }


def _copy_input(row: dict[str, Any], label: str) -> Path:
    src = CORPUS / row["input_file"]
    dst = OUT / "p80-promotion-outputs" / f"p80-batch-{label}-{row['package_id']}{src.suffix}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return dst


def _payload(item: dict[str, Any]) -> dict[str, Any]:
    plan = item["plan"]
    return {"operation_id": plan["operation_id"], "target": plan["target"], "params": _params(plan, _request_value(item["before_value"], plan, item["index"]))}


def _request_value(before: str, plan: dict[str, Any], index: int) -> str:
    extra = extra_request_value(before, plan, index)
    if extra is not None:
        return extra
    selector = plan.get("value_selector", "")
    if any(token in selector for token in ("useLocalDpi", "wrappingTextBoxFlag")) and before.lower() in {"", "0", "1", "false", "true"}:
        return "0" if before.lower() in {"1", "true"} else "1"
    if before.isdigit() and "srgbClr" not in selector:
        return str(int(before) + index + 1)
    return _after_value(before, index, plan)


def _params(plan: dict[str, Any], value: str) -> dict[str, str]:
    return extra_params(plan, value) or _base_params(plan, value)


def _value(output: Path, item: dict[str, Any]) -> str:
    plan = item["plan"]
    value = _read_value(output, item["row"]["part_name"], plan["value_selector"], plan.get("attribute_name"))
    item.setdefault("before_value", value)
    return value


def _semantic(row: dict[str, Any], plan: dict[str, Any], value: str) -> dict[str, str]:
    payload = {"value": value, "qname": row.get("qname", ""), "value_selector": plan["value_selector"]}
    if plan.get("attribute_name"):
        payload["attribute_name"] = plan["attribute_name"]
    return payload


def _outside(before: dict[str, str], after: dict[str, str], targets: set[str]) -> int:
    return sum(after.get(path) != digest and not any(_inside(path, target) for target in targets) for path, digest in before.items())


def _targets_by_part(plans: list[dict[str, Any]]) -> dict[str, set[str]]:
    targets: dict[str, set[str]] = defaultdict(set)
    for item in plans:
        row, plan = item["row"], item["plan"]
        targets[row["part_name"]].update({row["selector"], plan["value_selector"]})
    return targets


def _validation_errors(output: Path) -> set[tuple[str, ...]]:
    server = JsonRpcServer()
    try:
        server.handle("ooxml_open", {"path": str(output)})
        return _error_set(server.handle("ooxml_validate", {}))
    finally:
        _close(server)


def _error_set(validation: dict[str, Any]) -> set[tuple[str, ...]]:
    return {(i.get("rule_id", ""), i.get("severity", ""), i.get("message", ""), i.get("file_path", ""), i.get("xpath", "")) for i in validation.get("findings", []) if i.get("severity") == "ERROR"}


def _existing_source_ids() -> set[str]:
    ids = set()
    for row in _existing_promotion_rows():
        if row.get("pass") is not True and row.get("semantic_edit_pass") is not True:
            continue
        source = str(row.get("source_row_id", ""))
        ids.add(source[4:] if source.startswith("p80|") else source)
    return ids


def _inside(path: str, target: str) -> bool:
    return path == target or path.startswith(target + "/") or target.startswith(path + "/")


def _key(item: dict[str, Any]) -> str:
    row = item["row"]
    return f"{row['input_file']}|{row['part_name']}|{row['selector']}"


def _close(server: JsonRpcServer) -> None:
    try:
        server.handle("ooxml_close", {})
    except Exception:
        server.cleanup()


def _write_noop() -> int:
    _write_json(OUT / "p80-semantic-promotion-generic-batch-summary.json", {"gate_pass": False, "row_count": 0})
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
