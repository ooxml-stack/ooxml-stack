from __future__ import annotations
from typing import Any
from former_preserve_only_drawing_policy import drawing_safe_attr_values
from former_preserve_only_math_policy import MATH_PRESENCE_OPS, math_safe_attr_values
from former_preserve_only_numeric_leaf import checked_numeric_value, next_numeric_value
from former_preserve_only_p14_presence import PRESENCE_OPS as P14_PRESENCE_OPS
from former_preserve_only_picture_effect_presence import PICTURE_EFFECT_PRESENCE_OPS
from former_preserve_only_w14_policy import w14_safe_attr_values
from ooxml_spec import SpecQuery, ns
_SPEC = SpecQuery()
_PREFERRED_ENUM_NEXT = {
    "orthographicFront": "perspectiveFront",
    "perspectiveFront": "orthographicFront",
    "threePt": "balanced",
    "balanced": "threePt",
    "accent1": "accent2",
    "accent2": "accent1",
    "tx1": "accent1",
    "lt1": "accent1",
    "solid": "dash",
    "dash": "solid",
}
_FALLBACK_ENUM_TYPES = {
    ("brkBin", "val"): "m:ST_BreakBin",
    ("brkBinSub", "val"): "m:ST_BreakBinSub",
    ("camera", "prst"): "a:ST_PresetCameraType",
    ("hiddenScene3d", "prst"): "a:ST_PresetCameraType", ("hiddenEffects", "algn"): "a:ST_RectAlignment",
    ("defJc", "val"): "m:ST_Jc",
    ("grpSpPr", "bwMode"): "a:ST_BlackWhiteMode",
    ("intLim", "val"): "m:ST_LimLoc",
    ("scene3d", "prst"): "a:ST_PresetCameraType",
    ("naryLim", "val"): "m:ST_LimLoc",
    ("lightRig", "rig"): "a:ST_LightRigType",
    ("schemeClr", "val"): "a:ST_SchemeColorVal",
    ("spPr", "bwMode"): "a:ST_BlackWhiteMode",
    ("prstDash", "val"): "a:ST_PresetLineDashVal",
    ("sty", "val"): "m:ST_Style",
    ("wgp", "bwMode"): "a:ST_BlackWhiteMode",
    ("wsp", "bwMode"): "a:ST_BlackWhiteMode",
    **{("bodyPr", attr): f"a:{typ}" for attr, typ in {"anchor": "ST_TextAnchoringType", "vert": "ST_TextVerticalType", "wrap": "ST_TextWrappingType"}.items()},
}
_SAFE_STRING_ATTRS = {
    ("urn:schemas-microsoft-com:vml", "imagedata", "title"),
    ("http://schemas.microsoft.com/office/drawing/2008/diagram", "cNvPr", "name"),
    ("http://schemas.microsoft.com/office/drawing/2008/diagram", "nvGrpSpPr", "name"),
    ("http://schemas.microsoft.com/office/drawing/2008/diagram", "nvSpPr", "name"), ("http://schemas.microsoft.com/office/drawing/2008/diagram", "spTree", "name"), ("http://schemas.microsoft.com/office/drawing/2008/diagram", "drawing", "name"),
    ("http://schemas.microsoft.com/office/powerpoint/2010/main", "section", "name"),
    ("http://schemas.microsoft.com/office/powerpoint/2010/main", "sectionLst", "name"),
    ("http://schemas.microsoft.com/office/thememl/2012/main", "themeFamily", "name"),
    ("http://schemas.microsoft.com/office/word/2010/wordprocessingGroup", "cNvPr", "name"),
    ("http://schemas.microsoft.com/office/word/2010/wordprocessingGroup", "grpSp", "name"),
    ("http://schemas.microsoft.com/office/word/2010/wordprocessingShape", "cNvPr", "name"),
    ("http://schemas.microsoft.com/office/word/2010/wordprocessingShape", "wsp", "name"),
    ("http://schemas.openxmlformats.org/drawingml/2006/chartDrawing", "cNvPr", "name"),
    ("http://schemas.openxmlformats.org/drawingml/2006/chartDrawing", "nvSpPr", "name"), ("http://schemas.openxmlformats.org/drawingml/2006/chartDrawing", "sp", "name"),
}
_SAFE_ATTR_ENUMS = {
    ("http://schemas.microsoft.com/office/2006/activeX", "ocx", "classid"): ("{5512D110-5CC6-11CF-8D67-00AA00BDCE1D}", "{5512D116-5CC6-11CF-8D67-00AA00BDCE1D}", "{5512D11A-5CC6-11CF-8D67-00AA00BDCE1D}", "{5512D122-5CC6-11CF-8D67-00AA00BDCE1D}"), ("urn:schemas-microsoft-com:office:office", "shapedefaults", "fillcolor"): ("#FFFFFF", "#00AA55"),
    ("http://schemas.microsoft.com/office/word/2010/wordml", "round", "val"): ("", "0", "false", "1", "true"),
    ("http://schemas.openxmlformats.org/officeDocument/2006/math", "mathFont", "val"): ("Cambria Math", "Cambria Math-semantic"),
    ("http://schemas.microsoft.com/office/word/2010/wordml", "ligatures", "val"): ("standardContextual", "none"), ("urn:schemas-microsoft-com:office:office", "idmap", "ext"): ("view", "edit", "backwardCompatible"), ("http://www.wps.cn/officeDocument/2022/drawingmlCustomData", "textFrameExt", "type"): ("text", "text-semantic"), ("http://schemas.microsoft.com/office/drawing/2017/model3d", "raster", "rName"): ("Office3DRenderer", "Office3DRenderer-semantic"), ("http://schemas.microsoft.com/office/drawing/2012/chart", "spPr", "prst"): ("rect", "wedgeRectCallout"), ("http://schemas.openxmlformats.org/officeDocument/2006/math", "ctrlPr", "ascii"): ("Cambria Math", "Cambria Math-semantic"), ("http://schemas.openxmlformats.org/officeDocument/2006/math", "ctrlPr", "lang"): ("en-US", "pt-BR", "zh-CN"),
    **{("http://schemas.microsoft.com/office/powerpoint/2010/main", local, "dir"): ("l", "r") for local in ("conveyor", "flip", "gallery", "switch", "vortex")},
    **{("http://schemas.microsoft.com/office/powerpoint/2010/main", local, "dir"): ("u", "d", "l", "r") for local in ("pan", "prism")},
    **{("http://schemas.microsoft.com/office/powerpoint/2010/main", local, "dir"): ("in", "out") for local in ("flythrough", "warp")},
    ("http://schemas.microsoft.com/office/powerpoint/2010/main", "doors", "dir"): ("horz", "vert"),
    ("http://schemas.microsoft.com/office/powerpoint/2012/main", "guide", "orient"): ("horz", "vert"),
    ("http://schemas.microsoft.com/office/powerpoint/2012/main", "notesGuideLst", "orient"): ("horz", "vert"),
    ("http://schemas.microsoft.com/office/powerpoint/2012/main", "prstTrans", "prst"): ("pageCurlDouble", "pageCurlSingle", "curtains", "wind", "airplane", "fallOver", "drape", "peelOff", "prestige", "crush"),
    ("http://schemas.microsoft.com/office/powerpoint/2012/main", "sldGuideLst", "orient"): ("horz", "vert"),
    ("http://schemas.microsoft.com/office/powerpoint/2015/09/main", "morph", "option"): ("byObject", "byWord", "byChar"),
}
_SCHEME_COLORS = ("bg1", "tx1", "bg2", "tx2", "accent1", "accent2", "accent3", "accent4", "accent5", "accent6", "hlink", "folHlink", "phClr", "dk1", "lt1", "dk2", "lt2")
_VML_PATH_METADATA = "vml.path.metadata.set_value"
_VML_FORMULA_EQN = "vml.formula.eqn.set_value"
_VML_BOOLEAN_OPS = {"vml.fill.set_enabled", "vml.stroke.set_enabled", "vml.shadow.set_enabled", "vml.textpath.set_enabled"}
_ANCHORLOCK_PRESENCE = "legacy_office_drawing.anchorlock.presence.set_enabled"
_NO_FILL_PRESENCE = "office_extension.no_fill.presence.set_enabled"
_BEVEL_PRESENCE = "office_extension.text_outline.bevel.presence.set_enabled"
_CONTEXTUAL_ALTERNATES_PRESENCE = "office_extension.contextual_alternates.presence.set_enabled"
_DELETE_ONLY_PRESENCE = {_ANCHORLOCK_PRESENCE, _NO_FILL_PRESENCE, _BEVEL_PRESENCE, _CONTEXTUAL_ALTERNATES_PRESENCE} | set(P14_PRESENCE_OPS.values()) | set(PICTURE_EFFECT_PRESENCE_OPS.values()) | set(MATH_PRESENCE_OPS.values())
_VML_FORMULA_EQN_VALUES = ("val #0", "sum #0 0 0")
def checked_requested_value(before: str, requested: str, row: dict[str, Any]) -> str:
    if requested == before:
        return requested
    if (numeric := checked_numeric_value(before, requested, row)) is not None:
        return numeric
    if _is_text_row(row):
        return requested
    if row.get("operation_id") in _DELETE_ONLY_PRESENCE:
        if requested == "false": return requested
        _raise_unsafe("untyped-attribute", before, requested, row)
    if _is_special_operation_value(requested, row):
        return requested
    safe_values = _safe_attr_enum_values(row)
    if safe_values:
        if before in safe_values and requested in safe_values:
            return requested
        _raise_unsafe("safe-enum", before, requested, row)
    if _is_safe_textbox_flag(row):
        if before in {"1", "true"} and requested in {"0", "false"}:
            return requested
        _raise_unsafe("textbox-flag", before, requested, row)
    enum_values = _enum_values(row)
    if enum_values:
        if before not in enum_values or requested not in enum_values:
            _raise_unsafe("enum-value", before, requested, row)
        return requested
    if _is_boolean_attr(row, before) or _is_schema_boolean_attr(row):
        if requested in {"true", "false", "0", "1"}:
            return requested
        _raise_unsafe("boolean", before, requested, row)
    if _is_safe_hex_color_attr(row, before):
        if _is_hex_color(requested):
            return requested
        _raise_unsafe("hex-color", before, requested, row)
    if _is_int_literal(before):
        if _is_int_literal(requested):
            return requested
        _raise_unsafe("integer", before, requested, row)
    if _is_hex_color(before):
        if _is_hex_color(requested):
            return requested
        _raise_unsafe("hex-color", before, requested, row)
    if _is_safe_scheme_color_attr(row, before):
        if requested in _SCHEME_COLORS:
            return requested
        _raise_unsafe("scheme-color", before, requested, row)
    if _is_safe_string_attr(row) and requested.strip() and _control_free(requested):
        return requested
    _raise_unsafe("untyped-attribute", before, requested, row)
