"""Narrow PowerPoint 2010 transition presence hydration."""
from __future__ import annotations
from typing import Any
from lxml import etree

P14_NS = "http://schemas.microsoft.com/office/powerpoint/2010/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
PAN_QNAME = f"{{{P14_NS}}}pan"
PRISM_QNAME = f"{{{P14_NS}}}prism"
RIPPLE_QNAME = f"{{{P14_NS}}}ripple"
FLYTHROUGH_QNAME = f"{{{P14_NS}}}flythrough"
SHRED_QNAME = f"{{{P14_NS}}}shred"
REVEAL_QNAME = f"{{{P14_NS}}}reveal"
TRANSITION_QNAME = f"{{{P_NS}}}transition"
PAN_PRESENCE_OP = "office_extension.transition_pan.presence.set_enabled"
PRISM_PRESENCE_OP = "office_extension.transition_prism.presence.set_enabled"
RIPPLE_PRESENCE_OP = "office_extension.transition_ripple.presence.set_enabled"
FLYTHROUGH_PRESENCE_OP = "office_extension.transition_flythrough.presence.set_enabled"
SHRED_PRESENCE_OP = "office_extension.transition_shred.presence.set_enabled"
REVEAL_PRESENCE_OP = "office_extension.transition_reveal.presence.set_enabled"
PRESENCE_OPS = {
    PAN_QNAME: PAN_PRESENCE_OP,
    PRISM_QNAME: PRISM_PRESENCE_OP,
    RIPPLE_QNAME: RIPPLE_PRESENCE_OP,
    FLYTHROUGH_QNAME: FLYTHROUGH_PRESENCE_OP,
    SHRED_QNAME: SHRED_PRESENCE_OP,
    REVEAL_QNAME: REVEAL_PRESENCE_OP,
}


def p14_presence_operation(row: dict[str, Any]) -> str:
    if row.get("family") == "office_extension" and row.get("semantic_value_kind") == "no_descendant_value":
        return PRESENCE_OPS.get(row.get("qname"), "")
    return ""


def p14_presence_contract(row: dict[str, Any], tree: etree._ElementTree, node: etree._Element) -> dict[str, Any]:
    parent = node.getparent()
    operation = PRESENCE_OPS.get(node.tag, "")
    if not operation or len(node) or node.attrib or (node.text or "").strip():
        return _unsupported(row, "p14_transition_presence_requires_empty_target")
    if parent is None or parent.tag != TRANSITION_QNAME:
        return _unsupported(row, "p14_transition_presence_requires_transition_parent")
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
