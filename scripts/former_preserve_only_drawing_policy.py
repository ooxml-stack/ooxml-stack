#!/usr/bin/env python3
"""Safe subset policy for DrawingML/chart drawing metadata promotion rows."""
from __future__ import annotations

from typing import Any

CHART_DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/chartDrawing"
HYPERLINK_COLOR_NS = "http://schemas.microsoft.com/office/drawing/2018/hyperlinkcolor"
DIAGRAM_2016_NS = "http://schemas.microsoft.com/office/drawing/2016/12/diagram"

_TEXT_VERT_OVERFLOW_VALUES = ("overflow", "ellipsis", "clip")
_HYPERLINK_COLOR_VALUES = ("hlink", "tx")
_PRESET_LINE_DASH_VALUES = ("solid", "dot", "dash", "lgDash", "dashDot", "lgDashDot", "lgDashDotDot", "sysDash", "sysDot", "sysDashDot", "sysDashDotDot")


def drawing_safe_attr_values(row: dict[str, Any]) -> tuple[str, ...]:
    uri, local = _qname_parts(str(row.get("qname", "")))
    attr = str(row.get("attribute_name", "")).rsplit("}", 1)[-1].split(":", 1)[-1]
    selector = str(row.get("operation_target_selector", ""))
    if uri == DIAGRAM_2016_NS and local == "spPr":
        if attr == "val" and selector.endswith("/a:prstDash"):
            return _PRESET_LINE_DASH_VALUES
    if uri == HYPERLINK_COLOR_NS and local == "hlinkClr":
        if attr == "val" and selector.endswith("/ahyp:hlinkClr"):
            return _HYPERLINK_COLOR_VALUES
    if uri == CHART_DRAWING_NS and local == "txBody":
        if attr == "vertOverflow" and selector.endswith("/a:bodyPr"):
            return _TEXT_VERT_OVERFLOW_VALUES
    return ()


def _qname_parts(qname: str) -> tuple[str, str]:
    if not qname.startswith("{"):
        return "", qname.split(":", 1)[-1]
    uri, local = qname[1:].split("}", 1)
    return uri, local