def next_requested_value(before: str, index: int, row: dict[str, Any]) -> str:
    attr = row.get("attribute_name", "").rsplit("}", 1)[-1]
    operation = row["operation_id"]
    if (numeric := next_numeric_value(before, row)) is not None:
        return numeric
    if operation in {"vml.shape.fill.set_color", "vml.shape.stroke.set_color"}:
        return "#00AA55"
    if operation == _VML_PATH_METADATA:
        return "f" if before != "f" else "t"
    if operation == _VML_FORMULA_EQN:
        return "sum #0 0 0" if before != "sum #0 0 0" else "val #0"
    if operation in _VML_BOOLEAN_OPS: return "f" if before in {"t", "true", "1"} else "t"
    if operation in _DELETE_ONLY_PRESENCE:
        return "false"
    if operation == "alternate_content.choice.metadata.set_value":
        return before if "a14" in before.split() else f"{before} a14".strip()
    enum_next = _next_enum_value(before, row)
    if enum_next:
        return enum_next
    if attr in {"nil", "enabled"} or before in {"true", "false"}:
        return "false" if before in {"true", "1"} else "true"
    if _is_schema_boolean_attr(row):
        return "false" if before in {"true", "1"} else "true"
    safe_values = _safe_attr_enum_values(row)
    if safe_values:
        return next(value for value in safe_values if value != before)
    if _is_safe_hex_color_attr(row, before) or attr == "val" and _is_hex_color(before) and not _is_int_literal(before):
        return "00AA55"
    if _is_safe_scheme_color_attr(row, before):
        return _next_scheme_color(before)
    if attr == "val" and _is_binary_flag(row.get("qname", "")):
        return "0" if before != "0" else "1"
    if _is_safe_textbox_flag(row):
        return "0"
    if _is_safe_string_attr(row):
        return _next_safe_string(before, index, row)
    if _is_int_literal(before):
        return str(int(before) - 1 if int(before) >= 32767 else int(before) + 1)
    if row.get("value_kind") == "attribute" or row.get("attribute_name"):
        _raise_unsafe("untyped-attribute", before, "", row)
    return "campaign" if not before else f"{before}-campaign-{index}"
