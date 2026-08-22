"""P87 chart and Office extension semantic editing evidence runner."""
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
from ooxml_operation_engine.chart_ops import read_chart_value  # noqa: E402
from ooxml_operation_engine.jsonrpc_server import JsonRpcServer  # noqa: E402
OUT = Path(__file__).resolve().parent
DENOMINATOR = OUT.parent / "p82" / "sh-semantic-denominator.jsonl"
ARTIFACTS = ROOT / "ooxml-stack" / "release-evidence" / "artifact-blobs"
TITLE = "/c:chartSpace/c:chart/c:title[1]"
SERIES = "//c:ser[1]/c:tx[1]"
def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    rows, gaps = _select_rows()
    shutil.rmtree(OUT / "outputs", ignore_errors=True)
    evidence, packages = _run_packages(rows)
    office = _run_office(packages, args.run_office)
    packages = _with_artifacts(packages)
    summary = _summary(evidence, packages, office, gaps)
    _write_json("chart-extension-semantic-rows.json", {"rows": evidence})
    _write_json("chart-extension-semantic-summary.json", summary)
    return 0 if summary["gate_pass"] else 1
def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-office", action="store_true")
    return parser.parse_args(argv)
def _select_rows() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    native_axis_title_found = False
    for row in _denominator_rows():
        if row.get("family") == "chart_drawing":
            _maybe_select_chart_drawing(selected, row)
        if row.get("family") in {"office_chart_extension", "office_extension"}:
            _maybe_select_office_extension(selected, row)
        if _is_chart_part(row):
            _maybe_select_chart_text(selected, row)
            native_axis_title_found = native_axis_title_found or _has_axis_title(row)
    required = [
        "chart.title.set_text", "chart.series_label.set_text",
        "docx:chart.drawing.metadata.set_value", "pptx:chart.drawing.metadata.set_value",
        "office_chart_extension.known_metadata", "office_extension.known_metadata",
    ]
    missing = [key for key in required if key not in selected]
    if missing:
        raise RuntimeError(f"P87 row selection missing groups: {missing}")
    return [selected[key] for key in required], {"native_axis_title_found": native_axis_title_found}
def _denominator_rows() -> list[dict[str, Any]]:
    rows = []
    with DENOMINATOR.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("family") in {"chart_drawing", "office_chart_extension", "office_extension"}:
                rows.append(row)
    return rows
def _maybe_select_chart_text(selected: dict[str, dict[str, Any]], row: dict[str, Any]) -> None:
    if "chart.title.set_text" not in selected and _text_at(row, TITLE):
        selected["chart.title.set_text"] = _derived(row, "chart.title.set_text", TITLE, None)
    if "chart.series_label.set_text" not in selected and _text_at(row, SERIES):
        selected["chart.series_label.set_text"] = _derived(row, "chart.series_label.set_text", SERIES, None)
def _maybe_select_chart_drawing(selected: dict[str, dict[str, Any]], row: dict[str, Any]) -> None:
    key = f"{row.get('format')}:chart.drawing.metadata.set_value"
    if key not in selected and row.get("format") in {"docx", "pptx"}:
        attr = _first_attr(row)
        if attr:
            selected[key] = _derived(row, "chart.drawing.metadata.set_value", row["selector"], attr)
def _maybe_select_office_extension(selected: dict[str, dict[str, Any]], row: dict[str, Any]) -> None:
    key = f"{row['family']}.known_metadata"
    if key in selected:
        return
    if row["family"] == "office_extension" and row.get("format") == "docx" and row.get("package_id") != "docx_ms_expansion_110_testchartoleobjectembeddings":
        return
    attr = _first_attr(row)
    if attr:
        selected[key] = _derived(row, "office_extension.known_metadata.set_value", row["selector"], attr)
def _derived(row: dict[str, Any], op: str, selector: str, attr: str | None) -> dict[str, Any]:
    basis = f"{row['row_id']}|{op}|{selector}|{attr or ''}"
    stable_id = f"p87:{hashlib.sha256(basis.encode()).hexdigest()[:16]}"
    return row | {
        "source_row_id": row["row_id"], "source_stable_id": row["stable_id"],
        "row_id": f"p87|{row['package_id']}|{row['part_name']}|{stable_id}",
        "stable_id": stable_id, "operation_id": op, "selector": selector,
        "attribute_name": attr or "", "target_family": _target_family(op, row),
    }
def _target_family(op: str, row: dict[str, Any]) -> str:
    if op.startswith("chart.title"):
        return "chart_title"
    if op.startswith("chart.series"):
        return "chart_series_label"
    return row["family"]
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
        evidence = [_run_row(server, output, row, i) for i, row in enumerate(rows)]
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
def _payload(row: dict[str, Any], before: str, index: int) -> dict[str, Any]:
    op = row["operation_id"]
    value = _after_value(row, before, index)
    params = {"text": value} if op.endswith("set_text") else {"attribute_name": row["attribute_name"], "value": value}
    return {"operation_id": op, "target": f"{row['part_name']}::{row['selector']}", "params": params}
def _value(path: Path, row: dict[str, Any]) -> str:
    attr = row.get("attribute_name") or None
    return read_chart_value(path, row["part_name"], row["selector"], attr)
