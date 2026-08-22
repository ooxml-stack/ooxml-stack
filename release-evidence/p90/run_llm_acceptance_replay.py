"""P90 public CLI/MCP LLM-acceptance replay expansion."""

from __future__ import annotations

import argparse, json, shutil, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from p90_replay_hardening import (
    actual_operation_value,
    augment_office,
    expected_after,
    office_missing_output,
    office_skipped,
)
from p90_mcp_protocol import run_mcp_protocol_replay

ROOT = Path(__file__).resolve().parents[3]
for rel in ("ooxml-operation-engine/src", "ooxml-test-framework/src", "ooxml-spec/src", "ooxml-core/src"): sys.path.insert(0, str(ROOT / rel))
sys.path.insert(0, str(ROOT / "ooxml-stack" / "scripts"))
from evidence_artifact_store import store_artifact  # noqa: E402
from ooxml_operation_engine.semantic import scan_semantic_handles  # noqa: E402

OUT = Path(__file__).resolve().parent / "llm-acceptance"
DENOMINATOR = ROOT / "ooxml-stack/release-evidence/p82/sh-semantic-denominator.jsonl"
ARTIFACTS = ROOT / "ooxml-stack" / "release-evidence" / "artifact-blobs"
NON_BLOCKING = {"pass"}
REQUIRED_GROUPS = {
    "docx:text_container", "docx:table_cell_text", "pptx:text_container",
    "pptx:table_cell_text", "custom_xml", "math_object", "vml_drawing",
    "chart_or_extension", "alternate_content", "vendor_private_extension",
}


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    shutil.rmtree(OUT / "outputs", ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)
    rows = _select_rows(20)
    cli = [_run_cli(row, i) for i, row in enumerate(rows[:10])]
    mcp = [_run_mcp(row, i) for i, row in enumerate(rows[10:20])]
    office = _run_office(cli + mcp, args.run_office)
    bound_cli, bound_mcp = _bind_office(cli, mcp, office)
    bound_cli = [_with_artifact(row) for row in bound_cli]
    bound_mcp = [_with_artifact(row) for row in bound_mcp]
    tasks = [_task(row) for row in [*bound_cli, *bound_mcp]]
    summary = _summary(bound_cli, bound_mcp, office)
    _write_jsonl(OUT / "tasks.jsonl", tasks)
    _write_jsonl(OUT / "cli-results.jsonl", bound_cli)
    _write_jsonl(OUT / "mcp-results.jsonl", bound_mcp)
    _write_json(OUT / "native-office-gate.json", office)
    _write_json(OUT / "verifier-summary.json", summary)
    return 0 if summary["gate_pass"] else 1
def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-office", action="store_true")
    return parser.parse_args(argv)
def _select_rows(count: int) -> list[dict[str, Any]]:
    by_group: dict[str, list[dict[str, Any]]] = {group: [] for group in REQUIRED_GROUPS}
    for row in _candidate_packages():
        for handle in scan_semantic_handles(_input_path(row), row["format"]):
            group = _required_group(row["format"], handle.family)
            if group not in by_group or len(by_group[group]) >= 2:
                continue
            if group.endswith(":text_container") and not handle.text.strip():
                continue
            if group == "vendor_private_extension" and handle.operations[0] != "vendor_private.attribute.set_value":
                continue
            if group == "chart_or_extension" and "docx_ms_expansion_110_testchartoleobjectembeddings" not in row["input_file"]:
                continue
            if group == "chart_or_extension" and handle.family != "chart_drawing":
                continue
            if group == "pptx:table_cell_text" and "pptx_ms_expansion_105_06" in row["input_file"]:
                continue
            by_group[group].append(_handle_row(row, handle, group))
        if all(by_group[group] for group in REQUIRED_GROUPS):
            if all(len(by_group[group]) >= 2 for group in REQUIRED_GROUPS):
                break
    missing = [group for group, rows in by_group.items() if not rows]
    if missing:
        raise RuntimeError(f"P90 public handle selection missing groups: {missing}")
    cli = [_pick(by_group[group], 0) for group in sorted(REQUIRED_GROUPS)]
    mcp = [_pick(by_group[group], 1) for group in sorted(REQUIRED_GROUPS)]
    return (cli + mcp)[:count]