def _next_enum_value(before: str, row: dict[str, Any]) -> str:
    values = _enum_values(row)
    if not values:
        return ""
    if before not in values:
        _raise_unsafe("enum-before", before, "", row)
    preferred = _PREFERRED_ENUM_NEXT.get(before)
    if preferred in values:
        return preferred
    return next(value for value in values if value != before)
def _enum_values(row: dict[str, Any]) -> tuple[str, ...]:
    qname = _prefixed_name(row.get("qname", ""))
    attr = row.get("attribute_name", "")
    attr_local = attr.rsplit("}", 1)[-1].split(":", 1)[-1]
    type_name = _attribute_type(qname, attr_local)
    values = _enum_values_for_type(type_name, qname.split(":", 1)[0] if ":" in qname else "")
    if values:
        return values
    element_local = qname.split(":", 1)[-1]
    fallback = _FALLBACK_ENUM_TYPES.get((element_local, attr_local))
    return _enum_values_for_type(fallback, "")
def _attribute_type(qname: str, attr_local: str) -> str:
    if not qname or ":" not in qname:
        return ""
    prefix = qname.split(":", 1)[0]
    element_type = _SPEC.find_element(qname)
    if not element_type:
        return ""
    canonical = _canonical_type(element_type, prefix)
    for attr in _SPEC.resolved_attributes(canonical):
        if attr["name"].split(":", 1)[-1] == attr_local:
            return attr.get("type", "")
    return ""
