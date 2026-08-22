#!/usr/bin/env python3
"""Build schema-policy unlock candidates for remaining rows."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from former_preserve_only_schema_policy_audit import _audit_row, _candidate_rows, _promoted_sources
from semantic_editability_unlock_common import (
    EVIDENCE,
    local_name,
    namespace,
    policy_action,
    read_jsonl,
    sample_values,
    table,
    value_kind,
    write_json,
    write_md,
)

OUT_JSON = EVIDENCE / "schema-policy-unlock-candidates.json"
OUT_MD = EVIDENCE / "schema-policy-unlock-candidates.md"


def main() -> int:
    hydrated = read_jsonl(EVIDENCE / "operation-hydration-ledger.jsonl")
    candidates = build_candidates({}, hydrated)
    write_json(OUT_JSON, candidates)
    write_md(OUT_MD, markdown(candidates))
    print({"candidates": str(OUT_JSON), "dashboard": str(OUT_MD)})
    return 0


def build_candidates(remaining: dict[str, Any], hydrated: list[dict[str, Any]]) -> dict[str, Any]:
    del remaining
    groups = _rejected_groups(hydrated)
    rows = [_candidate(key, bucket) for key, bucket in groups.items()]
    rows = sorted(rows, key=lambda row: _sort_key(row))
    return {
        "schema_version": "schema-policy-unlock-candidates-v1",
        "candidate_count": len(rows),
        "unlock_now_count": sum(row["recommended_action"] == "unlock_now" for row in rows),
        "needs_spec_check_count": sum(row["recommended_action"] == "needs_spec_check" for row in rows),
        "keep_blocked_count": sum(row["recommended_action"] == "keep_blocked" for row in rows),
        "candidates": rows,
    }


def _rejected_groups(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str, str], list[dict[str, Any]]]:
    groups: defaultdict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    cache: dict = {}
    for index, row in enumerate(_candidate_rows(rows, _promoted_sources())):
        reason = row.get("_policy_rejection_reason") or _audit_row(row, index, cache)
        if reason:
            key = (str(row.get("family", "")), str(row.get("qname", "")), _attr(row), reason)
            groups[key].append(row)
    return groups


def _candidate(key: tuple[str, str, str, str], matches: list[dict[str, Any]]) -> dict[str, Any]:
    family, qname, attr, reason = key
    values = sample_values(matches)
    kind = value_kind(values[0] if values else "", attr)
    action, safe = policy_action(attr, qname, kind, reason)
    return {
        "qname": qname,
        "namespace": namespace(qname),
        "attribute_name": attr,
        "attribute_local_name": local_name(attr),
        "family": family,
        "current_rejection_reason": reason,
        "observed_value_samples": values,
        "value_type_classification": kind,
        "proposed_safe_replacement_value": _replacement(kind, values, action),
        "why_the_replacement_is_safe": safe,
        "expected_candidate_row_count": len(matches),
        "expected_packages_touched": len({item.get("package_id") for item in matches}),
        "required_oracle": _oracle(kind),
        "required_regression_tests": _tests(kind),
        "risk_level": _risk(action, kind),
        "recommended_action": action,
        "sample_row_ids": [item.get("row_id", "") for item in matches[:5]],
    }


def _attr(row: dict[str, Any]) -> str:
    return str(row.get("attribute_name") or "")


def _replacement(kind: str, values: list[str], action: str = "") -> str:
    first = values[0] if values else ""
    if action == "unlock_now" and kind == "empty":
        return "Object [semantic-edit-index]"
    if kind == "boolean_like":
        return "0" if first in {"1", "true"} else "1"
    if kind == "text_or_enum_like":
        return f"{first}-semantic" if first else "semantic"
    if kind == "color_like":
        return "FF0000"
    if kind == "integer_like":
        return "schema-bounded integer from value policy"
    return "none until stronger oracle exists"


def _oracle(kind: str) -> str:
    base = "exact before/requested/after value, sibling unchanged, API/CLI/MCP proof, native Office pass"
    if kind in {"identity_like", "relationship_like"}:
        return base + ", plus relationship ownership oracle"
    if kind in {"integer_like", "color_like"}:
        return base + ", plus schema bounds or parser validation"
    return base


def _tests(kind: str) -> list[str]:
    tests = ["accept allowlisted safe value", "reject identity/reference/binary fields", "reject ambiguous selector"]
    if kind in {"integer_like", "color_like"}:
        tests.append("reject out-of-domain typed value")
    return tests


def _risk(action: str, kind: str) -> str:
    if action == "keep_blocked":
        return "high"
    return "medium" if kind in {"integer_like", "color_like"} else "low"


def _sort_key(row: dict[str, Any]) -> tuple[int, int, str]:
    action_order = {"unlock_now": 0, "needs_spec_check": 1, "keep_blocked": 2}
    return (action_order[row["recommended_action"]], -row["expected_candidate_row_count"], row["attribute_name"])


def markdown(summary: dict[str, Any]) -> str:
    lines = ["# Schema Policy Unlock Candidates", ""]
    lines += [f"- Candidate count: {summary['candidate_count']}"]
    lines += [f"- Unlock now: {summary['unlock_now_count']}"]
    lines += [f"- Needs spec check: {summary['needs_spec_check_count']}"]
    lines += [f"- Keep blocked: {summary['keep_blocked_count']}", ""]
    rows = summary["candidates"][:40]
    lines += table(
        "Candidates",
        ("Action", "Risk", "Family", "QName", "Attribute", "Kind", "Rows", "Packages", "Why"),
        [(r["recommended_action"], r["risk_level"], r["family"], r["qname"], r["attribute_name"], r["value_type_classification"], r["expected_candidate_row_count"], r["expected_packages_touched"], r["why_the_replacement_is_safe"]) for r in rows],
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