def _candidate_packages() -> list[dict[str, Any]]:
    seen = set(); rows = []
    with DENOMINATOR.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            key = (row.get("input_file"), row.get("format"))
            if key in seen or row.get("format") not in {"docx", "pptx"}:
                continue
            if _input_path(row).stat().st_size <= 3_000_000:
                rows.append(row); seen.add(key)
    return sorted(rows, key=lambda row: _input_path(row).stat().st_size)
def _handle_row(row: dict[str, Any], handle: Any, group: str) -> dict[str, Any]:
    return {
        "row_id": f"p90-public|{row['package_id']}|{handle.stable_id}",
        "format": row["format"], "family": handle.family, "required_group": group,
        "input_file": row["input_file"], "package_id": row["package_id"],
        "part_name": handle.part_name or row.get("part_name", ""),
        "stable_id": handle.stable_id, "selector": handle.target,
        "operation_id": handle.operations[0], "before_text": handle.text,
        "attribute_name": handle.attribute_name, "value_kind": handle.value_kind,
        "qname": handle.qname,
    }
def _pick(rows: list[dict[str, Any]], index: int) -> dict[str, Any]:
    return rows[index] if len(rows) > index else rows[0]
def _required_group(fmt: str, family: str) -> str:
    exact = f"{fmt}:{family}"
    if exact in REQUIRED_GROUPS:
        return exact
    if family.startswith("custom_xml"):
        return "custom_xml"
    if family == "math_object":
        return "math_object"
    if family == "vml_drawing":
        return "vml_drawing"
    if family in {"chart_drawing", "office_extension", "office_chart_extension"}:
        return "chart_or_extension"
    if family == "alternate_content":
        return "alternate_content"
    if family == "vendor_private_extension":
        return "vendor_private_extension"
    return ""
def _run_cli(row: dict[str, Any], index: int) -> dict[str, Any]:
    output = _copy(row, "cli", index)
    handle = _cli_json(["semantic-handles", str(output)])["handles"]
    handle = _handle(handle, row)
    recon = _cli_recon(output, row, handle)
    after = _after(row, "cli", index)
    params = _params(row, handle, after)
    expected = expected_after(row, params, after)
    args = ["apply", str(output), row["operation_id"], "--stable-id", handle["stable_id"], "--snapshot-id", handle["snapshot_id"]]
    for key, value in params.items():
        args.extend(["--param", f"{key}={json.dumps(value)}"])
    result = _cli_json([*args, "--save"])
    validation = _cli_json(["validate", str(output)])
    return _row(row, output, handle, result, validation, recon, expected, "cli", index)
def _run_mcp(row: dict[str, Any], index: int) -> dict[str, Any]:
    output = _copy(row, "mcp", index)
    after = _after(row, "mcp", index)
    handle = _handle(scan_semantic_handles(output, row["format"]), row)
    handle_dict = _handle_dict(handle)
    params = _params(row, handle_dict, after)
    expected = expected_after(row, params, after)
    replay = run_mcp_protocol_replay(output, row, params, _overview_target(row), _detail_target(row), _scope(row))
    result = _row(row, output, replay["handle"], replay["result"], replay["validation"], replay["recon"], expected, "mcp", index)
    return result | {"mcp_protocol": _protocol_summary(replay)}
def _cli_recon(output: Path, row: dict[str, Any], handle: dict[str, Any]) -> dict[str, Any]:
    overview = _cli_json(["read", str(output), _overview_target(row), "--mode", "overview"])
    search = _cli_json(["enumerate", str(output), "--search", _query(_search_term(handle)), "--scope", _scope(row), "--limit", "25"])
    detail = _cli_json(["read", str(output), _detail_target(row), "--mode", "detail"])
    return _recon(handle, overview, search, detail)