def _canonical_type(type_name: str, prefix: str) -> str:
    candidate = f"{prefix}:{type_name}" if ":" not in type_name else type_name
    return candidate if _SPEC.complex_type(candidate) else type_name
def _enum_values_for_type(type_name: str | None, prefix: str) -> tuple[str, ...]:
    if not type_name:
        return ()
    candidates = [type_name]
    if ":" not in type_name and prefix:
        candidates.insert(0, f"{prefix}:{type_name}")
    for candidate in candidates:
        try:
            values = tuple(_SPEC.enum_values(candidate))
        except ValueError:
            continue
        if values:
            return values
    return ()
def _prefixed_name(qname: str) -> str:
    if not qname.startswith("{"):
        return qname
    uri, local = qname[1:].split("}", 1)
    prefix = ns.prefix_for_uri(uri)
    return f"{prefix}:{local}" if prefix else local
def _is_text_row(row: dict[str, Any]) -> bool:
    return row.get("value_kind") == "text" and not row.get("attribute_name")
def _is_special_operation_value(value: str, row: dict[str, Any]) -> bool:
    operation = row.get("operation_id")
    if operation == "alternate_content.choice.metadata.set_value":
        return bool(value.strip())
    if operation in {"vml.shape.fill.set_color", "vml.shape.stroke.set_color"}: return value.startswith("#") and _is_hex_color(value[1:])
    if operation == "vml.image.metadata.set_title": return bool(value.strip()) and _control_free(value)
    if operation == _VML_PATH_METADATA:
        return value in {"t", "f"}
    if operation == _VML_FORMULA_EQN:
        return value in _VML_FORMULA_EQN_VALUES
    if operation in _VML_BOOLEAN_OPS: return value in {"t", "f", "true", "false", "1", "0"}
    return False
def _is_boolean_attr(row: dict[str, Any], before: str) -> bool:
    attr = row.get("attribute_name", "").rsplit("}", 1)[-1]
    return attr in {"nil", "enabled"} or before in {"true", "false"} or _is_binary_flag(row.get("qname", ""))
def _is_schema_boolean_attr(row: dict[str, Any]) -> bool:
    attr = row.get("attribute_name", "").rsplit("}", 1)[-1].split(":", 1)[-1]
    return _attribute_type(_prefixed_name(row.get("qname", "")), attr) == "xsd:boolean"
