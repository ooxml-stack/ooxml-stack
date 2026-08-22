"""Exact empty picture-effect presence hydration."""
from __future__ import annotations
from typing import Any
from lxml import etree

A14_NS = "http://schemas.microsoft.com/office/drawing/2010/main"
FILM_GRAIN_QNAME = f"{{{A14_NS}}}artisticFilmGrain"
ARTISTIC_BLUR_QNAME = f"{{{A14_NS}}}artisticBlur"
IMAGE_EFFECT_QNAME = f"{{{A14_NS}}}imgEffect"
FILM_GRAIN_PRESENCE_OP = "office_extension.picture_effect.film_grain.presence.set_enabled"
ARTISTIC_BLUR_PRESENCE_OP = "office_extension.picture_effect.artistic_blur.presence.set_enabled"
PICTURE_EFFECT_PRESENCE_OPS = {FILM_GRAIN_QNAME: FILM_GRAIN_PRESENCE_OP, ARTISTIC_BLUR_QNAME: ARTISTIC_BLUR_PRESENCE_OP}


def picture_effect_presence_operation(row: dict[str, Any]) -> str:
    if (
        row.get("family") == "office_extension"
        and row.get("qname") in PICTURE_EFFECT_PRESENCE_OPS
        and row.get("semantic_value_kind") == "no_descendant_value"
    ):
        return PICTURE_EFFECT_PRESENCE_OPS[row["qname"]]
    return ""


def picture_effect_presence_contract(row: dict[str, Any], tree: etree._ElementTree, node: etree._Element) -> dict[str, Any]:
    parent = node.getparent()
    operation = PICTURE_EFFECT_PRESENCE_OPS.get(node.tag, "")
    if not operation or len(node) or node.attrib or (node.text or "").strip():
        return _unsupported(row, "picture_effect_presence_requires_empty_target")
    if parent is None or parent.tag != IMAGE_EFFECT_QNAME:
        return _unsupported(row, "picture_effect_presence_requires_image_effect_parent")
    return {
        "operation_hydration_status": "hydrated",
        "operation_id": operation,
        "operation_target_selector": tree.getpath(node),
        "value_kind": "presence",
        "before_semantic_value": "true",
        "requested_semantic_value": "false",
    }


def _unsupported(row: dict[str, Any], reason: str) -> dict[str, Any]:
    return {"operation_hydration_status": "unsupported_mapping", "operation_hydration_error": reason, "qname": row.get("qname")}
