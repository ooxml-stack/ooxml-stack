from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from lxml import etree
from jsonl_artifacts import read_jsonl as _read_jsonl_artifact, write_jsonl as _write_jsonl_artifact

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / rel) for rel in ("ooxml-operation-engine/src", "ooxml-test-framework/src", "ooxml-spec/src", "ooxml-core/src")]
sys.path.insert(0, str(ROOT / "ooxml-stack" / "scripts"))
from evidence_artifact_store import store_artifact  # noqa: E402
from ooxml_operation_engine.jsonrpc_server import JsonRpcServer  # noqa: E402

OUT = ROOT / "ooxml-stack" / "release-evidence" / "p90"
ROWS = ROOT / "ooxml-stack" / "release-evidence" / "p77" / "public-api-object-edit-rows.jsonl"
CORPUS = ROOT / "ooxml-native-corpus"
ARTIFACTS = ROOT / "ooxml-stack" / "release-evidence" / "artifact-blobs"
PASS_STATUSES = {"pass"}
TREE_CACHE: dict[tuple[str, str], etree._ElementTree] = {}

def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    existing = _existing_promotion_rows()
    new_rows = _run_candidates(_select_candidates(args.max_rows, args.max_scan, set(args.families), args.max_package_mb, args.qname_contains, args.package_id))
    office = _run_office(new_rows, args.run_office)
    rows = _merge_rows(existing, [_bind_office(row, office) for row in new_rows])
    summary = _summary(rows, office)
    _write_jsonl(OUT / "p80-semantic-promotion-rows.jsonl", rows)
    _write_json(OUT / "p80-semantic-promotion-summary.json", summary)
    return 0 if summary["gate_pass"] else 1
def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-rows", type=int, default=20)
    parser.add_argument("--max-scan", type=int, default=2000)
    parser.add_argument("--max-package-mb", type=float, default=0.0)
    parser.add_argument("--qname-contains", default="")
    parser.add_argument("--package-id", default="")
    parser.add_argument("--families", nargs="*", default=())
    parser.add_argument("--run-office", action="store_true")
    return parser.parse_args(argv)
def _select_candidates(limit: int, max_scan: int, families: set[str], max_package_mb: float, qname_contains: str, package_id: str) -> list[dict[str, Any]]:
    selected, seen = [], set()
    existing = _existing_p90_source_rows()
    with ROWS.open(encoding="utf-8") as stream:
        for index, line in enumerate(stream):
            if index >= max_scan:
                break
            row = json.loads(line)
            if families and row.get("family") not in families:
                continue
            if package_id and row.get("package_id") != package_id:
                continue
            if qname_contains and qname_contains not in row.get("qname", ""):
                continue
            if max_package_mb and (CORPUS / row["input_file"]).stat().st_size > max_package_mb * 1024 * 1024:
                continue
            if row["row_id"] in existing or f"p80|{row['row_id']}" in existing:
                continue
            plan = _plan(row)
            key = (row["input_file"], row["part_name"], row["selector"])
            if plan and key not in seen:
                selected.append(row | {"promotion_plan": plan})
                seen.add(key)
            if len(selected) >= limit:
                break
    return selected
def _run_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    (OUT / "p80-promotion-outputs").mkdir(parents=True, exist_ok=True)
    return [_run_one(row, index) for index, row in enumerate(rows)]
def _run_one(row: dict[str, Any], index: int) -> dict[str, Any]:
    output = _copy_input(row, index)
    plan = row["promotion_plan"]
    before = _read_value(output, row["part_name"], plan["value_selector"], plan.get("attribute_name"))
    before_digest = _target_digest(output, row)
    before_part = _part_fingerprints(output, row["part_name"])
    result = _apply(output, plan, _after_value(before, index, plan))
    after = _read_value(output, row["part_name"], plan["value_selector"], plan.get("attribute_name"))
    after_digest = _target_digest(output, row)
    outside = _outside_changes(before_part, _part_fingerprints(output, row["part_name"]), row["selector"])
    return _row(row, output, plan, before, after, before_digest, after_digest, outside, result)