def _is_hex_color(value: str) -> bool:
    return len(value) == 6 and all(ch in "0123456789abcdefABCDEF" for ch in value)
def _is_int_literal(value: str) -> bool:
    body = value[1:] if value.startswith("-") else value
    return bool(body) and all("0" <= ch <= "9" for ch in body)
def _is_binary_flag(qname: str) -> bool:
    return any(token in qname for token in ("showMediaCtrls", "discardImageEditData", "chartTrackingRefBased"))
def _is_safe_string_attr(row: dict[str, Any]) -> bool:
    uri, local = _qname_parts(row.get("qname", ""))
    attr = row.get("attribute_name", "").rsplit("}", 1)[-1].split(":", 1)[-1]
    return (uri, local, attr) in _SAFE_STRING_ATTRS
def _safe_attr_enum_values(row: dict[str, Any]) -> tuple[str, ...]:
    for safe_values in (math_safe_attr_values(row), w14_safe_attr_values(row), drawing_safe_attr_values(row)):
        if safe_values:
            return safe_values
    uri, local = _qname_parts(row.get("qname", ""))
    attr = row.get("attribute_name", "").rsplit("}", 1)[-1].split(":", 1)[-1]
    return _SAFE_ATTR_ENUMS.get((uri, local, attr), ())
def _is_safe_scheme_color_attr(row: dict[str, Any], before: str) -> bool:
    uri, local = _qname_parts(row.get("qname", ""))
    attr = row.get("attribute_name", "").rsplit("}", 1)[-1].split(":", 1)[-1]
    return attr == "val" and before in _SCHEME_COLORS and (uri.endswith("/office/drawing/2010/main") and local == "hiddenFill" or uri.endswith("/office/word/2010/wordml") and local in {"solidFill", "textFill"})
def _is_safe_hex_color_attr(row: dict[str, Any], before: str) -> bool:
    uri, local = _qname_parts(row.get("qname", ""))
    attr = row.get("attribute_name", "").rsplit("}", 1)[-1].split(":", 1)[-1]
    selector = str(row.get("operation_target_selector", ""))
    return uri.endswith("/office/word/2010/wordml") and attr == "val" and _is_hex_color(before) and (local == "srgbClr" or local in {"contourClr", "extrusionClr"} and selector.endswith("/w14:srgbClr"))
def _is_safe_textbox_flag(row: dict[str, Any]) -> bool:
    uri, local = _qname_parts(row.get("qname", ""))
    attr = row.get("attribute_name", "").rsplit("}", 1)[-1].split(":", 1)[-1]
    return local == "cNvSpPr" and attr == "txBox" and uri.endswith(("wordprocessingShape", "/drawing/2008/diagram", "/chartDrawing"))
def _qname_parts(qname: str) -> tuple[str, str]:
    if not qname.startswith("{"):
        return "", qname.split(":", 1)[-1]
    uri, local = qname[1:].split("}", 1); return uri, local
def _next_scheme_color(before: str) -> str:
    preferred = _PREFERRED_ENUM_NEXT.get(before)
    if preferred in _SCHEME_COLORS: return preferred
    return next(value for value in _SCHEME_COLORS if value != before)
def _next_safe_string(before: str, index: int, row: dict[str, Any]) -> str:
    suffix = f" [semantic-edit-{index}]"; base = before.strip() or ("Section" if _is_section_string_attr(row) else "Object")
    if base.endswith(suffix):
        return base
    return f"{base[:180]}{suffix}"
def _is_section_string_attr(row: dict[str, Any]) -> bool:
    uri, local = _qname_parts(row.get("qname", ""))
    return uri.endswith("/office/powerpoint/2010/main") and local in {"section", "sectionLst"}
def _control_free(value: str) -> bool:
    return all(ch >= " " or ch in "\t\n\r" for ch in value)
def _raise_unsafe(kind: str, before: str, requested: str, row: dict[str, Any]) -> str:
    qname = row.get("qname", ""); attr = row.get("attribute_name", "")
    raise ValueError(f"schema_policy_unsafe_{kind}: {qname} @{attr} {before!r}->{requested!r}")
