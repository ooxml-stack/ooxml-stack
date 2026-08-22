#!/usr/bin/env python3
"""Schema-bounded numeric leaf policy for semantic promotion."""
from __future__ import annotations
from decimal import Decimal, InvalidOperation
from typing import Any

WP14_NS = "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing"
CDR_NS = "http://schemas.openxmlformats.org/drawingml/2006/chartDrawing"
RELATIVE_SIZE_OP = "office_extension.relative_size.set_percentage"
POSITION_PERCENTAGE_OP = "office_extension.position_percentage_offset.set_percentage"
MARKER_COORDINATE_OP = "chart.drawing.marker_coordinate.set_value"
MEDIA_TRIM_OP = "office_extension.media_trim.set_end"
P14_TRIM = "{http://schemas.microsoft.com/office/powerpoint/2010/main}trim"
NUMERIC_LEAF_OPS = {RELATIVE_SIZE_OP, POSITION_PERCENTAGE_OP, MARKER_COORDINATE_OP, MEDIA_TRIM_OP}
_QNAME_OPS = {
    f"{{{WP14_NS}}}pctWidth": RELATIVE_SIZE_OP,
    f"{{{WP14_NS}}}pctHeight": RELATIVE_SIZE_OP,
    f"{{{WP14_NS}}}pctPosVOffset": POSITION_PERCENTAGE_OP,
    f"{{{CDR_NS}}}x": MARKER_COORDINATE_OP,
    f"{{{CDR_NS}}}y": MARKER_COORDINATE_OP,
}

def numeric_leaf_operation(row: dict[str, Any]) -> str:
    return _QNAME_OPS.get(row.get("qname", ""), "")

def numeric_attribute_operation(row: dict[str, Any], attr: str) -> str:
    return MEDIA_TRIM_OP if row.get("qname") == P14_TRIM and attr == "end" and row.get("semantic_value_kind") == "direct_attr" else ""

def checked_numeric_value(before: str, requested: str, row: dict[str, Any]) -> str | None:
    operation = row.get("operation_id")
    if operation not in NUMERIC_LEAF_OPS:
        return None
    number = _decimal(requested)
    if operation in {RELATIVE_SIZE_OP, POSITION_PERCENTAGE_OP} and requested.isdigit() and number >= 0:
        return requested
    if operation == MARKER_COORDINATE_OP and 0 <= number <= 1:
        return requested
    if operation == MEDIA_TRIM_OP and number >= 0:
        return requested
    raise ValueError(f"schema_policy_unsafe_numeric_leaf: {before!r}->{requested!r}")

def next_numeric_value(before: str, row: dict[str, Any]) -> str | None:
    operation = row.get("operation_id")
    if operation in {RELATIVE_SIZE_OP, POSITION_PERCENTAGE_OP}:
        checked_numeric_value(before, before, row)
        return str(int(before) + 1)
    if operation == MARKER_COORDINATE_OP:
        number = _decimal(before)
        if not 0 <= number <= 1:
            raise ValueError(f"schema_policy_unsafe_numeric_before: {before!r}")
        return _plain(number + Decimal("0.01") if number <= Decimal("0.99") else number - Decimal("0.01"))
    if operation == MEDIA_TRIM_OP:
        number = _decimal(before)
        if number < 0:
            raise ValueError(f"schema_policy_unsafe_numeric_before: {before!r}")
        return _plain(number + Decimal("0.000001"))
    return None

def _decimal(value: str) -> Decimal:
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"invalid numeric leaf: {value!r}") from exc
    if not number.is_finite():
        raise ValueError(f"invalid numeric leaf: {value!r}")
    return number

def _plain(value: Decimal) -> str:
    text = format(value, "f").rstrip("0").rstrip(".")
    return text or "0"