def _plan(row: dict[str, Any]) -> dict[str, Any] | None:
    if row["family"] == "alternate_content":
        return None
    if row["family"] == "office_extension" and row.get("qname", "").endswith("}creationId"):
        return _op(row, "office_extension.creation_id.set", row["selector"], _creation_id_attr(row))
    if row["family"] == "office_extension" and row.get("qname", "").endswith("}useLocalDpi"):
        return _op(row, "office_extension.known_metadata.set_value", row["selector"], "val")
    node, tree = _resolve(row)
    if node is None:
        return None
    attr = _safe_attr(node)
    attr_node = node if attr else next((item for item in node.iterdescendants() if _safe_attr(item)), None)
    if attr_node is not None:
        return _attr_plan(row, tree, attr_node, _safe_attr(attr_node))
    return _text_plan(row, tree, _text_node(node))

def _attr_plan(row, tree, node, attr: str) -> dict[str, Any] | None:
    family = row["family"]
    if family.startswith("custom_xml") or family == "sharepoint_property":
        return _op(row, "custom_xml.attribute.set_value", tree.getpath(node), attr)
    if family in {"wps_extension"}:
        return _op(row, "wps_extension.known_field.set_value", tree.getpath(node), attr)
    if family == "vendor_private_extension":
        return _op(row, "vendor_private.attribute.set_value", tree.getpath(node), attr)
    if family in {"office_extension", "office_chart_extension", "drawing_extension", "office_drawing_sketch_extension", "chart_drawing"} and row["part_name"].startswith(("word/", "ppt/")):
        return _op(row, "office_extension.known_metadata.set_value", tree.getpath(node), attr)
    if family == "math_object" and _omml_safe_part(row["part_name"]):
        return _op(row, "math.object.metadata.set_value", tree.getpath(node), attr)
    return None
def _text_plan(row, tree, node) -> dict[str, Any] | None:
    if node is None:
        return None
    family = row["family"]
    selector = tree.getpath(node)
    if family.startswith("custom_xml") or family == "sharepoint_property":
        return _op(row, "custom_xml.element.set_text", selector, "")
    if family == "vendor_private_extension":
        return _op(row, "vendor_private.text_node.set_value", selector, "")
    if family == "math_object" and _omml_safe_part(row["part_name"]):
        return _op(row, "math.token.set_text", selector, "")
    return None
def _op(row, operation_id: str, value_selector: str, attr: str) -> dict[str, Any]:
    return {"operation_id": operation_id, "target": f"{row['part_name']}::{value_selector}", "value_selector": value_selector, "attribute_name": attr}
def _apply(output: Path, plan: dict[str, Any], value: str) -> dict[str, Any]:
    server = JsonRpcServer()
    server.handle("ooxml_open", {"path": str(output)})
    try:
        result = server.handle("ooxml_apply", {"operation_id": plan["operation_id"], "target": plan["target"], "params": _params(plan, value)})
        validation = server.handle("ooxml_validate", {})
        server.handle("ooxml_save", {})
        return {"apply": result, "validation": validation}
    finally:
        try:
            server.handle("ooxml_close", {})
        except Exception:
            server.cleanup()
def _params(plan: dict[str, Any], value: str) -> dict[str, str]:
    op = plan["operation_id"]
    if op == "office_extension.creation_id.set":
        return {"value": value}
    if op in {"custom_xml.element.set_text", "math.token.set_text", "vendor_private.text_node.set_value"}:
        return {"text": value}
    return {"attribute_name": plan["attribute_name"], "value": value}


def _row(row, output, plan, before, after, before_digest, after_digest, outside, result) -> dict[str, Any]:
    valid = result["apply"].get("provenance", {}).get("validation", {}).get("passed") is True
    standalone = result["validation"].get("passed") is True or result["validation"].get("validation", {}).get("passed") is True
    errors = sum(item.get("severity") == "ERROR" for item in result["validation"].get("findings", []))
    changed = before != after and before_digest != after_digest
    params = _params(plan, after)
    return {"row_id": f"{row['format']}|{row['package_id']}|{row['part_name']}|{row['stable_id']}", "format": row["format"], "input_file": row["input_file"], "package_id": row["package_id"], "part_name": row["part_name"], "stable_id": row["stable_id"], "stable_id_scope": "package-local", "selector": row["selector"], "operation_target": plan["target"], "operation_params": params, "family": row["family"], "semantic_model_id": f"{row['family']}.p80-promotion.v1", "operation_id": plan["operation_id"], "capability_tier": "semantic-active-editable", "understanding_level": _understanding(row["family"]), "before_semantic_value": {"value": before, "qname": row.get("qname", ""), "value_selector": plan["value_selector"]}, "requested_semantic_change": {"operation_id": plan["operation_id"], "value": after}, "after_semantic_value": {"value": after, "qname": row.get("qname", ""), "value_selector": plan["value_selector"]}, "target_semantic_changed": changed, "sibling_unexpected_semantic_mutation_count": outside, "package_invariant_pass": valid, "standalone_validation_pass": standalone, "standalone_validation_error_count": errors, "native_office_result": "not-run", "public_api_path": "ooxml_operation_engine.JsonRpcServer.ooxml_apply", "cli_path_checked": False, "mcp_path_checked": False, "llm_acceptance_task_ids": [], "source_phase": "p80", "source_row_id": f"p80|{row['row_id']}", "output_file": _rel(output), "pass": changed and outside == 0 and valid}


