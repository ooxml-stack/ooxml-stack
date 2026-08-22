"""Exact OLE locked-field boolean contract."""
from __future__ import annotations

from typing import Any

from lxml import etree

O_NS = "urn:schemas-microsoft-com:office:office"
LOCKED_FIELD = f"{{{O_NS}}}LockedField"
OLE_OBJECT = f"{{{O_NS}}}OLEObject"
OPERATION = "office_extension.ole.locked_field.set_enabled"
CONTRACT_VERSION = "ole-locked-field-explicit-false-v1"


def is_candidate(row: dict[str, Any]) -> bool:
    return (
        row.get("qname") == LOCKED_FIELD
        and row.get("family") == "legacy_office_drawing"
        and row.get("semantic_value_kind") == "direct_text"
        and row.get("blocker_type") == "semantic_value_available_pending_proof"
        and str(row.get("part_name", "")).startswith("word/")
    )


def hydration_contract(tree: etree._ElementTree, node: etree._Element) -> dict[str, Any]:
    parent = node.getparent()
    if node.tag != LOCKED_FIELD or parent is None or parent.tag != OLE_OBJECT:
        return _unsupported("ole_locked_field_requires_exact_parent")
    if node.attrib or len(node) or (node.text or "") != "false":
        return _unsupported("ole_locked_field_requires_explicit_false_leaf")
    return {
        "operation_hydration_status": "hydrated", "operation_id": OPERATION,
        "operation_target_selector": tree.getpath(node), "value_kind": "text",
        "before_semantic_value": "false", "requested_semantic_value": "true",
        "semantic_contract_version": CONTRACT_VERSION,
    }


def promotion_allowed(row: dict[str, Any]) -> bool:
    return (
        row.get("qname") == LOCKED_FIELD and row.get("operation_id") == OPERATION
        and row.get("before_semantic_value") == "false"
        and row.get("requested_semantic_value") == "true"
        and row.get("semantic_contract_version") == CONTRACT_VERSION
    )


def _unsupported(reason: str) -> dict[str, str]:
    return {"operation_hydration_status": "unsupported_mapping", "operation_hydration_reason": reason}
