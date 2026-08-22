"""P85 OMML math semantic editing evidence runner."""

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
from ooxml_operation_engine.omml_ops import read_omml_attr, read_omml_text  # noqa: E402

OUT = Path(__file__).resolve().parent
DENOMINATOR = OUT.parent / "p82" / "sh-semantic-denominator.jsonl"
ARTIFACTS = ROOT / "ooxml-stack" / "release-evidence" / "artifact-blobs"
OPS = ["math.token.set_text", "math.run.set_text", "math.object.metadata.set_value"]
GROUPS = [(fmt, op) for fmt in ("docx", "pptx") for op in OPS]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    rows = _select_rows()
    shutil.rmtree(OUT / "outputs", ignore_errors=True)
    evidence, packages = _run_packages(rows)
    office = _run_office(packages, args.run_office)
    packages = _with_artifacts(packages)
    summary = _summary(evidence, packages, office)
    _write_json("omml-semantic-rows.json", {"rows": evidence})
    _write_json("omml-semantic-summary.json", summary)
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
            if row.get("family") != "math_object" or not _safe_part(row):
                continue
            if not _has_math_text(row):
                continue
            for op in OPS:
                key = (row["format"], op)
                if key not in selected:
                    selected[key] = row | {"operation_id": op}
                    break
            if len(selected) == len(GROUPS):
                break
    missing = [f"{fmt}:{op}" for fmt, op in GROUPS if (fmt, op) not in selected]
    if missing:
        raise RuntimeError(f"P85 row selection missing groups: {missing}")
    return [selected[group] for group in GROUPS]

def _safe_part(row: dict[str, Any]) -> bool:
    part = row.get("part_name", "")
    return part == "word/document.xml" or part.startswith("ppt/slides/slide")

def _has_math_text(row: dict[str, Any]) -> bool:
    try:
        return bool(read_omml_text(_input_path(row), row["part_name"], row["selector"]).strip())
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
    target_path = _selector_element_path(working, row)
    fingerprints_before = _part_fingerprints(working, row["part_name"])
    result = server.handle("ooxml_apply", _payload(row, before, index))
    after = _value(working, row)
    fingerprints_after = _part_fingerprints(working, row["part_name"])
    sibling_changes = _sibling_changes(fingerprints_before, fingerprints_after, target_path)
    validation = result.get("provenance", {}).get("validation", {})
    return _evidence_row(row, output, before, after, sibling_changes, validation)

def _working_path(server: JsonRpcServer) -> Path:
    session = getattr(server, "_session", None)
    if session is None:
        raise RuntimeError("No active session")
    return session.working_path

def _payload(row: dict[str, Any], before: str, index: int) -> dict[str, Any]:
    op_id = row["operation_id"]
    if op_id == "math.object.metadata.set_value":
        params = {"attribute_name": "p85", "value": _after_value(row, before, index)}
    else:
        params = {"text": _after_value(row, before, index)}
    return {"operation_id": op_id, "target": f"{row['part_name']}::{row['selector']}", "params": params}

def _value(path: Path, row: dict[str, Any]) -> str:
    if row["operation_id"] == "math.object.metadata.set_value":
        return read_omml_attr(path, row["part_name"], row["selector"], "p85")
    return read_omml_text(path, row["part_name"], row["selector"])

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
    ns = {"m": "http://schemas.openxmlformats.org/officeDocument/2006/math"}
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
    return sum(1 for path, digest in before.items() if not path.startswith(target_path) and after.get(path) != digest)

def _evidence_row(row, output, before, after, sibling_changes, validation):
    return {
        "row_id": row["row_id"], "format": row["format"], "input_file": row["input_file"],
        "output_file": _rel(output), "package_id": row["package_id"], "part_name": row["part_name"],
        "stable_id": row["stable_id"], "selector": row["selector"], "qname": row["qname"],
        "family": row["family"], "operation_id": row["operation_id"],
        "semantic_model_id": "omml.math.p85.v1", "understanding_level": "office-semantic",
        "before_value": before, "after_value": after, "target_semantic_hit": before != after,
        "sibling_unexpected_semantic_mutation_count": sibling_changes,
        "validation_pass": validation.get("passed") is True,
        "pass": before != after and sibling_changes == 0 and validation.get("passed") is True,
    }

def _run_office(packages: list[dict[str, Any]], enabled: bool) -> dict[str, Any]:
    output = OUT / "omml-semantic-office-open-gate.json"
    if not enabled:
        return {"summary": {"gate_pass": False, "skipped": True}}
    files = [str(ROOT / package["output_file"]) for package in packages]
    cmd = ["uv", "run", "python", "tools/office-open-gate/office_open_gate.py", *files, "--timeout-seconds", "120", "--dialog-wait-seconds", "8", "-o", str(output)]
    subprocess.run(cmd, cwd=ROOT / "ooxml-test-framework", check=True)
    return json.loads(output.read_text(encoding="utf-8"))

def _summary(rows: list[dict[str, Any]], packages: list[dict[str, Any]], office: dict[str, Any]) -> dict[str, Any]:
    office_summary = office.get("summary", {})
    return {
        "claim": "P85 OMML math semantic active editing measured slice; not symbolic algebra or layout parity.",
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
    dst = dst_dir / f"p85-{row['package_id']}{src.suffix}"
    shutil.copy2(src, dst)
    return dst

def _package_row(row: dict[str, Any], output: Path, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    return {"input_file": row["input_file"], "output_file": _rel(output), "row_count": len(evidence), "pass": all(item["pass"] for item in evidence)}

def _with_artifacts(packages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [package | {"artifact": store_artifact(ROOT / package["output_file"], ARTIFACTS, ROOT)} for package in packages]

def _after_value(row: dict[str, Any], before: str, index: int) -> str:
    suffix = hashlib.sha256(f"{row['row_id']}|{row['operation_id']}".encode()).hexdigest()[:8]
    return f"m{index}{suffix}" if before != "" else f"p85-{suffix}"

def _input_path(row: dict[str, Any]) -> Path:
    return ROOT / "ooxml-native-corpus" / row["input_file"]

def _group_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = f"{row['format']}:{row['operation_id']}"
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
