#!/usr/bin/env python3
"""Campaign-scoped object-level semantic promotion runner."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZipFile
import anyio
from lxml import etree
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ROOT.parent
CORPUS = PROJECTS / "ooxml-native-corpus"
ENGINE = Path(os.environ.get("OOXML_OPERATION_ENGINE_DIR", PROJECTS / "ooxml-operation-engine"))
OUT = ROOT / "release-evidence/former-preserve-only-semantic-editability"
LEDGER = OUT / "gap-ledger.jsonl"
ROWS = OUT / "promotion-rows.jsonl"
SUMMARY = OUT / "promotion-summary.json"
OUTPUTS = OUT / "promotion-outputs"
PUBLIC = OUT / "public-paths"
OFFICE_DIR = OUT / "office-results"
ARTIFACTS = ROOT / "release-evidence/artifact-blobs"

for path in (ENGINE / "src", PROJECTS / "ooxml-test-framework/src", PROJECTS / "ooxml-core/src"):
    sys.path.insert(0, str(path))

from evidence_artifact_store import store_artifact  # noqa: E402
from ooxml_operation_engine.jsonrpc_server import JsonRpcServer  # noqa: E402
def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    phase = _mark(f"select rows label={args.label}")
    plans = _plans(_select_rows(args), args)
    _done(f"select rows planned={len(plans)}", phase)
    if not plans:
        return _write_summary([])
    phase = _mark("copy api")
    api_path = _copy(plans[0]["row"], f"api-{args.label}")
    _done("copy api", phase)
    phase = _mark("api replay")
    api = _run_api(api_path, plans)
    _done("api replay", phase)
    phase = _mark("cli replay")
    cli = _run_cli(plans, args.label)
    _done("cli replay", phase)
    phase = _mark("mcp replay")
    mcp = anyio.run(_run_mcp, plans, args.label)
    _done("mcp replay", phase)
    phase = _mark("office gate")
    office = _run_office(api_path, args.run_office)
    _done(f"office gate status={office['status']}", phase)
    api["artifact"] = _store_artifact(api_path)
    phase = _mark("write evidence")
    rows = [_evidence_row(item, api_path, api, cli, mcp, office) for item in plans]
    merged = _merge(_read_jsonl(ROWS), rows)
    _write_jsonl(ROWS, merged)
    _write_json(SUMMARY, _summary(merged, len(rows), args.label))
    _done("write evidence", phase)
    print(json.dumps(_summary(rows, len(rows), args.label), indent=2, sort_keys=True))
    return 0 if rows and all(row["pass"] for row in rows) else 1

def _mark(message: str) -> float:
    print(f"[campaign] start {message}", flush=True)
    return time.monotonic()
def _done(message: str, started: float) -> None:
    print(f"[campaign] done {message} in {time.monotonic() - started:.1f}s", flush=True)
def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-rows", type=int, default=50)
    parser.add_argument("--family", default="office_extension")
    parser.add_argument("--qname-contains", nargs="*", default=("rowId", "colId"))
    parser.add_argument("--package-id", default="")
    parser.add_argument("--max-package-mb", type=float, default=15.0)
    parser.add_argument("--label", default="office-extension-row-col")
    parser.add_argument("--attribute-name", default="val")
    parser.add_argument("--requested-value", default="")
    parser.add_argument("--required-before-value", default="")
    parser.add_argument("--semantic-model-id", default="")
    parser.add_argument("--run-office", action="store_true")
    return parser.parse_args(argv)
def _select_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    promoted = _existing_source_ids()
    with LEDGER.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if _eligible(row, args, promoted):
                groups[row["package_id"]].append(row)
    package = args.package_id or max(groups, key=lambda key: len(groups[key]), default="")
    return groups.get(package, [])[: args.max_rows]
def _eligible(row: dict[str, Any], args: argparse.Namespace, promoted: set[str]) -> bool:
    if row.get("family") != args.family or row.get("source_row_id") in promoted:
        return False
    if row.get("blocker_type") != "semantic_value_available_pending_proof":
        return False
    if args.qname_contains and not any(token in row.get("qname", "") for token in args.qname_contains):
        return False
    if args.package_id and row.get("package_id") != args.package_id:
        return False
    if args.required_before_value:
        before = _read_value(CORPUS / row["input_file"], row["part_name"], row["selector"], args.attribute_name)
        if before != args.required_before_value:
            return False
    size_mb = (CORPUS / row["input_file"]).stat().st_size / 1024 / 1024
    return not args.max_package_mb or size_mb <= args.max_package_mb
def _model_id(args: argparse.Namespace) -> str:
    return args.semantic_model_id or f"{args.family}.known_metadata.{args.attribute_name}.v1"
def _plans(rows: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    plans: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, row in enumerate(rows):
        key = (row["part_name"], row["selector"])
        if key in seen:
            continue
        before = _read_value(CORPUS / row["input_file"], row["part_name"], row["selector"], args.attribute_name)
        requested = args.requested_value or _next_value(before, index)
        plans.append({"row": row, "index": index, "attr": args.attribute_name, "before": before, "requested": requested, "semantic_model_id": _model_id(args)})
        seen.add(key)
    return plans
def _run_api(path: Path, plans: list[dict[str, Any]]) -> dict[str, Any]:
    before = _snapshot(path, plans)
    errors: list[str] = []
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
        validation = {}
        baseline = set()
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
    _store_artifact(path)
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
    _store_artifact(path)
    return _check_path(path, plans, before) | {"return_code": code, "stderr": error, "list_tools_pass": bool(getattr(tools, "tools", []))}
async def _mcp_apply(session: ClientSession, path: Path, plans: list[dict[str, Any]]) -> tuple[int, str]:
    try:
        await _call_tool(session, "ooxml_open", {"path": str(path)})
        await _call_tool(session, "ooxml_apply", {"plan": [_payload(item) for item in plans]})
        await _call_tool(session, "ooxml_validate", {})
        await _call_tool(session, "ooxml_save", {})
        return 0, ""
    except Exception as exc:  # noqa: BLE001
        return 1, str(exc)
    finally:
        try:
            await _call_tool(session, "ooxml_close", {})
        except Exception:
            pass
async def _call_tool(session: ClientSession, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = await session.call_tool(name, arguments)
    if result.isError:
        raise RuntimeError(f"{name} failed: {result.content}")
    return json.loads(result.content[0].text if result.content else "{}")
def _run_office(path: Path, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"return_code": None, "status": "not-run", "gate_pass": False, "results": [], "office_json": ""}
    office_json = _office_json(path)
    office_json.unlink(missing_ok=True)
    cmd = ["uv", "run", "python", "tools/office-open-gate/office_open_gate.py", str(path), "--timeout-seconds", "240", "--dialog-wait-seconds", "30", "--path-root", str(PROJECTS), "-o", str(office_json)]
    done = subprocess.run(cmd, cwd=PROJECTS / "ooxml-test-framework", capture_output=True, text=True, check=False)
    data = json.loads(office_json.read_text()) if office_json.exists() else {"summary": {}, "results": []}
    status = _office_status(data, path)
    return {"return_code": done.returncode, "status": status, "gate_pass": data.get("summary", {}).get("gate_pass") is True, "results": data.get("results", []), "office_json": str(office_json.relative_to(ROOT))}
def _evidence_row(item: dict[str, Any], output: Path, api: dict[str, Any], cli: dict[str, Any], mcp: dict[str, Any], office: dict[str, Any]) -> dict[str, Any]:
    row = item["row"]
    checks = api["rows"].get(_row_id(row), {})
    semantic_pass = checks.get("pass") is True and not api["errors"] and not api["new_errors"]
    public_pass = _path_pass(cli, row) and _path_pass(mcp, row)
    office_pass = office["return_code"] == 0 and office["status"] == "pass"
    return _row_payload(row, item, output, semantic_pass, public_pass, office_pass, api, cli, mcp, office)
def _row_payload(row, item, output, semantic_pass, public_pass, office_pass, api, cli, mcp, office) -> dict[str, Any]:
    return {"row_id": _row_id(row), "source_row_id": row["source_row_id"], "source_phase": "former-preserve-only-campaign", "format": row["format"], "input_file": row["input_file"], "package_id": row["package_id"], "part_name": row["part_name"], "stable_id": row["stable_id"], "stable_id_scope": "package-local", "selector": row["selector"], "qname": row["qname"], "family": row["family"], "semantic_model_id": item["semantic_model_id"], "operation_id": "office_extension.known_metadata.set_value", "operation_target": f"{row['part_name']}::{row['selector']}", "operation_params": {"attribute_name": item["attr"], "value": item["requested"]}, "capability_tier": "semantic-active-editable", "understanding_level": "office-semantic", "before_semantic_value": {"attribute_name": item["attr"], "value": item["before"], "qname": row["qname"], "value_selector": row["selector"]}, "requested_semantic_change": {"operation_id": "office_extension.known_metadata.set_value", "value": item["requested"]}, "after_semantic_value": {"attribute_name": item["attr"], "value": item["requested"], "qname": row["qname"], "value_selector": row["selector"]}, "target_semantic_changed": item["before"] != item["requested"], "sibling_unexpected_semantic_mutation_count": api["rows"].get(_row_id(row), {}).get("outside_changes", -1), "package_invariant_pass": semantic_pass, "public_api_path": "JsonRpcServer.ooxml_apply + CLI ooxml-engine apply + MCP ooxml_apply", "cli_path_checked": _path_pass(cli, row), "mcp_path_checked": _path_pass(mcp, row), "mcp_list_tools_pass": mcp.get("list_tools_pass") is True, "mcp_call_tool_replay_pass": mcp.get("return_code") == 0, "native_office_result": office["status"], "office_result_id": office.get("office_json", ""), "output_file": str(output.relative_to(PROJECTS)), "cli_output_file": cli.get("output_file", ""), "mcp_output_file": mcp.get("output_file", ""), "cli_return_code": cli.get("return_code"), "mcp_return_code": mcp.get("return_code"), "semantic_edit_pass": semantic_pass, "pass": semantic_pass and public_pass and office_pass}
def _snapshot(path: Path, plans: list[dict[str, Any]]) -> dict[str, Any]:
    parts = {item["row"]["part_name"] for item in plans}
    return {"parts": {part: _fingerprints(path, part) for part in parts}}
def _check_path(path: Path, plans: list[dict[str, Any]], before: dict[str, Any]) -> dict[str, Any]:
    targets = _targets(plans)
    after = {part: _fingerprints(path, part) for part in before["parts"]}
    rows = {}
    for item in plans:
        row = item["row"]
        actual = _read_value(path, row["part_name"], row["selector"], item["attr"])
        outside = _outside(before["parts"][row["part_name"]], after[row["part_name"]], targets[row["part_name"]])
        rows[_row_id(row)] = {"after_value": actual, "expected_after_value": item["requested"], "outside_changes": outside, "pass": actual == item["requested"] and outside == 0}
    return {"output_file": str(path.relative_to(PROJECTS)), "rows": rows}
def _payload(item: dict[str, Any]) -> dict[str, Any]:
    row = item["row"]
    return {"operation_id": "office_extension.known_metadata.set_value", "target": f"{row['part_name']}::{row['selector']}", "params": {"attribute_name": item["attr"], "value": item["requested"]}}
def _copy(row: dict[str, Any], label: str) -> Path:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    dst = OUTPUTS / f"{label}-{row['package_id']}{Path(row['input_file']).suffix}"
    shutil.copy2(CORPUS / row["input_file"], dst)
    return dst
def _store_artifact(path: Path) -> dict[str, Any]:
    return store_artifact(path, ARTIFACTS, ROOT)
def _read_value(path: Path, part_name: str, selector: str, attr: str) -> str:
    tree = _tree(path, part_name)
    nodes = tree.xpath(selector, namespaces=_namespaces(tree.getroot()))
    if len(nodes) != 1:
        raise ValueError(f"selector matched {len(nodes)} nodes: {selector}")
    return nodes[0].get(attr, "")
def _tree(path: Path, part_name: str) -> etree._ElementTree:
    with ZipFile(path) as package:
        return etree.parse(BytesIO(package.read(part_name)), etree.XMLParser(remove_blank_text=False, resolve_entities=False))
def _fingerprints(path: Path, part: str) -> dict[str, str]:
    tree = _tree(path, part)
    return {tree.getpath(node): _digest(node) for node in tree.getroot().iter()}
def _digest(node: etree._Element) -> str:
    try:
        data = etree.tostring(node, method="c14n")
    except etree.C14NError:
        data = etree.tostring(node, encoding="utf-8")
    return hashlib.sha256(data).hexdigest()
def _outside(before: dict[str, str], after: dict[str, str], targets: set[str]) -> int:
    changed = [path for path, digest in before.items() if after.get(path) != digest]
    return sum(not any(_inside_or_ancestor(path, target) for target in targets) for path in changed)
def _inside_or_ancestor(path: str, target: str) -> bool:
    return path == target or path.startswith(target + "/") or target.startswith(path + "/")
def _targets(plans: list[dict[str, Any]]) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for item in plans:
        grouped[item["row"]["part_name"]].add(item["row"]["selector"])
    return grouped
def _namespaces(root: etree._Element) -> dict[str, str]:
    return {key: value for node in root.iter() for key, value in node.nsmap.items() if key}
def _errors(validation: dict[str, Any]) -> set[tuple[str, ...]]:
    return {(i.get("rule_id", ""), i.get("file_path", ""), i.get("xpath", ""), i.get("message", "")) for i in validation.get("findings", []) if i.get("severity") == "ERROR"}
def _process_meta(done: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return {"return_code": done.returncode, "stdout_sha256": hashlib.sha256(done.stdout.encode()).hexdigest(), "stderr_sha256": hashlib.sha256(done.stderr.encode()).hexdigest(), "stderr": done.stderr[-500:]}
def _path_pass(result: dict[str, Any], row: dict[str, Any]) -> bool:
    return result.get("return_code") == 0 and result.get("rows", {}).get(_row_id(row), {}).get("pass") is True
def _office_status(data: dict[str, Any], path: Path) -> str:
    names = {str(path), str(path.resolve()), str(path.relative_to(PROJECTS)), path.name}
    for item in data.get("results", []):
        if item.get("file") in names or Path(item.get("file", "")).name == path.name:
            return str(item.get("status", "missing")).lower()
    return "missing"
def _office_json(path: Path) -> Path:
    OFFICE_DIR.mkdir(parents=True, exist_ok=True)
    return OFFICE_DIR / f"{path.stem}.json"
def _next_value(before: str, index: int) -> str:
    return str(int(before or "0") + 100_000 + index + 1) if before.isdigit() else f"{before}-campaign-{index}"
def _row_id(row: dict[str, Any]) -> str:
    return f"{row['format']}|{row['package_id']}|{row['part_name']}|{row['stable_id']}"
def _existing_source_ids() -> set[str]:
    return {row.get("source_row_id", "") for row in _read_jsonl(ROWS) if row.get("pass") is True}
def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
def _merge(existing: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = {row["row_id"]: row for row in existing}
    for row in rows:
        merged[row["row_id"]] = row
    return list(merged.values())
def _summary(rows: list[dict[str, Any]], new_rows: int, label: str) -> dict[str, Any]:
    return {"schema_version": "former-preserve-only-campaign-promotion-v1", "summary_scope": "cumulative_promotion_rows", "latest_label": label, "latest_new_row_count": new_rows, "label": label, "row_count": len(rows), "new_row_count": new_rows, "row_pass_count": sum(row.get("pass") is True for row in rows), "semantic_edit_pass_count": sum(row.get("semantic_edit_pass") is True for row in rows), "cli_path_pass_count": sum(row.get("cli_path_checked") is True for row in rows), "mcp_path_pass_count": sum(row.get("mcp_path_checked") is True for row in rows), "native_office_pass_count": sum(row.get("native_office_result") == "pass" for row in rows), "gate_pass": bool(rows) and all(row.get("pass") is True for row in rows)}
def _write_summary(rows: list[dict[str, Any]]) -> int:
    _write_json(SUMMARY, _summary(rows, 0, "empty"))
    return 1
if __name__ == "__main__":
    raise SystemExit(main())
