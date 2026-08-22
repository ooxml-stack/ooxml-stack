"""P86 VML semantic editing evidence runner."""

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
from ooxml_operation_engine.jsonrpc_server import JsonRpcServer  # noqa: E402
from ooxml_operation_engine.vml_ops import read_vml_value  # noqa: E402

OUT = Path(__file__).resolve().parent
DENOMINATOR = OUT.parent / "p82" / "sh-semantic-denominator.jsonl"
ARTIFACTS = ROOT / "ooxml-stack" / "release-evidence" / "artifact-blobs"
OPS = [
    "vml.shape.text.set", "vml.shape.geometry.set", "vml.shape.fill.set_color",
    "vml.shape.stroke.set_color", "vml.shape.metadata.set_name",
]
BASE_OPS = OPS[:-1]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    rows = _select_rows()
    shutil.rmtree(OUT / "outputs", ignore_errors=True)
    evidence, packages = _run_packages(rows)
    office = _run_office(packages, args.run_office)
    packages = _with_artifacts(packages)
    summary = _summary(evidence, packages, office)
    _write_json("vml-semantic-rows.json", {"rows": evidence})
    _write_json("vml-semantic-summary.json", summary)
    return 0 if summary["gate_pass"] else 1

def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-office", action="store_true")
    return parser.parse_args(argv)

def _select_rows() -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    with DENOMINATOR.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("family") != "vml_drawing" or row.get("format") != "docx":
                continue
            op = _operation_for_row(row)
            if op and op not in selected and _is_selectable(row, op):
                selected[op] = row | {"operation_id": op}
            if len(selected) == len(BASE_OPS):
                break
    missing = [op for op in BASE_OPS if op not in selected]
    if missing:
        raise RuntimeError(f"P86 row selection missing operations: {missing}")
    return [selected[op] for op in BASE_OPS]

def _operation_for_row(row: dict[str, Any]) -> str:
    local = _local(row["qname"])
    if local == "textbox":
        return "vml.shape.text.set"
    if local in {"shape", "rect", "oval", "line"}:
        return "vml.shape.geometry.set" if "geometry" not in row else ""
    if local == "fill":
        return "vml.shape.fill.set_color"
    if local == "stroke":
        return "vml.shape.stroke.set_color"
    return ""

def _is_selectable(row: dict[str, Any], op: str) -> bool:
    try:
        if op == "vml.shape.text.set":
            return bool(_value(_input_path(row), row).strip())
        if op == "vml.shape.metadata.set_name":
            return False
        return True
    except Exception:
        return False

