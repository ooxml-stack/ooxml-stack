"""Explicit reason codes for semantic blocker rows."""

from __future__ import annotations


def no_semantic_reason(row: dict) -> str:
    local = _local(row.get("qname", ""))
    family = row.get("family", "")
    if local in {"sldId", "modId", "creationId"}:
        return "relationship_identity_like"
    if local in {"svgBlip", "blip"}:
        return "binary_payload_reference"
    if family in {"wps_extension", "vendor_private_extension"}:
        return "needs_vendor_family_model"
    if family in {"drawing_extension", "office_drawing_sketch_extension"}:
        return "needs_family_model"
    return "needs_family_model"


def is_explicit_unsupported(reason: str) -> bool:
    return reason in {
        "relationship_identity_like",
        "binary_payload_reference",
        "needs_vendor_family_model",
        "needs_family_model",
    }


def _local(qname: str) -> str:
    return qname.rsplit("}", 1)[-1] if qname.startswith("{") else qname.rsplit(":", 1)[-1]
