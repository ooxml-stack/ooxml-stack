"""Extra P80 promotion plans for structural semantic objects."""

from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from lxml import etree

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "ooxml-native-corpus"
MC_CHOICE = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Choice"
GUARD_PREFIXES = ("p15", "p14", "a14", "wp14", "v", "c16r2")
VML_DRAWING = "vml_drawing"
SCHEME_COLORS = (
    "accent1", "accent2", "accent3", "accent4", "accent5", "accent6",
    "tx1", "tx2", "bg1", "bg2", "dk1", "lt1", "dk2", "lt2", "hlink", "folHlink",
)
OMML_JC_VALUES = ("left", "center", "right", "centerGroup")
DIRECTION_VALUES = ("l", "r", "u", "d")
IN_OUT_VALUES = ("in", "out")
BW_MODE_VALUES = ("clr", "auto", "gray", "ltGray", "invGray", "grayWhite", "blackGray", "blackWhite", "black", "white", "hidden")
ANCHOR_VALUES = ("t", "ctr", "b")
DEFAULT_ATTRS = {
    "{http://schemas.microsoft.com/office/drawing/2008/diagram}cNvSpPr": ("office_extension.known_metadata.set_value", "txBox"),
    "{http://schemas.microsoft.com/office/word/2010/wordprocessingShape}cNvSpPr": ("office_extension.known_metadata.set_value", "txBox"),
    "{http://schemas.openxmlformats.org/drawingml/2006/chartDrawing}cNvSpPr": ("chart.drawing.metadata.set_value", "txBox"),
    "{http://schemas.openxmlformats.org/officeDocument/2006/math}dispDef": ("math.object.metadata.set_value", "val"),
    "{http://schemas.microsoft.com/office/word/2012/wordml}chartTrackingRefBased": ("office_extension.known_metadata.set_value", "val"),
    "{http://schemas.microsoft.com/office/drawing/2010/main}shadowObscured": ("office_extension.known_metadata.set_value", "val"),
    "{http://schemas.microsoft.com/office/word/2010/wordml}round": ("office_extension.known_metadata.set_value", "val"),
}


def extra_plan(row: dict[str, Any]) -> dict[str, Any] | None:
    default = _default_attr_plan(row)
    if default is not None:
        return default
    if row.get("family") == VML_DRAWING:
        return _vml_plan(row)
    return _alternate_plan(row) if row.get("family") == "alternate_content" else None


def extra_params(plan: dict[str, Any], value: str) -> dict[str, str] | None:
    op = plan["operation_id"]
    if op in {"vml.shape.fill.set_color", "vml.shape.stroke.set_color"}:
        return {"color": value}
    if op == "vml.shape.text.set":
        return {"text": value}
    if op == "vml.shape.geometry.set":
        return {"style": value}
    if op == "vml.shape.metadata.set_name":
        return {"name": value}
    if op == "alternate_content.choice.metadata.set_value":
        return {"attribute_name": plan["attribute_name"], "value": value}
    return None


def extra_request_value(before: str, plan: dict[str, Any], index: int) -> str | None:
    op = plan["operation_id"]
    if op == "office_extension.known_metadata.set_value":
        return _known_metadata_value(before, plan, index)
    if plan.get("default_boolean_attr") is True:
        return "0" if before.lower() in {"1", "true"} else "1"
    if op.startswith("alternate_content."):
        return alternate_requires_value(before)
    if op in {"vml.shape.fill.set_color", "vml.shape.stroke.set_color"}:
        return _next_color(before, index)
    if op == "vml.shape.text.set":
        return before + f" p90v{index}" if before.strip() else f"p90v{index}"
    if op == "vml.shape.geometry.set":
        return _next_style(before, index)
    if op == "vml.shape.metadata.set_name":
        return before + f"-p90v{index}" if before.strip() else f"p90v{index}"
    return None


