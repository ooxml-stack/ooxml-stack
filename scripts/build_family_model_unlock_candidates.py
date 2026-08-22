#!/usr/bin/env python3
"""Build family-model unlock candidates for semantic editability."""

from __future__ import annotations

from typing import Any

from semantic_editability_unlock_common import (
    EVIDENCE,
    family_model_template,
    read_json,
    table,
    write_json,
    write_md,
)

OUT_JSON = EVIDENCE / "family-model-unlock-candidates.json"
OUT_MD = EVIDENCE / "family-model-unlock-candidates.md"

PRIORITIES = [
    "office_extension",
    "vml_drawing",
    "math_object",
    "office_chart_extension",
    "chart_drawing",
    "custom_xml_schema",
    "custom_xml_payload",
    "wps_extension",
    "legacy_office_drawing",
    "alternate_content",
]


def main() -> int:
    remaining = read_json(EVIDENCE / "remaining-bucket-summary.json")
    summary = build_candidates(remaining)
    write_json(OUT_JSON, summary)
    write_md(OUT_MD, markdown(summary))
    print({"candidates": str(OUT_JSON), "dashboard": str(OUT_MD)})
    return 0


def build_candidates(remaining: dict[str, Any]) -> dict[str, Any]:
    rows = [_candidate(family, index, remaining) for index, family in enumerate(PRIORITIES, start=1)]
    rows = [row for row in rows if row["current_remaining_count"]]
    return {
        "schema_version": "family-model-unlock-candidates-v1",
        "candidate_count": len(rows),
        "candidates": rows,
    }


def _candidate(family: str, priority: int, remaining: dict[str, Any]) -> dict[str, Any]:
    by_family = remaining.get("by_family", {})
    blockers = remaining.get("by_family_blocker", {}).get(family, {})
    opportunities = _opportunities(family, remaining)
    template = family_model_template(family)
    total = int(by_family.get(family, 0))
    pending = int(blockers.get("semantic_value_available_pending_proof", 0))
    unsupported = total - pending
    return {
        "family_id": family,
        "priority": priority,
        "current_remaining_count": total,
        "current_pending_proof_count": pending,
        "current_unsupported_count": max(unsupported, 0),
        "what_the_object_represents_in_user_terms": template["user_terms"],
        "readable_semantic_fields": _readable(family),
        "editable_semantic_fields": template["editable_fields"],
        "disallowed_fields": template["disallowed_fields"],
        "stable_handle_requirements": "package-local stable_id, part_name, selector, qname, and unambiguous operation target",
        "before_value_extraction": _before(family),
        "after_value_oracle": "requested value equals after semantic value and target_semantic_changed is true",
        "sibling_unchanged_oracle": "same package/family/operation siblings keep before semantic values",
        "package_invariant_checks": "OPC parts, relationships, content types, binary hashes, and package open remain valid",
        "native_office_gate_requirements": "exact edited output opens in Word/PowerPoint with no repair/security/crash/timeout",
        "first_small_batch_target": _first_batch(family, opportunities),
    }


def _opportunities(family: str, remaining: dict[str, Any]) -> list[dict[str, Any]]:
    rows = remaining.get("family_model_opportunities", [])
    return [row for row in rows if row.get("family") == family and row.get("semantic_value_source") != "no_descendant_value"]


def _readable(family: str) -> str:
    mapping = {
        "math_object": "OMML token/run text and math metadata",
        "vml_drawing": "VML shape text, lock/wrap metadata, and safe style fields",
        "custom_xml_payload": "leaf text and attribute values",
        "custom_xml_schema": "schema element names, types, and annotations",
    }
    return mapping.get(family, "qname, known metadata attributes, semantic value kind, and selector")


def _before(family: str) -> str:
    if family in {"custom_xml_payload", "math_object", "vml_drawing"}:
        return "parse owner XML node and extract leaf text or allowlisted attribute"
    return "read allowlisted attribute or descendant metadata value from operation target selector"


def _first_batch(family: str, opportunities: list[dict[str, Any]]) -> dict[str, Any]:
    if not opportunities:
        return {"operation_id": "", "row_count": 0, "chunk_size": 0}
    top = opportunities[0]
    count = min(5, int(top.get("count", 0)))
    return {
        "operation_id": top.get("operation_needed", f"{family}.needs_family_model.model"),
        "qname": top.get("qname", ""),
        "semantic_value_source": top.get("semantic_value_source", ""),
        "row_count": count,
        "chunk_size": count,
    }


def markdown(summary: dict[str, Any]) -> str:
    lines = ["# Family Model Unlock Candidates", ""]
    lines += [f"- Candidate count: {summary['candidate_count']}", ""]
    rows = summary["candidates"]
    lines += table(
        "Ranked Families",
        ("Priority", "Family", "Remaining", "Pending proof", "Unsupported", "User terms", "Editable fields", "First batch"),
        [(r["priority"], r["family_id"], r["current_remaining_count"], r["current_pending_proof_count"], r["current_unsupported_count"], r["what_the_object_represents_in_user_terms"], r["editable_semantic_fields"], r["first_small_batch_target"]["operation_id"]) for r in rows],
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
