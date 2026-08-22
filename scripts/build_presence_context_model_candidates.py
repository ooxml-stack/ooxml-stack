#!/usr/bin/env python3
"""Build presence/context model candidates for empty semantic targets."""

from __future__ import annotations

from typing import Any

from semantic_editability_unlock_common import EVIDENCE, local_name, read_json, table, write_json, write_md

OUT_JSON = EVIDENCE / "presence-context-model-candidates.json"
OUT_MD = EVIDENCE / "presence-context-model-candidates.md"

ANCHORLOCK = "{urn:schemas-microsoft-com:office:word}anchorlock"
VML_FORMULAS = "{urn:schemas-microsoft-com:vml}formulas"
VML_STROKE = "{urn:schemas-microsoft-com:vml}stroke"


def main() -> int:
    discovery = read_json(EVIDENCE / "no-semantic-field-discovery.json")
    summary = build_candidates(discovery)
    write_json(OUT_JSON, summary)
    write_md(OUT_MD, markdown(summary))
    print({"candidates": str(OUT_JSON), "dashboard": str(OUT_MD)})
    return 0


def build_candidates(discovery: dict[str, Any]) -> dict[str, Any]:
    rows = [_candidate(group) for group in discovery.get("groups", [])]
    actionable = [row for row in rows if row["recommended_action"] == "design_presence_canary"]
    return {
        "schema_version": "presence-context-model-candidates-v1",
        "source_schema_version": discovery.get("schema_version", ""),
        "input_group_count": len(rows),
        "candidate_count": len(actionable),
        "expected_canary_row_count": sum(row["first_canary"]["row_count"] for row in actionable),
        "candidates": rows,
    }


def _candidate(group: dict[str, Any]) -> dict[str, Any]:
    qname = str(group.get("qname", ""))
    decision = _decision(group)
    return {
        "family": group.get("family", ""),
        "qname": qname,
        "local_name": local_name(qname),
        "row_count": int(group.get("count", 0)),
        "classification_counts": group.get("classification_counts", {}),
        "recommended_action": decision["action"],
        "presence_semantic": decision["semantic"],
        "risk": decision["risk"],
        "required_oracle": decision["oracle"],
        "first_canary": _first_canary(group, decision),
        "sample_rows": group.get("sample_rows", [])[:5],
    }


def _decision(group: dict[str, Any]) -> dict[str, str]:
    qname = str(group.get("qname", ""))
    action = str(group.get("recommended_action", ""))
    classes = group.get("classification_counts", {})
    if action != "investigate_context_model":
        return _keep("target is not a context-only presence candidate")
    if set(classes) != {"context_only_structural_container"}:
        return _keep("mixed classifications need a narrower report before modeling")
    if qname == ANCHORLOCK:
        return {
            "action": "design_presence_canary",
            "semantic": "empty element presence records Word VML anchor-lock metadata",
            "risk": "medium",
            "oracle": "presence toggles while parent shape attrs, sibling nodes, OPC invariants, and native Word open remain stable",
        }
    if qname == VML_FORMULAS:
        return _keep("empty v:formulas has no v:f children; formula semantics live in v:f/@eqn")
    if qname == VML_STROKE:
        return _defer("empty v:stroke may express inherited/default stroke state without a scalar oracle")
    return _defer("presence-only semantics need a family-specific user meaning and Office oracle")


def _keep(reason: str) -> dict[str, str]:
    return {
        "action": "keep_unsupported",
        "semantic": "",
        "risk": "high",
        "oracle": reason,
    }


def _defer(reason: str) -> dict[str, str]:
    return {
        "action": "needs_reference_oracle",
        "semantic": "",
        "risk": "high",
        "oracle": reason,
    }


def _first_canary(group: dict[str, Any], decision: dict[str, str]) -> dict[str, Any]:
    if decision["action"] != "design_presence_canary":
        return {"operation_id": "", "row_count": 0, "chunk_size": 0}
    count = min(5, int(group.get("count", 0)))
    family = str(group.get("family", ""))
    local = local_name(str(group.get("qname", "")))
    return {
        "operation_id": f"{family}.{local}.presence.set_enabled",
        "row_count": count,
        "chunk_size": count,
    }


def markdown(summary: dict[str, Any]) -> str:
    lines = ["# Presence Context Model Candidates", ""]
    lines += [f"- Input groups: {summary['input_group_count']}"]
    lines += [f"- Presence canary candidates: {summary['candidate_count']}"]
    lines += [f"- Expected canary rows: {summary['expected_canary_row_count']}", ""]
    rows = summary["candidates"][:40]
    lines += table(
        "Ranked Groups",
        ("Family", "QName", "Rows", "Action", "Risk", "Canary", "Oracle"),
        [
            (
                row["family"],
                row["qname"],
                row["row_count"],
                row["recommended_action"],
                row["risk"],
                row["first_canary"]["operation_id"],
                row["required_oracle"],
            )
            for row in rows
        ],
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