def _known_metadata_value(before: str, plan: dict[str, Any], index: int) -> str:
    attr = plan.get("attribute_name", "")
    low = before.lower()
    if before in {"horz", "vert"}:
        return "vert" if before == "horz" else "horz"
    if low in {"true", "false"}:
        return "false" if low == "true" else "true"
    if attr in {"spcFirstLastPara", "txBox"} and before in {"", "0", "1"}:
        return "0" if before == "1" else "1"
    if _braced_guid(before):
        return _next_guid(before, index)
    if _hex_color(before):
        return _next_color(before, index)
    if _signed_int(before):
        return str(int(before) + index + 1)
    if before in SCHEME_COLORS:
        return _next_enum(before, SCHEME_COLORS, index)
    if before in OMML_JC_VALUES:
        return _next_enum(before, OMML_JC_VALUES, index)
    if attr in {"name", "userId"}:
        return before + f" p90s{index}" if before.strip() else f"p90s{index}"
    if attr == "dir" and before in DIRECTION_VALUES:
        return _next_enum(before, DIRECTION_VALUES, index)
    if attr == "dir" and before in IN_OUT_VALUES:
        return _next_enum(before, IN_OUT_VALUES, index)
    if attr == "bwMode" and before in BW_MODE_VALUES:
        return _next_enum(before, BW_MODE_VALUES, index)
    if attr == "anchor" and before in ANCHOR_VALUES:
        return _next_enum(before, ANCHOR_VALUES, index)
    return before


def _next_enum(before: str, values: tuple[str, ...], index: int) -> str:
    shift = (index % (len(values) - 1)) + 1
    return values[(values.index(before) + shift) % len(values)]


def _braced_guid(value: str) -> bool:
    return len(value) == 38 and value[0] == "{" and value[-1] == "}" and all(
        char == "-" or char in "0123456789abcdefABCDEF" for char in value[1:-1]
    )


def _next_guid(before: str, index: int) -> str:
    digest = hashlib.sha256(f"{before}|p90s{index}".encode()).hexdigest().upper()
    return f"{{{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}}}"


def _hex_color(value: str) -> bool:
    raw = value[1:] if value.startswith("#") else value
    return len(raw) in {6, 8} and all(char in "0123456789abcdefABCDEF" for char in raw)


def _signed_int(value: str) -> bool:
    return value.lstrip("-").isdigit() and value not in {"", "-"}


def _default_attr_plan(row: dict[str, Any]) -> dict[str, Any] | None:
    spec = DEFAULT_ATTRS.get(row.get("qname", ""))
    if spec is None:
        return None
    try:
        tree = _tree(row["input_file"], row["part_name"])
        matches = tree.xpath(row["selector"], namespaces=_namespaces(tree.getroot()))
    except Exception:
        return None
    if len(matches) != 1 or not isinstance(matches[0], etree._Element):
        return None
    op, attr = spec
    selector = tree.getpath(matches[0])
    return {
        "operation_id": op,
        "target": f"{row['part_name']}::{selector}",
        "value_selector": selector,
        "attribute_name": attr,
        "default_boolean_attr": True,
    }


def _alternate_plan(row: dict[str, Any]) -> dict[str, Any] | None:
    try:
        tree = _tree(row["input_file"], row["part_name"])
        matches = tree.xpath(row["selector"], namespaces=_namespaces(tree.getroot()))
    except Exception:
        return None
    if len(matches) != 1 or not isinstance(matches[0], etree._Element):
        return None
    choice = _choice(matches[0])
    if choice is None or not choice.get("Requires"):
        return None
    selector = tree.getpath(choice)
    return {
        "operation_id": "alternate_content.choice.metadata.set_value",
        "target": f"{row['part_name']}::{selector}",
        "value_selector": selector,
        "attribute_name": "Requires",
    }


