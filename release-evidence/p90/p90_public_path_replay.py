"""Replay current P90 rows through public CLI and MCP paths."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
from typing import Any

import anyio
from lxml import etree
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from jsonl_artifacts import read_jsonl as _read_jsonl_artifact

ROOT = Path(__file__).resolve().parents[3]
for rel in ("ooxml-operation-engine/src", "ooxml-test-framework/src", "ooxml-spec/src", "ooxml-core/src"): sys.path.insert(0, str(ROOT / rel))
sys.path.insert(0, str(ROOT / "ooxml-stack" / "scripts"))
from evidence_artifact_store import store_artifact  # noqa: E402
from ooxml_operation_engine.semantic_objects import _xpath  # noqa: E402
OUT = ROOT / "ooxml-stack" / "release-evidence" / "p90"
ROWS = OUT / "sh-semantic-editability-rows.jsonl"
REPLAY = OUT / "p90-public-path-replay.jsonl"
SUMMARY = OUT / "p90-public-path-replay-summary.json"
REPLAY_DIR = OUT / "p90-public-paths"
CORPUS = ROOT / "ooxml-native-corpus"
ARTIFACTS = ROOT / "ooxml-stack" / "release-evidence" / "artifact-blobs"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    REPLAY_DIR.mkdir(parents=True, exist_ok=True)
    existing = _existing_replay()
    rows = _candidate_rows(args.max_rows, existing, args.min_input_size, args.max_input_size)
    new_results = [_replay_row(row, index, args.timeout_seconds) for index, row in enumerate(rows)]
    merged = _merge(existing, new_results)
    summary = _summary(merged)
    _write_jsonl(REPLAY, merged)
    _write_json(SUMMARY, summary)
    return 0 if summary["gate_pass"] else 1


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-rows", type=int, default=20)
    parser.add_argument("--min-input-size", type=int, default=0)
    parser.add_argument("--max-input-size", type=int, default=0)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    return parser.parse_args(argv)


def _candidate_rows(limit: int, existing: dict[str, dict[str, Any]], min_size: int, max_size: int) -> list[dict[str, Any]]:
    selected = []
    for row in _read_jsonl(ROWS):
        if _is_p80_promotion_row(row) or existing.get(row.get("row_id"), {}).get("pass") is True:
            continue
        if row.get("cli_path_checked") is True and row.get("mcp_path_checked") is True:
            continue
        size = _input_size(row)
        if size >= min_size and (not max_size or size <= max_size):
            selected.append(row)
    return sorted(selected, key=_input_size)[:limit]


def _input_size(row: dict[str, Any]) -> int:
    return (CORPUS / row["input_file"]).stat().st_size

def _is_p80_promotion_row(row: dict[str, Any]) -> bool:
    return row.get("source_phase") == "p80"


def _replay_row(row: dict[str, Any], index: int, timeout: int) -> dict[str, Any]:
    cli = _safe("cli", lambda: _run_cli(row, index, timeout))
    mcp = _safe("mcp", lambda: anyio.run(_run_mcp, row, index, timeout))
    return {
        "row_id": row["row_id"],
        "source_row_id": row.get("source_row_id", ""),
        "operation_id": row["operation_id"],
        "cli": cli,
        "mcp": mcp,
        "cli_path_checked": cli["pass"],
        "mcp_path_checked": mcp["pass"],
        "pass": cli["pass"] and mcp["pass"],
    }


def _safe(interface: str, fn) -> dict[str, Any]:
    try:
        return fn()
    except Exception as exc:
        return {"interface": interface, "pass": False, "error": str(exc)[-500:]}


def _run_cli(row: dict[str, Any], index: int, timeout: int) -> dict[str, Any]:
    path = _copy_input(row, index, "cli")
    handle = _handle(_cli_json(["semantic-handles", str(path)], timeout)["handles"], row, path)
    params = _params(row, handle)
    args = ["apply", str(path), row["operation_id"], "--stable-id", handle["stable_id"], "--snapshot-id", handle["snapshot_id"]]
    for key, value in sorted(params.items()):
        args.extend(["--param", f"{key}={json.dumps(value)}"])
    completed = _cli(args + ["--save"], timeout)
    result = _json_or_error(completed.stdout)
    validation = _cli_json(["validate", str(path)], timeout) if completed.returncode == 0 else {}
    return _checked("cli", path, row, result, validation, completed.returncode, completed.stderr, handle["stable_id"])


async def _run_mcp(row: dict[str, Any], index: int, timeout: int) -> dict[str, Any]:
    path = _copy_input(row, index, "mcp")
    server = StdioServerParameters(command=sys.executable, args=["-m", "ooxml_operation_engine.mcp_server"], cwd=str(ROOT / "ooxml-operation-engine"))
    with anyio.fail_after(timeout):
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                return await _mcp_calls(session, bool(tools.tools), path, row)


async def _mcp_calls(session: ClientSession, listed: bool, path: Path, row: dict[str, Any]) -> dict[str, Any]:
    await _call(session, "ooxml_open", {"path": str(path)})
    try:
        handles = await _call(session, "ooxml_semantic_handles", {})
        handle = _handle(handles["handles"], row, path)
        result = await _call(session, "ooxml_apply", _apply_payload(row, handle))
        validation = await _call(session, "ooxml_validate", {})
        await _call(session, "ooxml_save", {})
        checked = _checked("mcp", path, row, result, validation, 0, "", handle["stable_id"])
        return checked | {"mcp_list_tools_pass": listed, "mcp_call_tool_replay_pass": True}
    finally:
        await _call(session, "ooxml_close", {})


async def _call(session: ClientSession, name: str, args: dict[str, Any]) -> dict[str, Any]:
    result = await session.call_tool(name, args)
    if result.isError:
        raise RuntimeError(f"MCP tool {name} failed: {result.content}")
    text = result.content[0].text if result.content else "{}"
    return json.loads(text)


def _apply_payload(row: dict[str, Any], handle: dict[str, Any]) -> dict[str, Any]:
    return {"operation_id": row["operation_id"], "stable_id": handle["stable_id"], "snapshot_id": handle["snapshot_id"], "params": _params(row, handle)}


def _params(row: dict[str, Any], handle: dict[str, Any]) -> dict[str, str]:
    after = str(row["requested_semantic_change"]["value"])
    op = row["operation_id"]
    if op == "vml.shape.geometry.set":
        return {"style": after}
    if op in {"vml.shape.fill.set_color", "vml.shape.stroke.set_color"}:
        return {"color": after}
    if op == "vml.shape.metadata.set_name":
        return {"name": after}
    if op == "alternate_content.branch_policy.set":
        return {"requires": after}
    if op == "custom_xml.field.set_value":
        return {"field_name": _local_name(handle.get("qname", "")), "value": after}
    if op == "math.object.metadata.set_value":
        return {"attribute_name": handle.get("attribute_name") or "p85", "value": after}
    if op == "vendor_private.text_node.set_value":
        return {"text": after}
    if _is_attr_op(op):
        return {"attribute_name": handle.get("attribute_name", ""), "value": after}
    return {"text": after}

def _is_attr_op(op: str) -> bool:
    return op.endswith(".set_value") or op in {"chart.drawing.metadata.set_value", "math.object.metadata.set_value"}


def _checked(interface, path, row, result, validation, code, stderr, stable_id) -> dict[str, Any]:
    expected = str(row["requested_semantic_change"]["value"])
    actual = _actual_after(result, stable_id)
    diff = result.get("semantic_diff", {})
    valid = _validation_pass(result, validation)
    passed = code == 0 and actual == expected and diff.get("target_changed") is True and diff.get("sibling_safety_passed") is True and valid
    return {"interface": interface, "output_file": str(path.relative_to(ROOT)), "artifact": store_artifact(path, ARTIFACTS, ROOT), "return_code": code, "source_stable_id": row["stable_id"], "resolved_stable_id": stable_id, "after_value": actual, "expected_after_value": expected, "after_value_match": actual == expected, "target_semantic_hit": diff.get("target_changed") is True, "sibling_safety_passed": diff.get("sibling_safety_passed") is True, "validation_pass": valid, "stderr_size": len(stderr.encode("utf-8")), "stderr_warning_text_count": stderr.lower().count("warning"), "stderr_error_text_count": stderr.lower().count("error"), "stderr_unreadable_text_count": stderr.lower().count("unreadable"), "pass": passed}


def _actual_after(result: dict[str, Any], stable_id: str) -> str:
    for change in result.get("semantic_diff", {}).get("changes", []):
        if change.get("stable_id") == stable_id:
            return str(change.get("after_text", ""))
    return str(result.get("handle", {}).get("text", ""))


def _validation_pass(result: dict[str, Any], validation: dict[str, Any]) -> bool:
    return result.get("provenance", {}).get("validation", {}).get("passed") is True


def _handle(handles: list[dict[str, Any]], row: dict[str, Any], path: Path) -> dict[str, Any]:
    exact = [h for h in handles if h["stable_id"] == row["stable_id"] and h["target"] == row["selector"]]
    if len(exact) == 1:
        return exact[0]
    target = _current_target(row, path)
    if row["operation_id"] in {"math.token.set_text", "math.run.set_text", "vendor_private.text_node.set_value", "chart.series_label.set_text"}:
        child = _first_descendant_handle(handles, row, target)
        if child:
            return child
    matches = [h for h in handles if h["target"] == target and row["operation_id"] in h["operations"]]
    if len(matches) == 1:
        return matches[0]
    raise RuntimeError(f"{row['row_id']} resolved={len(matches)} target={target[:120]}")


def _first_descendant_handle(handles: list[dict[str, Any]], row: dict[str, Any], target: str) -> dict[str, Any] | None:
    op = row["operation_id"]
    found = [h for h in handles if h["target"].startswith(target + "/") and op in h["operations"]]
    before = str(row["before_semantic_value"]["value"])
    return next((h for h in found if str(h.get("text", "")) == before), found[0] if found else None)


def _current_target(row: dict[str, Any], path: Path) -> str:
    selector = row["selector"]
    if "::" in selector:
        return selector
    part = row["part_name"]
    with ZipFile(path) as zf:
        tree = etree.parse(BytesIO(zf.read(part)), etree.XMLParser(resolve_entities=False))
    matches = tree.xpath(selector, namespaces=_namespaces(tree))
    if len(matches) != 1 or not isinstance(matches[0], etree._Element):
        raise RuntimeError(f"selector matched {len(matches)} nodes: {selector}")
    return f"{part}::{_xpath(matches[0])}"


def _namespaces(tree: etree._ElementTree) -> dict[str, str]:
    ns = {}
    for node in tree.iter():
        for key, value in node.nsmap.items():
            if key:
                ns.setdefault(key, value)
    return ns


def _local_name(qname: str) -> str:
    return qname.rsplit("}", 1)[-1] if "}" in qname else qname.rsplit(":", 1)[-1]


def _copy_input(row: dict[str, Any], index: int, label: str) -> Path:
    src = CORPUS / row["input_file"]
    suffix = src.suffix
    safe = row["stable_id"].replace(":", "_")
    dst = REPLAY_DIR / f"{label}-{index:03d}-{row['package_id']}-{safe}{suffix}"
    shutil.copy2(src, dst)
    return dst


def _cli(args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["uv", "run", "ooxml-engine", *args], cwd=ROOT / "ooxml-operation-engine", capture_output=True, text=True, check=False, timeout=timeout)


def _cli_json(args: list[str], timeout: int) -> dict[str, Any]:
    result = _cli(args, timeout)
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-500:])
    return json.loads(result.stdout)


def _json_or_error(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def _existing_replay() -> dict[str, dict[str, Any]]:
    if not REPLAY.exists():
        return {}
    rows = _read_jsonl(REPLAY)
    return {row["row_id"]: row for row in rows if row.get("pass") is True}


def _merge(existing: dict[str, dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = dict(existing)
    for row in rows:
        if row.get("pass") is True:
            merged[row["row_id"]] = row
    return list(merged.values())


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"schema_version": "p90-public-path-replay-v1", "gate_pass": bool(rows) and all(row["pass"] for row in rows), "row_count": len(rows), "row_pass_count": sum(row["pass"] for row in rows), "cli_path_pass_count": sum(row["cli_path_checked"] for row in rows), "mcp_path_pass_count": sum(row["mcp_path_checked"] for row in rows)}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return _read_jsonl_artifact(path)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
