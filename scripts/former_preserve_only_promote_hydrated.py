from __future__ import annotations
import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from former_preserve_only_cover_page import promotion_allowed as cover_page_promotion_allowed
from former_preserve_only_office_boundaries import failed_office_packages
from former_preserve_only_numeric_leaf import NUMERIC_LEAF_OPS
from former_preserve_only_ole import OPERATION as OLE_LOCKED_FIELD_OP, promotion_allowed as ole_promotion_allowed
from former_preserve_only_p14_presence import PRESENCE_OPS as P14_PRESENCE_OPS
from former_preserve_only_picture_effect_presence import PICTURE_EFFECT_PRESENCE_OPS
from former_preserve_only_vml_stroke import BOOLEAN_OPS as VML_BOOLEAN_OPS, OPERATION as VML_STROKE_OP, OPERATIONS as VML_OPS, promotion_allowed as vml_stroke_promotion_allowed
from former_preserve_only_promote_batch import (
    CORPUS,
    ENGINE,
    PROJECTS,
    PUBLIC,
    ROWS,
    SUMMARY,
    _copy,
    _done,
    _errors,
    _fingerprints,
    _mark,
    _merge,
    _outside,
    _process_meta,
    _read_jsonl,
    _run_office,
    _tree,
    _write_json,
    _write_jsonl,
)
from former_preserve_only_promoted_index import alias_operation_count_from_rows, deduped_operation_count, promoted_index, row_target_key
from former_preserve_only_math_policy import MATH_PRESENCE_OPS, math_metadata_allowed
from former_preserve_only_value_policy import checked_requested_value, next_requested_value
from ooxml_operation_engine.jsonrpc_server import JsonRpcServer
from vml_text_value import visible_vml_text
OUT = Path(__file__).resolve().parents[1] / "release-evidence/former-preserve-only-semantic-editability"
HYDRATED = OUT / "operation-hydration-ledger.jsonl"
ANCHORLOCK_PRESENCE_OP = "legacy_office_drawing.anchorlock.presence.set_enabled"
NO_FILL_PRESENCE_OP = "office_extension.no_fill.presence.set_enabled"
BEVEL_PRESENCE_OP = "office_extension.text_outline.bevel.presence.set_enabled"
CONTEXTUAL_ALTERNATES_PRESENCE_OP = "office_extension.contextual_alternates.presence.set_enabled"
DELETE_ONLY_PRESENCE_OPS = {ANCHORLOCK_PRESENCE_OP, NO_FILL_PRESENCE_OP, BEVEL_PRESENCE_OP, CONTEXTUAL_ALTERNATES_PRESENCE_OP} | set(P14_PRESENCE_OPS.values()) | set(PICTURE_EFFECT_PRESENCE_OPS.values()) | set(MATH_PRESENCE_OPS.values())
def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv); phase = _mark(f"select hydrated rows label={args.label}")
    plans = _plans(_select_rows(args), args)
    _done(f"select hydrated rows planned={len(plans)}", phase)
    if args.dry_run:
        print(json.dumps({"planned": len(plans), "skipped_schema_policy_rows": getattr(args, "skipped_policy_rows", 0), "rows": [_brief(p) for p in plans]}, indent=2, sort_keys=True))
        return 0
    if not plans:
        return 1
    api_path = _copy(plans[0]["row"], f"api-{args.label}")
    api, cli, mcp = _run_all(api_path, plans, args.label)
    phase = _mark("office gate")
    office = _run_office(api_path, args.run_office)
    _done(f"office gate status={office['status']}", phase)
    rows = [_evidence_row(item, api_path, api, cli, mcp, office) for item in plans]
    if not rows or not all(row["pass"] for row in rows):
        print(json.dumps(_summary(rows, len(rows), args.label), indent=2, sort_keys=True))
        return 1
    merged = _merge(_read_jsonl(ROWS), rows)
    _write_jsonl(ROWS, merged)
    _write_json(SUMMARY, _summary(merged, len(rows), args.label))
    print(json.dumps(_summary(rows, len(rows), args.label), indent=2, sort_keys=True))
    return 0 if rows and all(row["pass"] for row in rows) else 1