def _vml_plan(row: dict[str, Any]) -> dict[str, Any] | None:
    try:
        tree = _tree(row["input_file"], row["part_name"])
        matches = tree.xpath(row["selector"], namespaces=_namespaces(tree.getroot()))
    except Exception:
        return None
    if len(matches) != 1 or not isinstance(matches[0], etree._Element):
        return None
    node = matches[0]
    local = etree.QName(node).localname
    if local == "stroke":
        return _attr_plan(row, tree, node, "vml.shape.stroke.set_color", "color")
    if local == "fill":
        return _attr_plan(row, tree, node, "vml.shape.fill.set_color", "color")
    if local in {"shape", "rect", "line", "oval", "roundrect"} and node.get("strokecolor"):
        return _attr_plan(row, tree, node, "vml.shape.stroke.set_color", "strokecolor")
    if local in {"shape", "rect", "line", "oval", "roundrect"} and node.get("fillcolor"):
        return _attr_plan(row, tree, node, "vml.shape.fill.set_color", "fillcolor")
    if local in {"shape", "rect", "line", "oval", "roundrect"} and node.get("style"):
        return _attr_plan(row, tree, node, "vml.shape.geometry.set", "style")
    if local in {"shape", "rect", "line", "oval", "roundrect", "shapetype"} and node.get("id"):
        return _attr_plan(row, tree, node, "vml.shape.metadata.set_name", "id")
    return _vml_text_plan(row, tree, node) if local == "textbox" else None


def _attr_plan(row, tree, node, op: str, attr: str) -> dict[str, Any]:
    selector = tree.getpath(node)
    return {"operation_id": op, "target": f"{row['part_name']}::{selector}", "value_selector": selector, "attribute_name": attr}


def _vml_text_plan(row, tree, node) -> dict[str, Any] | None:
    text_node = next((item for item in node.iter() if etree.QName(item).localname == "t" and (item.text or "").strip()), None)
    if text_node is None:
        return None
    return {"operation_id": "vml.shape.text.set", "target": f"{row['part_name']}::{tree.getpath(node)}", "value_selector": tree.getpath(text_node), "attribute_name": ""}


def alternate_requires_value(before: str) -> str:
    prefixes = before.split()
    for prefix in GUARD_PREFIXES:
        if prefix not in prefixes:
            return " ".join([*prefixes, prefix]) if prefixes else prefix
    return " ".join(reversed(prefixes))


def _next_color(before: str, index: int) -> str:
    raw = before[1:] if before.startswith("#") else before
    if len(raw) in {6, 8} and all(char in "0123456789abcdefABCDEF" for char in raw):
        value = f"{(int(raw, 16) + index + 1) % (16 ** len(raw)):0{len(raw)}X}"
        return f"#{value}" if before.startswith("#") else value
    return "#010101"


def _next_style(before: str, index: int) -> str:
    parts = before.split(";")
    for key in ("width", "height", "margin-left", "margin-top"):
        for pos, part in enumerate(parts):
            name, sep, value = part.partition(":")
            if sep and name.strip() == key:
                parts[pos] = f"{name}:{_bump_style_value(value.strip(), index)}"
                return ";".join(parts)
    return before + f";width:{100 + index}pt" if before else f"width:{100 + index}pt"


def _bump_style_value(value: str, index: int) -> str:
    suffix = "pt" if value.endswith("pt") else ""
    raw = value[:-2] if suffix else value
    try:
        return f"{float(raw) + ((index % 9) + 1) / 20:g}{suffix}"
    except ValueError:
        return value + f"-p90v{index}"


def _tree(input_file: str, part_name: str) -> etree._ElementTree:
    with ZipFile(CORPUS / input_file) as package:
        return etree.parse(BytesIO(package.read(part_name)), etree.XMLParser(resolve_entities=False))


def _choice(node: etree._Element) -> etree._Element | None:
    if node.tag == MC_CHOICE:
        return node
    return next((child for child in node if child.tag == MC_CHOICE), None)


def _namespaces(root: etree._Element) -> dict[str, str]:
    return {key: value for node in root.iter() for key, value in node.nsmap.items() if key}
