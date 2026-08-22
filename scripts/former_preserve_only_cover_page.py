"""Exact cover-page property text contract."""
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Any
from lxml import etree

NS = "http://schemas.microsoft.com/office/2006/coverPageProps"
PARENT_QNAME = f"{{{NS}}}CoverPageProperties"
PUBLISH_DATE = f"{{{NS}}}PublishDate"
REQUESTED_TEXT = {
    f"{{{NS}}}Abstract": "Document summary",
    f"{{{NS}}}CompanyAddress": "1 Example Street",
    f"{{{NS}}}CompanyPhone": "+1 555 0100",
    f"{{{NS}}}CompanyFax": "+1 555 0101",
    f"{{{NS}}}CompanyEmail": "office@example.com",
}
OPERATION = "custom_xml.element.set_text"
CONTRACT_VERSION = "cover-page-properties-empty-string-v1"
PUBLISH_DATE_CONTRACT_VERSION = "cover-page-publish-date-iso-v1"


def is_candidate(row: dict[str, Any]) -> bool:
    empty_field = (
        row.get("qname") in REQUESTED_TEXT
        and row.get("semantic_value_kind") == "no_descendant_value"
        and row.get("blocker_type") == "needs_family_model"
    )
    publish_date = (
        row.get("qname") == PUBLISH_DATE
        and row.get("semantic_value_kind") == "direct_text"
        and row.get("blocker_type") == "semantic_value_available_pending_proof"
    )
    return row.get("family") == "office_extension" and str(row.get("part_name", "")).startswith("customXml/") and (empty_field or publish_date)


def hydration_contract(row: dict[str, Any], tree: etree._ElementTree, node: etree._Element) -> dict[str, Any]:
    parent = node.getparent()
    if node.tag != row.get("qname") or parent is None or parent.tag != PARENT_QNAME:
        return _unsupported("cover_page_requires_exact_parent")
    if node.tag == PUBLISH_DATE:
        return _publish_date_contract(tree, node)
    if node.attrib or len(node) or (node.text or "").strip():
        return _unsupported("cover_page_requires_empty_string_leaf")
    return {
        "operation_hydration_status": "hydrated",
        "operation_id": OPERATION,
        "operation_target_selector": tree.getpath(node),
        "value_kind": "text",
        "before_semantic_value": "",
        "requested_semantic_value": REQUESTED_TEXT[node.tag],
        "semantic_contract_version": CONTRACT_VERSION,
    }


def promotion_allowed(row: dict[str, Any]) -> bool:
    if row.get("qname") == PUBLISH_DATE:
        return _publish_date_promotion_allowed(row)
    return (
        row.get("qname") in REQUESTED_TEXT
        and row.get("operation_id") == OPERATION
        and row.get("value_kind") == "text"
        and row.get("before_semantic_value") == ""
        and row.get("requested_semantic_value") == REQUESTED_TEXT[row["qname"]]
        and row.get("semantic_contract_version") == CONTRACT_VERSION
        and str(row.get("part_name", "")).startswith("customXml/")
    )


def _publish_date_contract(tree: etree._ElementTree, node: etree._Element) -> dict[str, Any]:
    before = (node.text or "").strip()
    requested = _next_publish_date(before)
    if node.attrib or len(node) or not requested:
        return _unsupported("publish_date_requires_iso_text_leaf")
    return {
        "operation_hydration_status": "hydrated", "operation_id": OPERATION,
        "operation_target_selector": tree.getpath(node), "value_kind": "text",
        "before_semantic_value": before, "requested_semantic_value": requested,
        "semantic_contract_version": PUBLISH_DATE_CONTRACT_VERSION,
    }


def _publish_date_promotion_allowed(row: dict[str, Any]) -> bool:
    before = row.get("before_semantic_value", "")
    return (
        row.get("operation_id") == OPERATION and row.get("value_kind") == "text"
        and row.get("requested_semantic_value") == _next_publish_date(before)
        and row.get("semantic_contract_version") == PUBLISH_DATE_CONTRACT_VERSION
        and str(row.get("part_name", "")).startswith("customXml/")
    )


def _next_publish_date(value: str) -> str:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return ""
    return (parsed + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")


def _unsupported(reason: str) -> dict[str, str]:
    return {"operation_hydration_status": "unsupported_mapping", "operation_hydration_reason": reason}