def _text_at(row: dict[str, Any], selector: str) -> bool:
    try:
        return bool(read_chart_value(_input_path(row), row["part_name"], selector).strip())
    except Exception:
        return False
def _has_axis_title(row: dict[str, Any]) -> bool:
    return _text_at(row, "//c:valAx/c:title[1] | //c:catAx/c:title[1] | //c:dateAx/c:title[1]")
def _first_attr(row: dict[str, Any]) -> str:
    try:
        attrs = list(_node(row).attrib)
        for attr in attrs:
            if not _unsafe_attr(attr):
                return attr
        return ""
    except Exception:
        return ""
def _unsafe_attr(attr: str) -> bool:
    low = attr.lower()
    return any(token in low for token in ("rel", "id", "minver", "macro", "textlink"))
def _node(row: dict[str, Any]) -> etree._Element:
    tree = _tree(_input_path(row), row["part_name"])
    matches = tree.xpath(row["selector"], namespaces=_namespaces(tree))
    if len(matches) != 1 or not isinstance(matches[0], etree._Element):
        raise RuntimeError(f"Selector did not resolve uniquely: {row['selector']}")
    return matches[0]
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
    ns = {"c": "http://schemas.openxmlformats.org/drawingml/2006/chart", "a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
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
        "row_id": row["row_id"], "source_row_id": row["source_row_id"], "format": row["format"],
        "input_file": row["input_file"], "output_file": _rel(output), "package_id": row["package_id"],
        "part_name": row["part_name"], "stable_id": row["stable_id"], "source_stable_id": row["source_stable_id"],
        "selector": row["selector"], "qname": row["qname"], "family": row["target_family"],
        "source_family": row["family"], "operation_id": row["operation_id"],
        "semantic_model_id": "chart.office_extension.p87.v1", "understanding_level": "office-semantic",
        "before_value": before, "after_value": after, "target_semantic_hit": before != after,
        "sibling_unexpected_semantic_mutation_count": sibling_changes,
        "validation_pass": validation.get("passed") is True,
        "pass": before != after and sibling_changes == 0 and validation.get("passed") is True,
    }
def _run_office(packages: list[dict[str, Any]], enabled: bool) -> dict[str, Any]:
    output = OUT / "chart-extension-semantic-office-open-gate.json"
    if not enabled:
        return {"summary": {"gate_pass": False, "skipped": True}}
    files = [str(ROOT / package["output_file"]) for package in packages]
    cmd = ["uv", "run", "python", "tools/office-open-gate/office_open_gate.py", *files, "--timeout-seconds", "120", "--dialog-wait-seconds", "8", "-o", str(output)]
    subprocess.run(cmd, cwd=ROOT / "ooxml-test-framework", check=True)
    return json.loads(output.read_text(encoding="utf-8"))
def _summary(rows: list[dict[str, Any]], packages: list[dict[str, Any]], office: dict[str, Any], gaps: dict[str, Any]) -> dict[str, Any]:
    office_summary = office.get("summary", {})
    return {
        "claim": "P87 chart/Office extension semantic active editing measured native slice; not chart data/cache recomputation.",
        "gate_pass": all(row["pass"] for row in rows) and office_summary.get("gate_pass") is True,
        "full_denominator_pass": False, "full_operation_list_pass": gaps["native_axis_title_found"],
        "native_axis_title_evidence_count": 1 if gaps["native_axis_title_found"] else 0,
        "object_row_count": len(rows), "object_row_pass_count": sum(1 for row in rows if row["pass"]),
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
        "operations": _operation_counts(rows), "groups": _group_counts(rows), "packages": packages,
    }
def _rows_by_input(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["input_file"]].append(row)
    return grouped
def _copy_package(row: dict[str, Any]) -> Path:
    src = _input_path(row); dst_dir = OUT / "outputs"; dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / f"p87-{row['package_id']}{src.suffix}"; shutil.copy2(src, dst); return dst
def _package_row(row: dict[str, Any], output: Path, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    return {"input_file": row["input_file"], "output_file": _rel(output), "row_count": len(evidence), "pass": all(item["pass"] for item in evidence)}
def _with_artifacts(packages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [package | {"artifact": store_artifact(ROOT / package["output_file"], ARTIFACTS, ROOT)} for package in packages]
def _after_value(row: dict[str, Any], before: str, index: int) -> str:
    if not row["operation_id"].endswith("set_text"):
        if before in {"0", "1"}:
            return "1" if before == "0" else "0"
        if before.isdigit():
            return str(int(before) + 1)
    suffix = hashlib.sha256(f"{row['row_id']}|{index}".encode()).hexdigest()[:8]
    return f"p87-{suffix}" if before != "p87-fixed" else f"p87-{suffix}-2"
def _is_chart_part(row: dict[str, Any]) -> bool:
    return "/charts/" in row.get("part_name", "") and row.get("part_name", "").endswith(".xml")
def _working_path(server: JsonRpcServer) -> Path:
    session = getattr(server, "_session", None)
    if session is None:
        raise RuntimeError("No active session")
    return session.working_path
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
