"""Exact VML stroke join-style enum contract."""
from __future__ import annotations

from typing import Any

from lxml import etree

V_NS = "urn:schemas-microsoft-com:vml"
STROKE = f"{{{V_NS}}}stroke"
FILL = f"{{{V_NS}}}fill"
OPERATION = "vml.stroke.set_join_style"
BOOLEAN_OPS = {FILL: "vml.fill.set_enabled", STROKE: "vml.stroke.set_enabled"}
OPERATIONS = {OPERATION, *BOOLEAN_OPS.values()}
VALUES = ("round", "bevel", "miter")
CONTRACT_VERSION = "vml-stroke-join-style-enum-v1"


def is_candidate(row: dict[str, Any]) -> bool:
    return (
        row.get("qname") in {FILL, STROKE} and row.get("family") == "vml_drawing"
        and row.get("semantic_value_kind") == "direct_attr"
        and row.get("blocker_type") == "semantic_value_available_pending_proof"
        and str(row.get("part_name", "")).startswith("word/")
    )


def hydration_contract(tree: etree._ElementTree, node: etree._Element) -> dict[str, Any]:
    before = node.get("joinstyle", "")
    if node.tag == STROKE and before in VALUES:
        return _contract(tree, node, OPERATION, "joinstyle", before, "round" if before != "round" else "bevel")
    before = node.get("on", "")
    if node.tag not in BOOLEAN_OPS or before not in {"t", "f", "true", "false", "1", "0"}:
        return _unsupported("vml_paint_requires_explicit_typed_value")
    return _contract(tree, node, BOOLEAN_OPS[node.tag], "on", before, "f" if before in {"t", "true", "1"} else "t")


def _contract(tree: etree._ElementTree, node: etree._Element, operation: str, attr: str, before: str, requested: str) -> dict[str, Any]:
    return {
        "operation_hydration_status": "hydrated", "operation_id": operation,
        "operation_target_selector": tree.getpath(node), "attribute_name": attr,
        "value_kind": "attribute", "before_semantic_value": before,
        "requested_semantic_value": requested, "semantic_contract_version": CONTRACT_VERSION,
    }


def promotion_allowed(row: dict[str, Any]) -> bool:
    operation = row.get("operation_id")
    before, requested = row.get("before_semantic_value"), row.get("requested_semantic_value")
    values = VALUES if operation == OPERATION else {"t", "f", "true", "false", "1", "0"}
    return (
        row.get("qname") in {FILL, STROKE} and operation in OPERATIONS
        and before in values and requested in values and before != requested
        and row.get("semantic_contract_version") == CONTRACT_VERSION
    )


def _unsupported(reason: str) -> dict[str, str]:
    return {"operation_hydration_status": "unsupported_mapping", "operation_hydration_reason": reason}
