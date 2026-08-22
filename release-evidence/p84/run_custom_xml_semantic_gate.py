"""P84 custom XML semantic editing evidence runner."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from collections import defaultdict
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from lxml import etree

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "ooxml-operation-engine" / "src"))
sys.path.insert(0, str(ROOT / "ooxml-stack" / "scripts"))

from evidence_artifact_store import store_artifact  # noqa: E402
from ooxml_operation_engine.custom_xml_ops import read_custom_xml_value  # noqa: E402
from ooxml_operation_engine.jsonrpc_server import JsonRpcServer  # noqa: E402

OUT = Path(__file__).resolve().parent
DENOMINATOR = OUT.parent / "p82" / "sh-semantic-denominator.jsonl"
ARTIFACTS = ROOT / "ooxml-stack" / "release-evidence" / "artifact-blobs"
GROUPS = [(fmt, fam) for fmt in ("docx", "pptx") for fam in (
    "custom_xml_property", "custom_xml_payload", "custom_xml_schema",
)]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    rows = _select_rows()
    shutil.rmtree(OUT / "outputs", ignore_errors=True)
    evidence, packages = _run_packages(rows)
    office = _run_office(packages, args.run_office)
    packages = _with_artifacts(packages)
    summary = _summary(evidence, packages, office)
    _write_json("custom-xml-semantic-rows.json", {"rows": evidence})
    _write_json("custom-xml-semantic-summary.json", summary)
    return 0 if summary["gate_pass"] else 1

def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-office", action="store_true")
    return parser.parse_args(argv)

def _select_rows() -> list[dict[str, Any]]:
    selected: dict[tuple[str, str], dict[str, Any]] = {}
    with DENOMINATOR.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            key = (row.get("format"), row.get("family"))
            if key in selected or key not in GROUPS:
                continue
            if _is_selectable(row):
                selected[key] = row
            if len(selected) == len(GROUPS):
                break
    missing = [f"{fmt}:{fam}" for fmt, fam in GROUPS if (fmt, fam) not in selected]
    if missing:
        raise RuntimeError(f"P84 row selection missing groups: {missing}")
    return [selected[group] for group in GROUPS]

def _is_selectable(row: dict[str, Any]) -> bool:
    try:
        if row["family"] == "custom_xml_schema":
            return bool(_schema_attribute(row))
        return bool(read_custom_xml_value(_input_path(row), row["part_name"], row["selector"]).strip())
    except Exception:
        return False

def _run_packages(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidence = []
    packages = []
    for package_rows in _rows_by_input(rows).values():
        output = _copy_package(package_rows[0])
        package_evidence = _run_one_package(output, package_rows)
        evidence.extend(package_evidence)
        packages.append(_package_row(package_rows[0], output, package_evidence))
    return evidence, packages

def _run_one_package(output: Path, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    server = JsonRpcServer()
    server.handle("ooxml_open", {"path": str(output)})
    try:
        evidence = [_run_row(server, output, row, index) for index, row in enumerate(rows)]
        server.handle("ooxml_save", {})
        return evidence
    finally:
        try:
            server.handle("ooxml_close", {})
        except Exception:
            server.cleanup()

def _run_row(server: JsonRpcServer, output: Path, row: dict[str, Any], index: int) -> dict[str, Any]:
    working = _working_path(server)
    before = _value(working, row)
    siblings_before = _part_fingerprints(working, row["part_name"])
    target_path = _selector_element_path(working, row["part_name"], row["selector"])
    payload, operation_id, value_kind = _payload(row, before, index)
    result = server.handle("ooxml_apply", payload)
    after = _value(working, row)
    siblings_after = _part_fingerprints(working, row["part_name"])
    sibling_changes = _sibling_changes(siblings_before, siblings_after, target_path)
    validation = result.get("provenance", {}).get("validation", {})
    return _evidence_row(row, output, operation_id, value_kind, before, after, sibling_changes, validation)

def _working_path(server: JsonRpcServer) -> Path:
    session = getattr(server, "_session", None)
    if session is None:
        raise RuntimeError("No active session")
    return session.working_path

def _payload(row: dict[str, Any], before: str, index: int) -> tuple[dict[str, Any], str, str]:
    if row["family"] == "custom_xml_schema":
        attr = _schema_attribute(row)
        params = {"attribute_name": attr, "value": _after_value(row, before, index)}
        return _request(row, "custom_xml.attribute.set_value", row["selector"], params), "custom_xml.attribute.set_value", "attribute"
    if row["family"] == "custom_xml_payload":
        parent = row["selector"].rsplit("/", 1)[0]
        params = {"field_name": _local_name(row["qname"]), "value": _after_value(row, before, index)}
        return _request(row, "custom_xml.field.set_value", parent, params), "custom_xml.field.set_value", "field-text"
    params = {"text": _after_value(row, before, index)}
    return _request(row, "custom_xml.element.set_text", row["selector"], params), "custom_xml.element.set_text", "element-text"

def _request(row: dict[str, Any], op_id: str, selector: str, params: dict[str, str]) -> dict[str, Any]:
    return {"operation_id": op_id, "target": f"{row['part_name']}::{selector}", "params": params}

def _value(path: Path, row: dict[str, Any]) -> str:
    attr = _schema_attribute(row) if row["family"] == "custom_xml_schema" else None
    return read_custom_xml_value(path, row["part_name"], row["selector"], attr)

def _schema_attribute(row: dict[str, Any]) -> str:
    attrs = _node_attrib(_input_path(row), row["part_name"], row["selector"])
    for name in attrs:
        if name.endswith("}fieldsID"):
            return name
    return next(iter(attrs), "")

def _node_attrib(path: Path, part_name: str, selector: str) -> dict[str, str]:
    tree = _tree(path, part_name)
    matches = tree.xpath(selector, namespaces=_namespaces(tree))
    if len(matches) != 1 or not isinstance(matches[0], etree._Element):
        return {}
    return dict(matches[0].attrib)

def _selector_element_path(path: Path, part_name: str, selector: str) -> str:
    tree = _tree(path, part_name)
    matches = tree.xpath(selector, namespaces=_namespaces(tree))
    if len(matches) != 1 or not isinstance(matches[0], etree._Element):
        raise RuntimeError(f"Selector did not resolve uniquely: {selector}")
    return _element_path(matches[0])

def _part_fingerprints(path: Path, part_name: str) -> dict[str, str]:
    tree = _tree(path, part_name)
    return {_element_path(node): _fingerprint(node) for node in tree.getroot().iter()}

def _tree(path: Path, part_name: str) -> etree._ElementTree:
    with ZipFile(path) as zf:
        data = zf.read(part_name)
    parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False)
    return etree.parse(BytesIO(data), parser)

def _namespaces(tree: etree._ElementTree) -> dict[str, str]:
    ns: dict[str, str] = {}
    for node in tree.iter():
        for key, value in node.nsmap.items():
            if key:
                ns.setdefault(key, value)
    return ns

def _element_path(node: etree._Element) -> str:
    parts = []
    while node is not None:
        parent = node.getparent()
        siblings = [] if parent is None else [n for n in parent if n.tag == node.tag]
        index = 1 if parent is None else siblings.index(node) + 1
        parts.append(f"{node.tag}[{index}]")
        node = parent
    return "/" + "/".join(reversed(parts))

def _fingerprint(node: etree._Element) -> str:
    payload = json.dumps({"tag": node.tag, "text": node.text or "", "attrib": dict(node.attrib)}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()

def _sibling_changes(before: dict[str, str], after: dict[str, str], target_path: str) -> int:
    changed = 0
    for path, digest in before.items():
        if path == target_path or after.get(path) == digest:
            continue
        changed += 1
    return changed

def _evidence_row(row, output, op_id, value_kind, before, after, sibling_changes, validation):
    return {
        "row_id": row["row_id"], "format": row["format"], "input_file": row["input_file"],
        "output_file": _rel(output), "package_id": row["package_id"], "part_name": row["part_name"],
        "stable_id": row["stable_id"], "selector": row["selector"], "qname": row["qname"],
        "family": row["family"], "operation_id": op_id, "semantic_model_id": f"{row['family']}.p84.v1",
        "understanding_level": "structural-semantic", "value_kind": value_kind,
        "before_value": before, "after_value": after, "target_semantic_hit": before != after,
        "sibling_unexpected_semantic_mutation_count": sibling_changes,
        "validation_pass": validation.get("passed") is True,
        "pass": before != after and sibling_changes == 0 and validation.get("passed") is True,
    }

def _run_office(packages: list[dict[str, Any]], enabled: bool) -> dict[str, Any]:
    output = OUT / "custom-xml-semantic-office-open-gate.json"
    if not enabled:
        return {"summary": {"gate_pass": False, "skipped": True}}
    files = [str(ROOT / package["output_file"]) for package in packages]
    cmd = ["uv", "run", "python", "tools/office-open-gate/office_open_gate.py", *files, "--timeout-seconds", "120", "--dialog-wait-seconds", "8", "-o", str(output)]
    subprocess.run(cmd, cwd=ROOT / "ooxml-test-framework", check=True)
    return json.loads(output.read_text(encoding="utf-8"))

def _summary(rows: list[dict[str, Any]], packages: list[dict[str, Any]], office: dict[str, Any]) -> dict[str, Any]:
    office_summary = office.get("summary", {})
    return {
        "claim": "P84 custom XML structural-semantic active editing measured slice; not full custom XML denominator completion.",
        "gate_pass": all(row["pass"] for row in rows) and office_summary.get("gate_pass") is True,
        "full_denominator_pass": False, "object_row_count": len(rows),
        "object_row_pass_count": sum(1 for row in rows if row["pass"]),
        "target_semantic_miss_count": sum(1 for row in rows if not row["target_semantic_hit"]),
        "sibling_unexpected_semantic_mutation_count": sum(row["sibling_unexpected_semantic_mutation_count"] for row in rows),
        "validation_failure_count": sum(1 for row in rows if not row["validation_pass"]),
        "native_office_gate_pass": office_summary.get("gate_pass") is True,
        "native_office_pass_count": office_summary.get("pass_total", 0),
        "native_office_total_count": office_summary.get("total", 0),
        "native_office_repair_dialog_count": office_summary.get("repair_dialog_count", 0),
        "native_office_security_dialog_count": office_summary.get("security_dialog_count", 0),
        "native_office_crash_count": office_summary.get("office_crash_count", 0),
        "native_office_timeout_count": office_summary.get("timeout_count", 0),
        "groups": _group_counts(rows), "operations": _operation_counts(rows), "packages": packages,
    }

def _rows_by_input(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["input_file"]].append(row)
    return grouped

def _copy_package(row: dict[str, Any]) -> Path:
    src = _input_path(row)
    dst_dir = OUT / "outputs"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / f"p84-{row['package_id']}{src.suffix}"
    shutil.copy2(src, dst)
    return dst

def _package_row(row: dict[str, Any], output: Path, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    return {"input_file": row["input_file"], "output_file": _rel(output), "row_count": len(evidence), "pass": all(item["pass"] for item in evidence)}

def _with_artifacts(packages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [package | {"artifact": store_artifact(ROOT / package["output_file"], ARTIFACTS, ROOT)} for package in packages]

def _after_value(row: dict[str, Any], before: str, index: int) -> str:
    suffix = hashlib.sha256(row["row_id"].encode()).hexdigest()[:8]
    return f"p84-{index}-{suffix}" if before != "false" else "true"

def _local_name(qname: str) -> str:
    return qname.rsplit("}", 1)[-1] if qname.startswith("{") else qname

def _input_path(row: dict[str, Any]) -> Path:
    return ROOT / "ooxml-native-corpus" / row["input_file"]

def _group_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = f"{row['format']}:{row['family']}"
        counts[key] = counts.get(key, 0) + 1
    return counts

def _operation_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["operation_id"]] = counts.get(row["operation_id"], 0) + 1
    return counts

def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT))
def _write_json(name: str, data: dict[str, Any]) -> None:
    (OUT / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