def _run_packages(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = _ensure_metadata_row(rows)
    evidence = []
    packages = []
    for package_rows in _rows_by_input(rows).values():
        output = _copy_package(package_rows[0])
        package_evidence = _run_one_package(output, package_rows)
        evidence.extend(package_evidence)
        packages.append(_package_row(package_rows[0], output, package_evidence))
    return evidence, packages

def _ensure_metadata_row(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if any(row["operation_id"] == "vml.shape.metadata.set_name" for row in rows):
        return rows
    shape = next(row for row in rows if _local(row["qname"]) in {"shape", "rect", "oval", "line"})
    return rows + [shape | {"operation_id": "vml.shape.metadata.set_name"}]

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
    target_path = _selector_element_path(working, row)
    before_fp = _part_fingerprints(working, row["part_name"])
    result = server.handle("ooxml_apply", _payload(row, before, index))
    after = _value(working, row)
    after_fp = _part_fingerprints(working, row["part_name"])
    sibling_changes = _sibling_changes(before_fp, after_fp, target_path)
    validation = result.get("provenance", {}).get("validation", {})
    return _evidence_row(row, output, before, after, sibling_changes, validation)

def _working_path(server: JsonRpcServer) -> Path:
    session = getattr(server, "_session", None)
    if session is None:
        raise RuntimeError("No active session")
    return session.working_path

def _payload(row: dict[str, Any], before: str, index: int) -> dict[str, Any]:
    op = row["operation_id"]
    if op == "vml.shape.text.set":
        params = {"text": _after_token(row, index)}
    elif op == "vml.shape.geometry.set":
        params = {"style": _after_style(before)}
    elif op in {"vml.shape.fill.set_color", "vml.shape.stroke.set_color"}:
        params = {"color": "#00AA66" if before != "#00AA66" else "#0066AA"}
    else:
        params = {"name": _after_token(row, index)}
    return {"operation_id": op, "target": f"{row['part_name']}::{row['selector']}", "params": params}

def _value(path: Path, row: dict[str, Any]) -> str:
    op = row["operation_id"]
    if op == "vml.shape.geometry.set":
        return read_vml_value(path, row["part_name"], row["selector"], "style")
    if op in {"vml.shape.fill.set_color", "vml.shape.stroke.set_color"}:
        return read_vml_value(path, row["part_name"], row["selector"], "color")
    if op == "vml.shape.metadata.set_name":
        return read_vml_value(path, row["part_name"], row["selector"], "id")
    return read_vml_value(path, row["part_name"], row["selector"])

def _selector_element_path(path: Path, row: dict[str, Any]) -> str:
    tree = _tree(path, row["part_name"])
    matches = tree.xpath(row["selector"], namespaces=_namespaces(tree))
    if len(matches) != 1 or not isinstance(matches[0], etree._Element):
        raise RuntimeError(f"Selector did not resolve uniquely: {row['selector']}")
    return _element_path(matches[0])

def _part_fingerprints(path: Path, part_name: str) -> dict[str, str]:
    tree = _tree(path, part_name)
    return {_element_path(node): _fingerprint(node) for node in tree.getroot().iter()}

def _tree(path: Path, part_name: str) -> etree._ElementTree:
    with ZipFile(path) as zf:
        data = zf.read(part_name)
    return etree.parse(BytesIO(data), etree.XMLParser(remove_blank_text=False, resolve_entities=False))

def _namespaces(tree: etree._ElementTree) -> dict[str, str]:
    ns = {"v": "urn:schemas-microsoft-com:vml", "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
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
        parts.append(f"{node.tag}[{1 if parent is None else siblings.index(node) + 1}]")
        node = parent
    return "/" + "/".join(reversed(parts))

def _fingerprint(node: etree._Element) -> str:
    payload = json.dumps({"tag": node.tag, "text": node.text or "", "attrib": dict(node.attrib)}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()

def _sibling_changes(before: dict[str, str], after: dict[str, str], target_path: str) -> int:
    return sum(1 for path, digest in before.items() if not path.startswith(target_path) and after.get(path) != digest)

def _evidence_row(row, output, before, after, sibling_changes, validation):
    return {
        "row_id": row["row_id"], "format": row["format"], "input_file": row["input_file"],
        "output_file": _rel(output), "package_id": row["package_id"], "part_name": row["part_name"],
        "stable_id": row["stable_id"], "selector": row["selector"], "qname": row["qname"],
        "family": row["family"], "operation_id": row["operation_id"], "semantic_model_id": "vml.drawing.p86.v1",
        "understanding_level": "office-semantic", "before_value": before, "after_value": after,
        "target_semantic_hit": before != after, "sibling_unexpected_semantic_mutation_count": sibling_changes,
        "validation_pass": validation.get("passed") is True,
        "pass": before != after and sibling_changes == 0 and validation.get("passed") is True,
    }

def _run_office(packages: list[dict[str, Any]], enabled: bool) -> dict[str, Any]:
    output = OUT / "vml-semantic-office-open-gate.json"
    if not enabled:
        return {"summary": {"gate_pass": False, "skipped": True}}
    files = [str(ROOT / package["output_file"]) for package in packages]
    cmd = ["uv", "run", "python", "tools/office-open-gate/office_open_gate.py", *files, "--timeout-seconds", "120", "--dialog-wait-seconds", "8", "-o", str(output)]
    subprocess.run(cmd, cwd=ROOT / "ooxml-test-framework", check=True)
    return json.loads(output.read_text(encoding="utf-8"))

def _summary(rows: list[dict[str, Any]], packages: list[dict[str, Any]], office: dict[str, Any]) -> dict[str, Any]:
    office_summary = office.get("summary", {})
    return {
        "claim": "P86 VML drawing semantic active editing measured DOCX slice.",
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
        "operations": _operation_counts(rows), "packages": packages,
    }

def _rows_by_input(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["input_file"]].append(row)
    return grouped

def _copy_package(row: dict[str, Any]) -> Path:
    src = _input_path(row); dst_dir = OUT / "outputs"; dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / f"p86-{row['package_id']}{src.suffix}"; shutil.copy2(src, dst); return dst

def _package_row(row: dict[str, Any], output: Path, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    return {"input_file": row["input_file"], "output_file": _rel(output), "row_count": len(evidence), "pass": all(item["pass"] for item in evidence)}

def _with_artifacts(packages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [package | {"artifact": store_artifact(ROOT / package["output_file"], ARTIFACTS, ROOT)} for package in packages]

def _after_style(style: str) -> str:
    return style.replace("width:297pt", "width:298pt") if "width:297pt" in style else style + ";width:298pt"

def _after_token(row: dict[str, Any], index: int) -> str:
    return f"p86-{index}-{hashlib.sha256(row['row_id'].encode()).hexdigest()[:8]}"

def _local(qname: str) -> str:
    return qname.rsplit("}", 1)[-1] if qname.startswith("{") else qname

def _input_path(row: dict[str, Any]) -> Path:
    return ROOT / "ooxml-native-corpus" / row["input_file"]

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
