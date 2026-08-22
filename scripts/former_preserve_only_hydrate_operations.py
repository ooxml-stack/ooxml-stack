from __future__ import annotations
import json
from collections import Counter
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZipFile
from lxml import etree
from former_preserve_only_cover_page import hydration_contract as cover_page_contract, is_candidate as is_cover_page_candidate
from former_preserve_only_math_policy import math_presence_contract, math_presence_operation
from former_preserve_only_numeric_leaf import numeric_attribute_operation, numeric_leaf_operation
from former_preserve_only_ole import hydration_contract as ole_contract, is_candidate as is_ole_candidate
from former_preserve_only_p14_presence import p14_presence_contract, p14_presence_operation
from former_preserve_only_picture_effect_presence import picture_effect_presence_contract, picture_effect_presence_operation
from former_preserve_only_vml_stroke import hydration_contract as vml_stroke_contract, is_candidate as is_vml_stroke_candidate
ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT.parent / "ooxml-native-corpus"
OUT = ROOT / "release-evidence/former-preserve-only-semantic-editability"
LEDGER = OUT / "gap-ledger.jsonl"
HYDRATED = OUT / "operation-hydration-ledger.jsonl"
SUMMARY = OUT / "operation-hydration-summary.json"
MC_CHOICE = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Choice"
O_EXTRUSIONOK = "{urn:schemas-microsoft-com:office:office}extrusionok"
W10_ANCHORLOCK = "{urn:schemas-microsoft-com:office:word}anchorlock"
ANCHORLOCK_PRESENCE_OP = "legacy_office_drawing.anchorlock.presence.set_enabled"; VML_ON_OPS = {"shadow": "vml.shadow.set_enabled", "textpath": "vml.textpath.set_enabled"}
W14_NO_FILL, W14_BEVEL = "{http://schemas.microsoft.com/office/word/2010/wordml}noFill", "{http://schemas.microsoft.com/office/word/2010/wordml}bevel"
W14_CONTEXTUAL_ALTERNATES, W14_TEXT_OUTLINE = "{http://schemas.microsoft.com/office/word/2010/wordml}cntxtAlts", "{http://schemas.microsoft.com/office/word/2010/wordml}textOutline"
W_RUN_PROPERTIES = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}rPr"
NO_FILL_PRESENCE_OP = "office_extension.no_fill.presence.set_enabled"
BEVEL_PRESENCE_OP = "office_extension.text_outline.bevel.presence.set_enabled"
CONTEXTUAL_ALTERNATES_PRESENCE_OP = "office_extension.contextual_alternates.presence.set_enabled"
W14_PRESENCE_OPS = {W14_NO_FILL: NO_FILL_PRESENCE_OP, W14_BEVEL: BEVEL_PRESENCE_OP, W14_CONTEXTUAL_ALTERNATES: CONTEXTUAL_ALTERNATES_PRESENCE_OP}
TEXT_OPS = {
    "custom_xml_payload": "custom_xml.element.set_text",
    "vendor_private_extension": "vendor_private.text_node.set_value",
}
ATTR_OPS = {
    "custom_xml_schema": "custom_xml.attribute.set_value",
    "custom_xml_property": "custom_xml.attribute.set_value",
    "wps_extension": "wps_extension.known_field.set_value",
    "office_extension": "office_extension.known_metadata.set_value",
    "office_chart_extension": "office_extension.known_metadata.set_value",
    "legacy_office_drawing": "office_extension.known_metadata.set_value",
    "sharepoint_property": "office_extension.known_metadata.set_value",
    "chart_drawing": "chart.drawing.metadata.set_value",
    "vendor_private_extension": "vendor_private.attribute.set_value",
}
DEFAULT_ATTRS = {
    "{http://schemas.microsoft.com/office/drawing/2010/main}useLocalDpi": "val",
    "{http://schemas.microsoft.com/office/drawing/2008/diagram}cNvSpPr": "txBox",
    "{http://schemas.microsoft.com/office/word/2010/wordprocessingShape}cNvSpPr": "txBox",
    "{http://schemas.openxmlformats.org/drawingml/2006/chartDrawing}cNvSpPr": "txBox",
    "{http://schemas.openxmlformats.org/officeDocument/2006/math}dispDef": "val",
    "{http://schemas.microsoft.com/office/word/2012/wordml}chartTrackingRefBased": "val",
    "{http://schemas.microsoft.com/office/drawing/2010/main}shadowObscured": "val",
    "{http://schemas.microsoft.com/office/word/2010/wordml}round": "val",
}
REQUIRES_PREFIX_CANDIDATES = ("a14", "w14", "wps", "wpg", "wpc", "c14", "cx1", "cx2", "p14", "v", "o", "a", "p", "w")
def main() -> int:
    if not LEDGER.exists():
        print(f"missing local cache: {LEDGER}\nrun: make campaign-gap-ledger", flush=True)
        return 2
    cache: dict[tuple[str, str], tuple[etree._ElementTree, dict[str, str]]] = {}
    nodes: dict[tuple[str, str, str], etree._Element] = {}
    rows = [_hydrate(row, cache, nodes) for row in _read_jsonl(LEDGER)]
    summary = _summary(rows)
    _write_jsonl(HYDRATED, rows)
    _write_json(SUMMARY, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0
def _hydrate(row: dict[str, Any], cache: dict[tuple[str, str], tuple[etree._ElementTree, dict[str, str]]], nodes: dict[tuple[str, str, str], etree._Element]) -> dict[str, Any]:
    if is_cover_page_candidate(row):
        try:
            tree, node = _node(row, cache, nodes)
            return row | cover_page_contract(row, tree, node)
        except Exception as exc:  # noqa: BLE001
            return row | {"operation_hydration_status": "unresolved", "operation_hydration_error": f"{type(exc).__name__}: {exc}"}
    if _presence_operation(row):
        try:
            tree, node = _node(row, cache, nodes)
            return row | _presence_contract(row, tree, node)
        except Exception as exc:  # noqa: BLE001
            return row | {"operation_hydration_status": "unresolved", "operation_hydration_error": f"{type(exc).__name__}: {exc}"}
    if row.get("blocker_type") != "semantic_value_available_pending_proof":
        return row | {"operation_hydration_status": "not_applicable"}
    try:
        tree, node = _node(row, cache, nodes)
        return row | _contract(row, tree, node)
    except Exception as exc:  # noqa: BLE001
        return row | {"operation_hydration_status": "unresolved", "operation_hydration_error": f"{type(exc).__name__}: {exc}"}
def _contract(row: dict[str, Any], tree: etree._ElementTree, node: etree._Element) -> dict[str, Any]:
    if is_ole_candidate(row):
        return ole_contract(tree, node)
    if is_vml_stroke_candidate(row):
        return vml_stroke_contract(tree, node)
    if row["family"] == "alternate_content":
        return _alternate_contract(row, node)
    target = _value_target(row, node)
    attr = _attr_name(row, target)
    if attr:
        op = _attr_operation(row, target, attr)
        return _attr_contract(row, tree, target, attr, op) if op else _unsupported(row, "no_attribute_operation", attr)
    if _text(target):
        op = _text_operation(row, target)
        if op == "custom_xml.element.set_text" and list(target):
            return _unsupported(row, "text_target_has_child_elements")
        return _text_contract(row, tree, target, op) if op else _unsupported(row, "no_text_operation")
    return _unsupported(row, "no_semantic_target")
def _alternate_contract(row: dict[str, Any], node: etree._Element) -> dict[str, Any]:
    choice = next((child for child in node if child.tag == MC_CHOICE), None)
    if choice is None or not choice.get("Requires"):
        return _unsupported(row, "missing_choice_requires")
    before = choice.get("Requires", "")
    requested = _requires_requested(before, choice)
    if requested == before:
        return _unsupported(row, "no_requires_mutation_prefix")
    return {
        "operation_hydration_status": "hydrated",
        "operation_id": "alternate_content.choice.metadata.set_value",
        "operation_target_selector": row["selector"],
        "attribute_name": "Requires",
        "value_kind": "attribute",
        "before_semantic_value": before,
        "requested_semantic_value": requested,
    }
def _is_anchorlock_presence_row(row: dict[str, Any]) -> bool:
    return (
        row.get("family") == "legacy_office_drawing"
        and row.get("qname") == W10_ANCHORLOCK
        and row.get("semantic_value_kind") == "no_descendant_value"
    )
def _presence_operation(row: dict[str, Any]) -> str:
    if operation := math_presence_operation(row):
        return operation
    if operation := picture_effect_presence_operation(row):
        return operation
    if operation := p14_presence_operation(row):
        return operation
    if _is_anchorlock_presence_row(row):
        return ANCHORLOCK_PRESENCE_OP
    if row.get("family") == "office_extension" and row.get("qname") in W14_PRESENCE_OPS and row.get("semantic_value_kind") == "no_descendant_value":
        return W14_PRESENCE_OPS[row["qname"]]
    return ""
def _presence_contract(row: dict[str, Any], tree: etree._ElementTree, node: etree._Element) -> dict[str, Any]:
    operation = _presence_operation(row)
    if operation == math_presence_operation(row):
        return math_presence_contract(row, tree, node)
    if operation == picture_effect_presence_operation(row):
        return picture_effect_presence_contract(row, tree, node)
    if operation == p14_presence_operation(row):
        return p14_presence_contract(row, tree, node)
    expected_parent = W_RUN_PROPERTIES if operation == CONTEXTUAL_ALTERNATES_PRESENCE_OP else W14_TEXT_OUTLINE
    if operation in W14_PRESENCE_OPS.values() and (node.getparent() is None or node.getparent().tag != expected_parent):
        return _unsupported(row, "w14_presence_requires_text_outline_parent")
    return _empty_presence_contract(row, tree, node, operation)
def _empty_presence_contract(row: dict[str, Any], tree: etree._ElementTree, node: etree._Element, operation: str) -> dict[str, Any]:
    expected = W10_ANCHORLOCK if operation == ANCHORLOCK_PRESENCE_OP else next(qname for qname, op in W14_PRESENCE_OPS.items() if op == operation)
    if node.tag != expected or len(node) or node.attrib or (node.text or "").strip():
        return _unsupported(row, "anchorlock_presence_requires_empty_target")
    return {
        "operation_hydration_status": "hydrated",
        "operation_id": operation,
        "operation_target_selector": tree.getpath(node),
        "value_kind": "presence",
        "before_semantic_value": "true",
        "requested_semantic_value": "false",
    }
def _requires_requested(before: str, choice: etree._Element) -> str:
    prefixes = before.split()
    for prefix in REQUIRES_PREFIX_CANDIDATES:
        if prefix in choice.nsmap and prefix not in prefixes:
            return " ".join(prefixes + [prefix])
    return before
def _value_target(row: dict[str, Any], node: etree._Element) -> etree._Element:
    kind = row.get("semantic_value_kind")
    if kind in {"descendant_attr", "descendant_text"}:
        return _descendant_target(node, kind)
    return node
def _descendant_target(node: etree._Element, kind: str) -> etree._Element:
    for child in node.iterdescendants():
        if kind == "descendant_attr" and _safe_attr(child):
            return child
        if kind == "descendant_text" and _text(child):
            return child
    raise ValueError(f"no {kind} target")
def _attr_name(row: dict[str, Any], node: etree._Element) -> str:
    if row.get("semantic_value_kind") == "direct_vml_path_metadata":
        return O_EXTRUSIONOK
    if row.get("semantic_value_kind") == "direct_creation_id":
        return "id" if "id" in node.attrib else "val" if "val" in node.attrib else ""
    return DEFAULT_ATTRS.get(node.tag, "") or _safe_attr(node)
def _attr_operation(row: dict[str, Any], node: etree._Element, attr: str) -> str:
    if operation := numeric_attribute_operation(row, attr): return operation
    family = row["family"]
    if family == "math_object":
        return "math.object.metadata.set_value"
    if family == "vml_drawing":
        return _vml_operation(node, attr)
    if row.get("semantic_value_kind") == "direct_creation_id":
        return "office_extension.creation_id.set"
    return ATTR_OPS.get(family, "")
def _text_operation(row: dict[str, Any], node: etree._Element) -> str:
    if operation := numeric_leaf_operation(row):
        return operation
    if row["family"] == "math_object":
        return "math.token.set_text" if etree.QName(node).localname == "t" else "math.run.set_text"
    if row["family"] == "vml_drawing":
        return "vml.shape.text.set"
    return TEXT_OPS.get(row["family"], "")
def _vml_operation(node: etree._Element, attr: str) -> str:
    local = etree.QName(node).localname
    attr_local = attr.rsplit("}", 1)[-1].split(":", 1)[-1]
    if local == "f" and attr_local == "eqn":
        return "vml.formula.eqn.set_value"
    if local == "path" and attr in {O_EXTRUSIONOK, "arrowok", "fillok", "gradientshapeok", "textpathok"}: return "vml.path.metadata.set_value"
    if attr == "on" and local in VML_ON_OPS: return VML_ON_OPS[local]
    if local == "imagedata" and attr == "{urn:schemas-microsoft-com:office:office}title": return "vml.image.metadata.set_title"
    if attr_local in {"color", "fillcolor"} and local in {"fill", "shape"}:
        return "vml.shape.fill.set_color"
    if attr_local in {"color", "strokecolor"} and local in {"stroke", "shape"}:
        return "vml.shape.stroke.set_color"
    if attr == "style":
        return "vml.shape.geometry.set"
    return "vml.shape.metadata.set_name" if attr == "id" else ""
def _attr_contract(row, tree, node, attr, op) -> dict[str, Any]:
    if op == "vml.path.metadata.set_value" and node.get(attr, "") == "":
        return _unsupported(row, "vml_path_metadata_requires_explicit_source_value")
    return {
        "operation_hydration_status": "hydrated",
        "operation_id": op,
        "operation_target_selector": tree.getpath(node),
        "attribute_name": attr,
        "value_kind": "attribute",
        "before_semantic_value": node.get(attr, ""),
    }
def _text_contract(row, tree, node, op) -> dict[str, Any]:
    return {
        "operation_hydration_status": "hydrated",
        "operation_id": op,
        "operation_target_selector": tree.getpath(node),
        "value_kind": "text",
        "before_semantic_value": _text(node),
    }
def _unsupported(row: dict[str, Any], reason: str, attr: str = "") -> dict[str, Any]:
    return {"operation_hydration_status": "unsupported_mapping", "operation_hydration_reason": reason} | ({"attribute_name": attr} if attr else {})
def _node(
    row: dict[str, Any],
    cache: dict[tuple[str, str], tuple[etree._ElementTree, dict[str, str]]],
    nodes: dict[tuple[str, str, str], etree._Element],
) -> tuple[etree._ElementTree, etree._Element]:
    key = (row["input_file"], row["part_name"], row["selector"])
    tree, namespaces = _part(row, cache)
    if key not in nodes:
        nodes[key] = _single(tree, row["selector"], namespaces)
    return tree, nodes[key]
def _part(row: dict[str, Any], cache: dict[tuple[str, str], tuple[etree._ElementTree, dict[str, str]]]) -> tuple[etree._ElementTree, dict[str, str]]:
    key = (row["input_file"], row["part_name"])
    if key in cache:
        return cache[key]
    with ZipFile(CORPUS / row["input_file"]) as package:
        tree = etree.parse(BytesIO(package.read(row["part_name"])), etree.XMLParser(remove_blank_text=False, resolve_entities=False))
    cache[key] = (tree, _namespaces(tree.getroot()))
    return cache[key]
def _single(tree: etree._ElementTree, selector: str, namespaces: dict[str, str]) -> etree._Element:
    matches = tree.xpath(selector, namespaces=namespaces)
    if len(matches) != 1 or not isinstance(matches[0], etree._Element):
        raise ValueError(f"selector matched {len(matches)}")
    return matches[0]
def _namespaces(root: etree._Element) -> dict[str, str]:
    return {key: value for node in root.iter() for key, value in node.nsmap.items() if key}
def _safe_attr(node: etree._Element) -> str:
    for name in node.attrib:
        low = name.lower()
        local = low.rsplit("}", 1)[-1]
        if local != "id" and not any(token in low for token in ("rel", "macro", "textlink", "minver")):
            return name
    return ""
def _text(node: etree._Element) -> str:
    return " ".join("".join(node.itertext()).split())
def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(row.get("operation_hydration_status") for row in rows)
    hydrated = [row for row in rows if row.get("operation_hydration_status") == "hydrated"]
    return {
        "schema_version": "former-preserve-only-operation-hydration-v1",
        "row_count": len(rows),
        "hydrated_count": len(hydrated),
        "status_counts": dict(sorted(statuses.items())),
        "hydrated_by_family": dict(Counter(row["family"] for row in hydrated).most_common()),
        "hydrated_by_operation": dict(Counter(row["operation_id"] for row in hydrated).most_common()),
        "unsupported_by_family": dict(Counter(row["family"] for row in rows if row.get("operation_hydration_status") == "unsupported_mapping").most_common()),
}
if __name__ == "__main__":
    raise SystemExit(main())