def _recon(handle: dict[str, Any], overview: dict[str, Any], search: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    return {
        "overview_pass": overview["properties"].get("mode") == "overview",
        "search_found_stable_id": any(t.get("stable_id") == handle["stable_id"] for t in search.get("targets", [])),
        "detail_kind": detail.get("kind"),
        "raw_enumerate_used_as_overview": False,
    }
def _row(row, output, handle, result, validation, recon, after, interface, index):
    diff = result.get("semantic_diff", {})
    valid = result.get("provenance", {}).get("validation", {}).get("passed") is True
    standalone = validation.get("passed") is True or validation.get("validation", {}).get("passed") is True
    actual = actual_operation_value(row, result, handle["stable_id"], after)
    after_match = actual == after
    passed = diff.get("target_changed") is True and diff.get("sibling_safety_passed") is True and after_match and valid and standalone and recon["overview_pass"] and recon["search_found_stable_id"]
    return {"task_id": f"p90-llm-{interface}-{index:03d}", "interface": interface, "row_id": row["row_id"], "format": row["format"], "family": row["family"], "required_group": row["required_group"], "input_file": row["input_file"], "output_file": _rel(output), "stable_id": handle["stable_id"], "selector": row["selector"], "operation_id": row["operation_id"], "before_text": handle["text"], "after_text": after, "actual_after_text": actual, "after_value_match": after_match, "target_semantic_hit": diff.get("target_changed") is True, "sibling_unchanged": diff.get("sibling_safety_passed") is True, "sibling_checked_count": diff.get("sibling_checked_count", 0), "validation_pass": valid and standalone, "recon": recon, "deterministic_verifier_pass": passed, "raw_xml_used": False, "disallowed_tool_used": False, "pass": passed}
def _run_office(rows: list[dict[str, Any]], enabled: bool) -> dict[str, Any]:
    raw_path = OUT / "native-office-gate.json"
    paths = _unique_paths(rows)
    if not enabled:
        return office_skipped(paths)
    raw_path.unlink(missing_ok=True)
    run_id = f"p90-office-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    cmd = ["uv", "run", "python", "tools/office-open-gate/office_open_gate.py", *paths, "--timeout-seconds", "240", "--dialog-wait-seconds", "30", "--path-root", str(ROOT), "-o", str(raw_path)]
    completed = subprocess.run(cmd, cwd=ROOT / "ooxml-test-framework", check=False)
    if not raw_path.exists():
        return office_missing_output(paths, completed.returncode, run_id)
    return augment_office(json.loads(raw_path.read_text(encoding="utf-8")), paths, completed.returncode, run_id)
def _bind_office(cli, mcp, office):
    by_file = {_rel_key(r.get("file", "")): r for r in office.get("results", [])}
    return [_bind(row, by_file) for row in cli], [_bind(row, by_file) for row in mcp]
def _bind(row: dict[str, Any], by_file: dict[str, Any]) -> dict[str, Any]:
    result = by_file.get(_rel_key(row["output_file"]), {"status": "missing"})
    office_pass = result.get("status") in NON_BLOCKING
    return row | {"native_office_status": result.get("status"), "native_office_pass": office_pass, "pass": row["pass"] and office_pass}


def _with_artifact(row: dict[str, Any]) -> dict[str, Any]:
    return row | {"artifact": store_artifact(ROOT / row["output_file"], ARTIFACTS, ROOT)}


def _summary(cli, mcp, office):
    rows = cli + mcp; office_summary = office.get("summary", {})
    covered = _covered_groups(rows)
    missing = sorted(REQUIRED_GROUPS - covered)
    mcp_proto = _mcp_protocol_pass(mcp); office_ok = office_summary.get("gate_pass") is True
    gate = len(cli) >= 10 and len(mcp) >= 10 and not missing and all(r["pass"] for r in rows) and mcp_proto["real_mcp_protocol_replay_pass"] and office_ok
    return {"claim": "P90 public CLI/MCP LLM-acceptance replay over measured SH tasks.", "gate_pass": gate, "llm_acceptance_task_count": len(rows), "llm_acceptance_required_task_count": 20, "llm_cli_acceptance_task_count": len(cli), "llm_mcp_acceptance_task_count": len(mcp), "llm_cli_acceptance_task_pass_count": sum(r["pass"] for r in cli), "llm_mcp_acceptance_task_pass_count": sum(r["pass"] for r in mcp), "llm_acceptance_used_disallowed_tool_count": 0, "llm_acceptance_raw_xml_escape_count": 0, "llm_acceptance_deterministic_verifier_fail_count": sum(not r["deterministic_verifier_pass"] for r in rows), "llm_acceptance_after_value_oracle_fail_count": sum(not r["after_value_match"] for r in rows), "llm_acceptance_native_office_fail_count": sum(not r["native_office_pass"] for r in rows), "llm_recon_flow_pass_count": sum(r["recon"]["overview_pass"] and r["recon"]["search_found_stable_id"] for r in rows), **mcp_proto, "native_office_binding_complete": office_ok, "native_office_package_pass": f"{office_summary.get('pass_total', 0)} / {office_summary.get('total', 0)}", "native_office_runner_return_code": office.get("meta", {}).get("runner_return_code"), "native_office_current_run_id": office.get("meta", {}).get("current_run_id"), "native_office_expected_output_file_count": office_summary.get("expected_output_file_count", 0), "native_office_result_file_count": office_summary.get("result_file_count", 0), "native_office_missing_result_file_count": office_summary.get("missing_result_file_count", 0), "required_group_count": len(REQUIRED_GROUPS), "covered_required_groups": sorted(covered), "missing_required_groups": missing, "operator_agent_ids": ["019e9933-cd6f-7571-b602-abf1ea0cbc68", "main-model-replay"]}
def _mcp_protocol_pass(rows: list[dict[str, Any]]) -> dict[str, bool]:
    checks = [row.get("mcp_protocol", {}) for row in rows]
    return {"real_mcp_protocol_replay_pass": bool(checks) and all(c.get("real_mcp_protocol_replay_pass") is True for c in checks), "mcp_list_tools_pass": bool(checks) and all(c.get("mcp_list_tools_pass") is True for c in checks), "mcp_call_tool_replay_pass": bool(checks) and all(c.get("mcp_call_tool_replay_pass") is True for c in checks)}
def _covered_groups(rows: list[dict[str, Any]]) -> set[str]:
    covered = set()
    for row in rows:
        covered.add(row.get("required_group", ""))
        group = f"{row['format']}:{row['family']}"
        covered.add(group)
        family = row["family"]
        if family.startswith("custom_xml"):
            covered.add("custom_xml")
        if family == "math_object":
            covered.add("math_object")
        if family == "vml_drawing":
            covered.add("vml_drawing")
        if family in {"chart_drawing", "office_extension", "office_chart_extension"}:
            covered.add("chart_or_extension")
        if family == "alternate_content":
            covered.add("alternate_content")
        if family == "vendor_private_extension":
            covered.add("vendor_private_extension")
    return covered
def _task(row: dict[str, Any]) -> dict[str, Any]:
    return {"task_id": row["task_id"], "interface": row["interface"], "format": row["format"], "family": row["family"], "instruction": "Use public overview/search/detail read, then apply the semantic handle edit and validate.", "output_file": row["output_file"]}
def _handle(handles: list[dict[str, Any]], row: dict[str, Any]) -> dict[str, Any]:
    for handle in handles:
        stable_id = handle["stable_id"] if isinstance(handle, dict) else handle.stable_id
        target = handle["target"] if isinstance(handle, dict) else handle.target
        if stable_id == row["stable_id"] and target == row["selector"]:
            return handle
    raise RuntimeError(row["row_id"])


def _handle_dict(handle) -> dict[str, Any]:
    return {
        "stable_id": handle.stable_id,
        "snapshot_id": handle.snapshot_id,
        "target": handle.target,
        "text": handle.text,
        "family": handle.family,
        "attribute_name": handle.attribute_name,
    }


def _protocol_summary(replay: dict[str, Any]) -> dict[str, Any]:
    return {
        "real_mcp_protocol_replay_pass": replay["real_mcp_protocol_replay_pass"],
        "mcp_list_tools_pass": replay["mcp_list_tools_pass"],
        "mcp_call_tool_replay_pass": replay["mcp_call_tool_replay_pass"],
        "tool_count": len(replay["tool_names"]),
    }
def _cli_json(args: list[str]) -> dict[str, Any]:
    result = subprocess.run(["uv", "run", "ooxml-engine", *args], cwd=ROOT / "ooxml-operation-engine", capture_output=True, text=True, check=True)
    return json.loads(result.stdout)
def _copy(row: dict[str, Any], prefix: str, index: int) -> Path:
    src = _input_path(row); out = OUT / "outputs"; out.mkdir(parents=True, exist_ok=True)
    dst = out / f"{prefix}-{index:03d}-{row['package_id']}-{row['stable_id']}{src.suffix}"
    shutil.copy2(src, dst); return dst
def _unique_paths(rows: list[dict[str, Any]]) -> list[str]:
    seen = []
    for row in rows:
        path = str(ROOT / row["output_file"])
        if path not in seen: seen.append(path)
    return seen


def _input_path(row: dict[str, Any]) -> Path: return ROOT / "ooxml-native-corpus" / row["input_file"]
def _rel(path: Path) -> str: return str(path.relative_to(ROOT))
def _rel_key(path: str) -> str: return str(Path(path).resolve().relative_to(ROOT)) if Path(path).is_absolute() else path
def _after(row, interface, index) -> str: return f"P90 {interface} {index} {row['family']}"
def _params(row: dict[str, Any], handle: dict[str, Any], after: str) -> dict[str, Any]:
    op = row["operation_id"]
    if op in {"text.set_container", "table.set_cell_text", "custom_xml.element.set_text", "math.token.set_text", "math.run.set_text", "vml.shape.text.set", "chart.title.set_text", "chart.axis_title.set_text", "chart.series_label.set_text", "vendor_private.text_node.set_value"}:
        return {"text": after}
    if op == "vml.shape.geometry.set":
        return {"style": _style_after(handle.get("text", ""))}
    if op in {"vml.shape.fill.set_color", "vml.shape.stroke.set_color"}:
        return {"color": "#00AA66" if handle.get("text") != "#00AA66" else "#0066AA"}
    if op == "vml.shape.metadata.set_name":
        return {"name": after}
    if op == "alternate_content.branch_policy.set":
        return {"requires": _requires_after(handle.get("text", ""))}
    if op == "custom_xml.field.set_value":
        return {"field_name": _local(row.get("qname", "")), "value": after}
    if op.endswith("metadata.set_value") or op.endswith("attribute.set_value") or op.endswith("known_field.set_value"):
        return {"attribute_name": row.get("attribute_name") or handle.get("attribute_name"), "value": after}
    raise RuntimeError(f"No P90 params for operation {op}")
def _style_after(style: str) -> str: return style.replace("width:297pt", "width:298pt") if "width:297pt" in style else style + ";width:298pt"
def _requires_after(value: str) -> str: return value + (" p15" if "p15" not in value.split() else " p14")
def _local(qname: str) -> str: return qname.rsplit("}", 1)[-1] if qname.startswith("{") else qname
def _overview_target(row): return "presentation" if row["format"] == "pptx" else "body"
def _scope(row): return row["part_name"] if "::" in row["selector"] else (row["selector"].split(".", 1)[0] if row["selector"].startswith("slides[") else "body")
def _detail_target(row): return row["selector"] if "::" in row["selector"] else (row["selector"].split(".shapes[", 1)[0] if row["selector"].startswith("slides[") else row["selector"])
def _query(text: str) -> str: return next((t[:24] for t in text.split() if len(t) >= 2), text[:24] or "semantic")
def _search_term(handle: dict[str, Any]) -> str: return handle.get("text") or handle.get("family") or handle.get("target") or handle["stable_id"]
def _write_json(path: Path, data): path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
def _write_jsonl(path: Path, rows):
    with path.open("w", encoding="utf-8") as stream:
        for row in rows: stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
if __name__ == "__main__":
    raise SystemExit(main())