def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--max-rows", type=int, default=20)
    p.add_argument("--family", default="")
    p.add_argument("--operation-id", default="")
    p.add_argument("--package-id", default="")
    p.add_argument("--qname", default="")
    p.add_argument("--attribute-name", default="")
    p.add_argument("--max-package-mb", type=float, default=5.0)
    p.add_argument("--label", default="hydrated")
    p.add_argument("--requested-value", default="")
    p.add_argument("--run-office", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args(argv)
def _select_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    promoted, promoted_targets = promoted_index(ROWS)
    failed = failed_office_packages(OUT / "office-results") if not args.package_id else set()
    rows = []
    for row in _read_jsonl(HYDRATED):
        if row.get("package_id") not in failed and _eligible(row, args, promoted, promoted_targets):
            rows.append(row)
    rows.sort(key=lambda row: (_size_mb(row), row["package_id"], row["row_id"]))
    if args.package_id:
        return [row for row in rows if row["package_id"] == args.package_id]
    return rows
def _eligible(row: dict[str, Any], args: argparse.Namespace, promoted: set[str], promoted_targets: set[tuple[str, str, str, str]]) -> bool:
    blocked_part = row.get("part_name", "").startswith(("customXml/", "docMetadata/")) and not cover_page_promotion_allowed(row)
    blocked_ole = row.get("operation_id") == OLE_LOCKED_FIELD_OP and not ole_promotion_allowed(row); blocked_vml_stroke = row.get("operation_id") in VML_OPS and not vml_stroke_promotion_allowed(row)
    if row.get("operation_hydration_status") != "hydrated" or row.get("source_row_id") in promoted or row_target_key(row) in promoted_targets or blocked_part or blocked_ole or blocked_vml_stroke:
        return False
    if args.family and row.get("family") != args.family:
        return False
    if args.operation_id and row.get("operation_id") != args.operation_id:
        return False
    if args.package_id and row.get("package_id") != args.package_id:
        return False
    if getattr(args, "qname", "") and row.get("qname") != args.qname:
        return False
    if getattr(args, "attribute_name", "") and row.get("attribute_name") != args.attribute_name:
        return False
    return _size_mb(row) <= args.max_package_mb
def _plans(rows: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    plans, seen = [], set()
    package = args.package_id
    args.skipped_policy_rows = 0
    for index, row in enumerate(rows):
        if package and row["package_id"] != package:
            continue
        unstable_math = not math_metadata_allowed(row)
        unsafe_text = row.get("operation_id") == "math.run.set_text" and not _is_math_run_target(row)
        if unstable_math or unsafe_text:
            args.skipped_policy_rows += 1
            continue
        key = (row["part_name"], row["operation_target_selector"])
        if key in seen or _overlaps(key, seen):
            continue
        before = _read_value(CORPUS / row["input_file"], row)
        try:
            requested = args.requested_value or row.get("requested_semantic_value") or next_requested_value(before, index, row)
            requested = checked_requested_value(before, requested, row)
        except ValueError as exc:
            if str(exc).startswith("schema_policy_unsafe_"):
                args.skipped_policy_rows += 1
                continue
            raise
        package = package or row["package_id"]
        if requested == before:
            continue
        plans.append({"row": row, "before": before, "requested": requested})
        seen.add(key)
        if len(plans) >= args.max_rows:
            break
    return plans
def _is_math_run_target(row: dict[str, Any]) -> bool:
    tail = str(row.get("operation_target_selector", "")).rsplit("/", 1)[-1]
    return tail == "m:r" or tail.startswith("m:r[") and tail.endswith("]")
def _overlaps(key: tuple[str, str], seen: set[tuple[str, str]]) -> bool:
    part, selector = key
    return any(part == old_part and (selector.startswith(old + "/") or old.startswith(selector + "/")) for old_part, old in seen)
def _run_all(path: Path, plans: list[dict[str, Any]], label: str) -> tuple[dict, dict, dict]:
    phase = _mark("api replay")
    api = _run_api(path, plans)
    _done("api replay", phase)
    phase = _mark("cli replay")
    cli = _run_cli(plans, label)
    _done("cli replay", phase)
    phase = _mark("mcp replay")
    mcp = anyio.run(_run_mcp, plans, label)
    _done("mcp replay", phase)
    return api, cli, mcp
def _run_api(path: Path, plans: list[dict[str, Any]]) -> dict[str, Any]:
    before, errors = _snapshot(path, plans), []
    server = JsonRpcServer()
    try:
        server.handle("ooxml_open", {"path": str(path)})
        baseline = _errors(server.handle("ooxml_validate", {}))
        for item in plans:
            server.handle("ooxml_apply", _payload(item))
        validation = server.handle("ooxml_validate", {})
        server.handle("ooxml_save", {})
    except Exception as exc:  # noqa: BLE001
        errors.append(f"{type(exc).__name__}: {exc}")
        validation, baseline = {}, set()
    finally:
        server.cleanup()
    return _check_path(path, plans, before) | {"errors": errors, "new_errors": sorted(_errors(validation) - baseline)}
def _run_cli(plans: list[dict[str, Any]], label: str) -> dict[str, Any]:
    path = _copy(plans[0]["row"], f"cli-{label}")
    plan_path = PUBLIC / f"cli-{label}.jsonl"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text("".join(json.dumps(_payload(item), sort_keys=True) + "\n" for item in plans))
    before = _snapshot(path, plans)
    cmd = ["uv", "run", "ooxml-engine", "apply", str(path), "--plan-jsonl", str(plan_path), "--save"]
    done = subprocess.run(cmd, cwd=ENGINE, capture_output=True, text=True, check=False)
    return _check_path(path, plans, before) | _process_meta(done)
async def _run_mcp(plans: list[dict[str, Any]], label: str) -> dict[str, Any]:
    path = _copy(plans[0]["row"], f"mcp-{label}")
    before = _snapshot(path, plans)
    params = StdioServerParameters(command=sys.executable, args=["-m", "ooxml_operation_engine.mcp_server"], cwd=str(ENGINE))
    tools, code, error = None, 1, ""
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                code, error = await _mcp_apply(session, path, plans)
    except Exception as exc:  # noqa: BLE001
        tools, code, error = None, 1, str(exc)
    return _check_path(path, plans, before) | {"return_code": code, "stderr": error, "list_tools_pass": bool(getattr(tools, "tools", []))}
async def _mcp_apply(session: ClientSession, path: Path, plans: list[dict[str, Any]]) -> tuple[int, str]:
    try:
        await _call(session, "ooxml_open", {"path": str(path)})
        await _call(session, "ooxml_apply", {"plan": [_payload(item) for item in plans]})
        await _call(session, "ooxml_validate", {})
        await _call(session, "ooxml_save", {})
        return 0, ""
    except Exception as exc:  # noqa: BLE001
        return 1, str(exc)
    finally:
        try:
            await _call(session, "ooxml_close", {})
        except Exception:
            pass
async def _call(session: ClientSession, name: str, arguments: dict[str, Any]) -> None:
    result = await session.call_tool(name, arguments)
    if result.isError:
        raise RuntimeError(f"{name} failed: {result.content}")
def _payload(item: dict[str, Any]) -> dict[str, Any]:
    row, value = item["row"], item["requested"]
    if row["operation_id"] in DELETE_ONLY_PRESENCE_OPS:
        if value != "false":
            raise ValueError("presence operation only supports false")
        return {"operation_id": row["operation_id"], "target": f"{row['part_name']}::{row['operation_target_selector']}", "params": {"enabled": False}}
    params = {"value": value}
    if row.get("attribute_name") and row["operation_id"] not in {"vml.formula.eqn.set_value", "office_extension.media_trim.set_end"}:
        params["attribute_name"] = row["attribute_name"]
    if row.get("value_kind") == "text" and row["operation_id"] not in NUMERIC_LEAF_OPS:
        params = {"text": value}
    if row["operation_id"] == OLE_LOCKED_FIELD_OP: params = {"enabled": value == "true"}
    if row["operation_id"] == VML_STROKE_OP: params = {"join_style": value}
    if row["operation_id"] in {*VML_BOOLEAN_OPS.values(), "vml.shadow.set_enabled", "vml.textpath.set_enabled"}: params = {"enabled": value in {"t", "true", "1"}}
    if row["operation_id"] in {"vml.shape.fill.set_color", "vml.shape.stroke.set_color"}:
        params = {"color": value}
    if row["operation_id"] == "vml.shape.geometry.set":
        params = {"style": value}
    if row["operation_id"] == "vml.shape.metadata.set_name":
        params = {"name": value}
    if row["operation_id"] == "vml.image.metadata.set_title": params = {"title": value}
    return {"operation_id": row["operation_id"], "target": f"{row['part_name']}::{row['operation_target_selector']}", "params": params}
def _snapshot(path: Path, plans: list[dict[str, Any]]) -> dict[str, Any]:
    parts = {item["row"]["part_name"] for item in plans}
    return {"parts": {part: _fingerprints(path, part) for part in parts}}
def _check_path(path: Path, plans: list[dict[str, Any]], before: dict[str, Any]) -> dict[str, Any]:
    after = {part: _fingerprints(path, part) for part in before["parts"]}
    targets = _targets(plans)
    rows = {}
    for item in plans:
        row = item["row"]
        actual = _read_value(path, row)
        outside = _outside(before["parts"][row["part_name"]], after[row["part_name"]], targets[row["part_name"]])
        rows[row["row_id"]] = {"after_value": actual, "expected_after_value": item["requested"], "outside_changes": outside, "pass": actual == item["requested"] and outside == 0}
    return {"output_file": str(path.relative_to(PROJECTS)), "rows": rows}
def _targets(plans: list[dict[str, Any]]) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = {}
    for item in plans:
        grouped.setdefault(item["row"]["part_name"], set()).add(item["row"]["operation_target_selector"])
    return grouped
def _read_value(path: Path, row: dict[str, Any]) -> str:
    tree = _tree(path, row["part_name"])
    nodes = tree.xpath(row["operation_target_selector"], namespaces=_ns(tree))
    if row["operation_id"] in DELETE_ONLY_PRESENCE_OPS:
        if len(nodes) > 1:
            raise ValueError(f"selector matched {len(nodes)}")
        return "true" if len(nodes) == 1 else "false"
    if len(nodes) != 1:
        raise ValueError(f"selector matched {len(nodes)}")
    node = nodes[0]
    if row.get("attribute_name"):
        if row["operation_id"] == "alternate_content.choice.metadata.set_value":
            node = next(child for child in node if child.tag.endswith("}Choice"))
        return node.get(row["attribute_name"], "")
    if row["operation_id"] == "vml.shape.text.set":
        return visible_vml_text(node)
    return " ".join("".join(node.itertext()).split())
def _evidence_row(item, output, api, cli, mcp, office) -> dict[str, Any]:
    row, checks = item["row"], api["rows"].get(item["row"]["row_id"], {})
    semantic = checks.get("pass") is True and not api["errors"] and not api["new_errors"]
    public = _path_pass(cli, row) and _path_pass(mcp, row)
    return _row_payload(row, item, output, semantic, public, office, checks.get("outside_changes", -1), cli, mcp)
def _row_payload(row, item, output, semantic, public, office, sibling_changes, cli, mcp) -> dict[str, Any]:
    params = _payload(item)["params"]
    changed = item["before"] != item["requested"]
    return {"row_id": row["row_id"], "source_row_id": row["source_row_id"], "source_phase": "former-preserve-only-campaign", "format": row["format"], "input_file": row["input_file"], "package_id": row["package_id"], "part_name": row["part_name"], "stable_id": row["stable_id"], "stable_id_scope": "package-local", "selector": row["selector"], "qname": row["qname"], "family": row["family"], "semantic_model_id": f"{row['family']}.{row['operation_id']}.v1", "operation_id": row["operation_id"], "operation_target": f"{row['part_name']}::{row['operation_target_selector']}", "operation_params": params, "capability_tier": "semantic-active-editable", "understanding_level": "operation-hydrated-semantic", "before_semantic_value": {"value": item["before"], "value_kind": row["value_kind"], "attribute_name": row.get("attribute_name", "")}, "requested_semantic_change": {"operation_id": row["operation_id"], "value": item["requested"]}, "after_semantic_value": {"value": item["requested"], "value_kind": row["value_kind"], "attribute_name": row.get("attribute_name", "")}, "target_semantic_changed": changed, "sibling_unexpected_semantic_mutation_count": sibling_changes, "package_invariant_pass": semantic, "public_api_path": "JsonRpcServer.ooxml_apply + CLI ooxml-engine apply + MCP ooxml_apply", "cli_path_checked": _path_pass(cli, row), "mcp_path_checked": _path_pass(mcp, row), "mcp_list_tools_pass": mcp.get("list_tools_pass") is True, "mcp_call_tool_replay_pass": mcp.get("return_code") == 0, "native_office_result": office["status"], "office_result_id": office.get("office_json", ""), "output_file": str(output.relative_to(PROJECTS)), "cli_output_file": cli.get("output_file", ""), "mcp_output_file": mcp.get("output_file", ""), "cli_return_code": cli.get("return_code"), "mcp_return_code": mcp.get("return_code"), "semantic_edit_pass": semantic and changed, "pass": changed and semantic and public and office["return_code"] == 0 and office["status"] == "pass"}
def _path_pass(result: dict[str, Any], row: dict[str, Any]) -> bool:
    return result.get("return_code") == 0 and result.get("rows", {}).get(row["row_id"], {}).get("pass") is True
def _ns(tree) -> dict[str, str]:
    return {k: v for node in tree.getroot().iter() for k, v in node.nsmap.items() if k}
def _size_mb(row: dict[str, Any]) -> float:
    return (CORPUS / row["input_file"]).stat().st_size / 1024 / 1024
def _brief(plan: dict[str, Any]) -> dict[str, Any]:
    row = plan["row"]
    return {key: row.get(key) for key in ("row_id", "family", "operation_id", "package_id", "part_name")}
def _summary(rows: list[dict[str, Any]], new_rows: int, label: str) -> dict[str, Any]:
    return {"schema_version": "former-preserve-only-campaign-promotion-v1", "summary_scope": "cumulative_promotion_rows", "latest_label": label, "latest_new_row_count": new_rows, "label": label, "new_row_count": new_rows, "row_count": len(rows), "row_pass_count": sum(row.get("pass") is True for row in rows), "semantic_edit_pass_count": sum(row.get("semantic_edit_pass") is True for row in rows), "deduped_semantic_edit_pass_count": deduped_operation_count([row for row in rows if row.get("semantic_edit_pass") is True]), "alias_operation_row_count": alias_operation_count_from_rows([row for row in rows if row.get("pass") is True]), "cli_path_pass_count": sum(row.get("cli_path_checked") is True for row in rows), "mcp_path_pass_count": sum(row.get("mcp_path_checked") is True for row in rows), "native_office_pass_count": sum(row.get("native_office_result") == "pass" for row in rows), "gate_pass": bool(rows) and all(row.get("pass") is True for row in rows)}
if __name__ == "__main__":
    raise SystemExit(main())