def _run_office(rows: list[dict[str, Any]], enabled: bool) -> dict[str, Any]:
    path = OUT / "p80-semantic-promotion-office.json"
    if not enabled:
        return {"summary": {"gate_pass": False, "skipped": True}, "results": []}
    files = [str(ROOT / row["output_file"]) for row in rows if row["pass"]]
    cmd = ["uv", "run", "python", "tools/office-open-gate/office_open_gate.py", *files, "--timeout-seconds", "240", "--dialog-wait-seconds", "30", "--path-root", str(ROOT), "-o", str(path)]
    subprocess.run(cmd, cwd=ROOT / "ooxml-test-framework", check=False)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"summary": {"gate_pass": False}, "results": []}


def _bind_office(row: dict[str, Any], office: dict[str, Any]) -> dict[str, Any]:
    by_file = {_rel_key(item.get("file", "")): item for item in office.get("results", [])}
    result = by_file.get(row["output_file"], {})
    status = result.get("status", "missing_office_result")
    return row | {"artifact": _store_artifact(ROOT / row["output_file"]), "native_office_result": status, "office_result_id": _office_id(row, status), "pass": row["pass"] and status in PASS_STATUSES}


def _summary(rows: list[dict[str, Any]], office: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": "p90-p80-semantic-promotion-v1", "gate_pass": bool(rows) and all(row["pass"] for row in rows), "row_count": len(rows), "row_pass_count": sum(row["pass"] for row in rows), "target_semantic_miss_count": sum(not row["target_semantic_changed"] for row in rows), "sibling_unexpected_semantic_mutation_count": sum(row["sibling_unexpected_semantic_mutation_count"] for row in rows), "native_office_gate_pass": office.get("summary", {}).get("gate_pass") is True, "native_office_pass_count": sum(row["native_office_result"] in PASS_STATUSES for row in rows), "native_office_total_count": len(rows), "native_office_batch_total_count": office.get("summary", {}).get("total", 0)}


def _resolve(row: dict[str, Any]) -> tuple[etree._Element | None, etree._ElementTree | None]:
    try:
        tree = _cached_tree(row["input_file"], row["part_name"])
        matches = tree.xpath(row["selector"], namespaces=_namespaces(tree.getroot()))
        return (matches[0], tree) if len(matches) == 1 and isinstance(matches[0], etree._Element) else (None, None)
    except Exception:
        return None, None


def _cached_tree(input_file: str, part_name: str) -> etree._ElementTree:
    key = (input_file, part_name)
    if key not in TREE_CACHE:
        TREE_CACHE[key] = _tree(CORPUS / input_file, part_name)
    return TREE_CACHE[key]


def _tree(path: Path, part_name: str) -> etree._ElementTree:
    with ZipFile(path) as package:
        return etree.parse(BytesIO(package.read(part_name)), etree.XMLParser(remove_blank_text=False, resolve_entities=False))


def _read_value(path: Path, part: str, selector: str, attr: str | None) -> str:
    node = _tree(path, part).xpath(selector, namespaces=_namespaces(_tree(path, part).getroot()))[0]
    return node.get(attr, "") if attr else (node.text or "")


def _target_digest(path: Path, row: dict[str, Any]) -> str:
    node = _tree(path, row["part_name"]).xpath(row["selector"], namespaces=_namespaces(_tree(path, row["part_name"]).getroot()))[0]
    return _digest_node(node)


def _part_fingerprints(path: Path, part: str) -> dict[str, str]:
    tree = _tree(path, part)
    return {tree.getpath(node): _digest_node(node) for node in tree.getroot().iter()}


def _digest_node(node: etree._Element) -> str:
    try:
        data = etree.tostring(node, method="c14n")
    except etree.C14NError:
        data = etree.tostring(node, encoding="utf-8")
    return hashlib.sha256(data).hexdigest()

def _outside_changes(before: dict[str, str], after: dict[str, str], target: str) -> int:
    return sum(not _inside_or_ancestor(path, target) and after.get(path) != digest for path, digest in before.items())


def _inside_or_ancestor(path: str, target: str) -> bool:
    return path == target or path.startswith(target + "/") or target.startswith(path + "/")


def _safe_attr(node: etree._Element) -> str:
    for name in node.attrib:
        low = name.lower()
        local = low.rsplit("}", 1)[-1]
        if local not in {"id", "nil"} and not any(token in low for token in ("rel", "macro", "textlink", "minver")):
            return name
    return ""


def _text_node(node: etree._Element) -> etree._Element | None:
    return next((item for item in node.iter() if (item.text or "").strip()), None)
def _after_value(before: str, index: int, plan: dict[str, Any]) -> str:
    if plan["operation_id"] == "office_extension.creation_id.set":
        if plan.get("attribute_name") == "val":
            return str((int(before or "0") + index + 1) % 4_294_967_295)
        digest = hashlib.sha256(f"{before}|p90s{index}".encode()).hexdigest().upper()
        return f"{{{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}}}"
    if "srgbClr" in plan.get("value_selector", "") and len(before) in {6, 8} and all(c in "0123456789abcdefABCDEF" for c in before):
        return f"{(int(before, 16) + index + 1) % (16 ** len(before)):0{len(before)}X}"
    scheme = ("accent1", "accent2", "accent3", "accent4", "accent5", "accent6", "tx1", "tx2", "bg1", "bg2", "dk1", "lt1", "dk2", "lt2", "hlink", "folHlink")
    if "schemeClr" in plan.get("value_selector", "") and before in scheme:
        return scheme[(scheme.index(before) + (index % (len(scheme) - 1)) + 1) % len(scheme)]
    return before + f" p90s{index}" if before.strip() else f"p90s{index}"
def _creation_id_attr(row: dict[str, Any]) -> str:
    return "val" if "powerpoint/2010/main" in row.get("qname", "") else "id"
def _existing_p90_source_rows() -> set[str]:
    rows = set()
    for path, pass_only in [(OUT / "sh-semantic-editability-rows.jsonl", False), (OUT / "p80-semantic-promotion-rows.jsonl", True)]:
        for row in _read_jsonl_artifact(path):
            if not pass_only or row.get("pass") is True:
                rows.add(row.get("source_row_id", ""))
    return rows
def _existing_promotion_rows() -> list[dict[str, Any]]:
    return _read_jsonl_artifact(OUT / "p80-semantic-promotion-rows.jsonl")
def _merge_rows(existing: list[dict[str, Any]], new_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = {row["row_id"]: row for row in existing}
    for row in new_rows:
        merged[row["row_id"]] = row
    return list(merged.values())
def _copy_input(row: dict[str, Any], index: int) -> Path:
    src = CORPUS / row["input_file"]
    dst_dir = OUT / "p80-promotion-outputs"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / f"p80-{index:03d}-{row['package_id']}-{row['stable_id'].replace(':', '_')}{src.suffix}"
    shutil.copy2(src, dst)
    return dst
def _store_artifact(path: Path) -> dict[str, Any]:
    return store_artifact(path, ARTIFACTS, ROOT)
def _namespaces(root: etree._Element) -> dict[str, str]:
    return {key: value for node in root.iter() for key, value in node.nsmap.items() if key}
def _omml_safe_part(part: str) -> bool:
    return part == "word/document.xml" or part.startswith("ppt/slides/slide")
def _understanding(family: str) -> str:
    return "structural-semantic" if family == "vendor_private_extension" else "office-semantic"
def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT))
def _rel_key(path: str) -> str:
    return str(Path(path).resolve().relative_to(ROOT)) if Path(path).is_absolute() else path
def _office_id(row: dict[str, Any], status: str) -> str:
    return hashlib.sha256(f"{row['output_file']}|{status}".encode()).hexdigest()[:16]
def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    _write_jsonl_artifact(path, rows)
if __name__ == "__main__":
    raise SystemExit(main())
