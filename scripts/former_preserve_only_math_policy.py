#!/usr/bin/env python3
"""Safe subset policy for OMML metadata promotion rows."""
from __future__ import annotations

from typing import Any
from lxml import etree

MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
MATH_RPR = f"{{{MATH_NS}}}rPr"
MATH_PRESENCE_OPS = {f"{{{MATH_NS}}}lit": "math.run_property.literal.presence.set_enabled", f"{{{MATH_NS}}}nor": "math.run_property.normal_text.presence.set_enabled"}

_FONT_VALUES = ("Cambria Math", "Cambria Math-semantic")
_LANG_VALUES = ("en-US", "pt-BR", "zh-CN")
_SCRIPT_VALUES = ("double-struck", "script")
_STYLE_VALUES = ("p", "bi")
_ONOFF_VALUES = ("on", "off", "", "true", "false", "0", "1")
_BEGIN_CHAR_VALUES = ("{", "[", "(", "（", "")
_END_CHAR_VALUES = ("}", "]", ")", "）", "[", "")
_F_TYPE_VALUES = ("bar", "skw", "lin", "noBar")
_JC_VALUES = ("left", "center", "right", "centerGroup")
_NARY_CHAR_VALUES = ("∑", "∫", "∏")
_SEP_CHAR_VALUES = ("|", "")
_XML_SPACE_VALUES = ("preserve", "default")
_SAFE_ONOFF_VAL_ELEMENTS = {
    "degHide",
    "dispDef",
    "smallFrac",
}

_SAFE_INTEGER_VAL_ELEMENTS = {
    "lMargin",
    "rMargin",
    "wrapIndent",
}

_SAFE_VAL_ELEMENTS = {
    "brkBin",
    "brkBinSub",
    "defJc",
    "degHide",
    "dispDef",
    "intLim",
    "jc",
    "mathFont",
    "naryLim",
    "smallFrac",
    "sty",
}
_SAFE_CTRLPR_ATTRS = {
    "ascii",
    "lang",
}

def math_presence_operation(row: dict[str, Any]) -> str:
    if row.get("family") == "math_object" and row.get("semantic_value_kind") == "no_descendant_value":
        return MATH_PRESENCE_OPS.get(row.get("qname", ""), "")
    return ""

def math_presence_contract(row: dict[str, Any], tree: etree._ElementTree, node: etree._Element) -> dict[str, Any]:
    operation = MATH_PRESENCE_OPS.get(node.tag, "")
    parent = node.getparent()
    if not operation or len(node) or node.attrib or (node.text or "").strip():
        return _presence_unsupported(row, "math_presence_requires_empty_target")
    if parent is None or parent.tag != MATH_RPR:
        return _presence_unsupported(row, "math_presence_requires_rpr_parent")
    return {"operation_hydration_status": "hydrated", "operation_id": operation, "operation_target_selector": tree.getpath(node), "value_kind": "presence", "before_semantic_value": "true", "requested_semantic_value": "false"}

def _presence_unsupported(row: dict[str, Any], reason: str) -> dict[str, Any]:
    return {"operation_hydration_status": "unsupported_mapping", "operation_hydration_error": reason, "qname": row.get("qname")}


def math_metadata_allowed(row: dict[str, Any]) -> bool:
    if row.get("operation_id") != "math.object.metadata.set_value":
        return True
    uri, local = _qname_parts(str(row.get("qname", "")))
    attr = str(row.get("attribute_name", "")).rsplit("}", 1)[-1].split(":", 1)[-1]
    if uri != MATH_NS:
        return False
    if attr == "val":
        return local in _SAFE_VAL_ELEMENTS or local in _SAFE_INTEGER_VAL_ELEMENTS or bool(_descendant_val_values(row))
    if attr == "space":
        return local == "t"
    if attr == "ascii" and _selector_ends(row, "/w:rFonts"):
        return True
    return attr in _SAFE_CTRLPR_ATTRS and _has_ctrlpr_context(local, row)


def math_safe_attr_values(row: dict[str, Any]) -> tuple[str, ...]:
    if row.get("operation_id") != "math.object.metadata.set_value":
        return ()
    uri, local = _qname_parts(str(row.get("qname", "")))
    attr = str(row.get("attribute_name", "")).rsplit("}", 1)[-1].split(":", 1)[-1]
    if uri != MATH_NS:
        return ()
    if attr == "val":
        if local in _SAFE_ONOFF_VAL_ELEMENTS:
            return _ONOFF_VALUES
        if local == "jc" or _selector_ends(row, "/m:jc"):
            return _JC_VALUES
        if local == "type" or _selector_ends(row, "/m:type"):
            return _F_TYPE_VALUES
        return _descendant_val_values(row)
    if attr == "space" and local == "t":
        return _XML_SPACE_VALUES
    if attr == "ascii" and _selector_ends(row, "/w:rFonts"):
        return _FONT_VALUES
    if not _has_ctrlpr_context(local, row):
        return ()
    if attr == "ascii":
        return _FONT_VALUES
    if attr == "lang":
        return _LANG_VALUES
    return ()


def _descendant_val_values(row: dict[str, Any]) -> tuple[str, ...]:
    selector = str(row.get("operation_target_selector", ""))
    if selector.endswith("/m:mathFont"):
        return _FONT_VALUES
    if selector.endswith("/m:sty"):
        return _STYLE_VALUES
    if selector.endswith("/m:scr"):
        return _SCRIPT_VALUES
    if selector.endswith("/m:begChr"):
        return _BEGIN_CHAR_VALUES
    if selector.endswith("/m:endChr"):
        return _END_CHAR_VALUES
    if selector.endswith("/m:sepChr"):
        return _SEP_CHAR_VALUES
    if selector.endswith("/m:chr"):
        return _NARY_CHAR_VALUES
    if selector.endswith("/m:type"):
        return _F_TYPE_VALUES
    if selector.endswith("/m:jc"):
        return _JC_VALUES
    return ()


def _has_ctrlpr_context(local: str, row: dict[str, Any]) -> bool:
    selector = str(row.get("operation_target_selector", ""))
    return local == "ctrlPr" or "/m:ctrlPr/" in selector


def _selector_ends(row: dict[str, Any], suffix: str) -> bool:
    return str(row.get("operation_target_selector", "")).endswith(suffix)


def _qname_parts(qname: str) -> tuple[str, str]:
    if not qname.startswith("{"):
        return "", qname.split(":", 1)[-1]
    uri, local = qname[1:].split("}", 1)
    return uri, local
