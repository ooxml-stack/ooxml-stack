#!/usr/bin/env python3
"""Build remaining-bucket analysis for semantic-editability burn-down."""
from __future__ import annotations
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable
from campaign_office_boundary_summary import package_id_from_result, primary_status
from chunk_timeout_boundaries import merge_office_timeout_boundaries, replay_timeout_packages
from former_preserve_only_promoted_index import promoted_index
from semantic_editability_failed_rows import failed_source_ids
from semantic_editability_remaining_candidates import candidate_packages, promotion_runner_counts
ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "release-evidence/former-preserve-only-semantic-editability"
CORPUS = ROOT.parent / "ooxml-native-corpus"
SUMMARY_OUT = EVIDENCE / "remaining-bucket-summary.json"
DASHBOARD_OUT = EVIDENCE / "remaining-bucket-dashboard.md"
def main() -> int:
    gaps = _read_jsonl(EVIDENCE / "gap-ledger.jsonl")
    hydrated = _read_jsonl(EVIDENCE / "operation-hydration-ledger.jsonl")
    gap_summary = _read_json(EVIDENCE / "gap-summary.json")
    hydration_summary = _read_json(EVIDENCE / "operation-hydration-summary.json")
    policy = _read_json(EVIDENCE / "schema-policy-audit.json")
    checkpoint = EVIDENCE / "chunk-promotion-checkpoint.json"
    office = merge_office_timeout_boundaries(_office_index(EVIDENCE / "office-results"), checkpoint, ROOT)
    replay_timeouts = replay_timeout_packages(checkpoint, ROOT)
    promoted_sources, promoted_targets = promoted_index(EVIDENCE / "promotion-rows.jsonl")
    failed_sources = failed_source_ids(checkpoint, EVIDENCE / "staged-rows")
    summary = build_summary(
        gaps, hydrated, gap_summary, hydration_summary, policy, office, replay_timeouts, _package_mb,
        promoted_sources=promoted_sources, promoted_targets=promoted_targets,
        failed_sources=failed_sources, runner_planner=promotion_runner_counts,
    )
    _write_json(SUMMARY_OUT, summary)
    DASHBOARD_OUT.write_text(_markdown(summary), encoding="utf-8")
    print(json.dumps({"summary": str(SUMMARY_OUT), "dashboard": str(DASHBOARD_OUT)}, indent=2))
    return 0
def build_summary(
    gaps: list[dict[str, Any]],
    hydrated: list[dict[str, Any]],
    gap_summary: dict[str, Any],
    hydration_summary: dict[str, Any],
    policy: dict[str, Any],
    office: dict[str, dict[str, Any]],
    replay_timeouts: list[dict[str, Any]],
    size_lookup: Callable[[str], float | None],
    promoted_sources: set[str] | None = None,
    promoted_targets: set[tuple[str, str, str, str]] | None = None,
    failed_sources: set[str] | None = None,
    runner_planner: Any = None,
) -> dict[str, Any]:
    return {
        "schema_version": "semantic-editability-remaining-buckets-v1",
        "starting_semantic_editable_count": gap_summary.get("semantic_editable_count", 0),
        "starting_remaining_count": gap_summary.get("semantic_editable_remaining", len(gaps)),
        "by_blocker": gap_summary.get("remaining_by_blocker", _counts(gaps, "blocker_type")),
        "by_family": gap_summary.get("remaining_by_family", _counts(gaps, "family")),
        "by_family_blocker": _nested_counts(gaps, "family", "blocker_type"),
        "by_family_qname_top50": _top_by_group(gaps, "family", "qname", 50),
        "by_operation_top50": dict(_counter(hydrated, "operation_id").most_common(50)),
        "by_attribute_top50": dict(_counter(hydrated, "attribute_name").most_common(50)),
        "hydration_status_counts": hydration_summary.get("status_counts", {}),
        "candidate_packages": candidate_packages(
            hydrated, office, replay_timeouts, size_lookup,
            promoted_sources=promoted_sources, promoted_targets=promoted_targets,
            failed_sources=failed_sources, runner_planner=runner_planner,
        ),
        "known_boundary_packages": _known_boundaries(office),
        "known_replay_timeout_packages": replay_timeouts,
        "safe_policy_expansion_opportunities": _policy_opportunities(policy),
        "family_model_opportunities": _model_opportunities(gaps),
        "must_remain_unsupported": _unsupported_buckets(gaps),
    }
def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"missing {path}; run make campaign-ledgers")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def _counter(rows: list[dict[str, Any]], field: str) -> Counter[str]:
    return Counter(str(row.get(field, "")) for row in rows if row.get(field))

def _counts(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    return dict(_counter(rows, field).most_common())

def _nested_counts(rows: list[dict[str, Any]], left: str, right: str) -> dict[str, dict[str, int]]:
    groups: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        groups[str(row.get(left, ""))][str(row.get(right, ""))] += 1
    return {key: dict(counter.most_common()) for key, counter in sorted(groups.items())}

def _top_by_group(rows: list[dict[str, Any]], group: str, field: str, limit: int) -> dict[str, dict[str, int]]:
    groups: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        if row.get(field):
            groups[str(row.get(group, ""))][str(row.get(field, ""))] += 1
    return {key: dict(counter.most_common(limit)) for key, counter in sorted(groups.items())}

def _office_index(office_dir: Path) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for path in sorted(office_dir.glob("api-*.json")):
        data = _read_json(path)
        status = primary_status(data)
        package = _package_from_office(path, data)
        if package:
            current = index.get(package, {})
            if current.get("status") != "pass" and current:
                continue
            if status != "pass" or not current:
                index[package] = {"status": status, "office_result": _display_path(path)}
    return index

def _display_path(path: Path) -> str:
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)

def _package_from_office(path: Path, data: dict[str, Any]) -> str:
    result = next(iter(data.get("results", [])), {})
    return package_id_from_result(result.get("file", "") or path.stem)


def _known_boundaries(office: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [{"package_id": pkg, **data} for pkg, data in office.items() if data.get("status") != "pass"]
    return sorted(rows, key=lambda row: (row["status"], row["package_id"]))

def _policy_opportunities(policy: dict[str, Any]) -> list[dict[str, Any]]:
    top = policy.get("rejection_by_attribute_top20", {})
    examples = policy.get("examples_by_reason", {})
    rows = []
    for attr, count in sorted(top.items(), key=lambda item: (-int(item[1]), item[0])):
        example = _example_for_attr(attr, examples)
        rows.append(_policy_row(attr, count, example))
    return rows

def _example_for_attr(attr: str, examples: dict[str, dict[str, Any]]) -> dict[str, Any]:
    for reason, example in examples.items():
        if example.get("attribute_name") == attr:
            return {"reason": reason, **example}
    return {}

def _policy_row(attr: str, count: int, example: dict[str, Any]) -> dict[str, Any]:
    reason = example.get("reason", "schema_policy_unsafe_untyped-attribute")
    return {
        "family": example.get("family", ""),
        "qname": example.get("qname", ""),
        "attribute_name": attr,
        "current_rejection_reason": reason,
        "count": count,
        "spec_type_if_known": "",
        "sample_row_ids": [example["row_id"]] if example.get("row_id") else [],
        "proposed_policy": _proposed_policy(str(reason)),
        "risk": "high" if "integer" in str(reason) else "medium",
    }

def _proposed_policy(reason: str) -> str:
    if "integer" in reason:
        return "add schema-backed integer bounds before promotion"
    return "allow only named attributes with exact before/requested/after oracle"

def _model_opportunities(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: defaultdict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("blocker_type") in {"needs_family_model", "needs_vendor_family_model"} and row.get("semantic_value_kind") != "no_descendant_value":
            grouped[(str(row.get("family", "")), str(row.get("qname", "")), str(row.get("next_operation_model", "")))].append(row)
    return [_model_row(key, bucket) for key, bucket in sorted(grouped.items(), key=lambda item: -len(item[1]))[:50]]

def _model_row(key: tuple[str, str, str], rows: list[dict[str, Any]]) -> dict[str, Any]:
    family, qname, operation = key
    return {
        "family": family,
        "qname": qname,
        "operation_needed": operation,
        "count": len(rows),
        "semantic_value_source": rows[0].get("semantic_value_kind", ""),
        "oracle_strategy": rows[0].get("required_oracle", ""),
        "sample_row_ids": [row.get("row_id", "") for row in rows[:3]],
        "owner_repo": rows[0].get("owner_repo", ""),
    }

def _unsupported_buckets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hard = {"relationship_identity_like", "binary_payload_reference", "needs_vendor_family_model"}
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        reason = _unsupported_reason(row, hard)
        if reason:
            grouped[reason].append(row)
    return [_unsupported_row(reason, bucket) for reason, bucket in sorted(grouped.items())]

def _unsupported_reason(row: dict[str, Any], hard: set[str]) -> str:
    blocker = str(row.get("blocker_type", ""))
    if blocker in hard:
        return blocker
    if row.get("semantic_value_kind") == "no_descendant_value":
        return "no_semantic_field_available"
    return ""

def _unsupported_row(reason: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    examples = [{key: row.get(key, "") for key in ("row_id", "family", "qname", "package_id")} for row in rows[:5]]
    return {"reason": reason, "count": len(rows), "examples": examples, "why_not_safe_yet": _why_unsupported(reason)}
def _why_unsupported(reason: str) -> str:
    why = {
        "relationship_identity_like": "changing identity/reference fields can sever cross-part links",
        "binary_payload_reference": "binary targets need a payload or relationship oracle before mutation",
        "needs_vendor_family_model": "vendor-private semantics need an explicit field model",
        "no_semantic_field_available": "the target has no attribute, text, or descendant scalar to edit",
    }
    return why.get(reason, "explicit unsupported reason remains required")

def _package_mb(input_file: str) -> float | None:
    path = CORPUS / input_file
    return round(path.stat().st_size / 1024 / 1024, 3) if path.exists() else None
def _markdown(summary: dict[str, Any]) -> str:
    lines = ["# Semantic Editability Remaining Buckets", ""]
    lines += [f"- Starting semantic-editable: {summary['starting_semantic_editable_count']}"]
    lines += [f"- Starting remaining: {summary['starting_remaining_count']}", ""]
    lines += _section_counts("Blockers", summary["by_blocker"])
    lines += _section_counts("Families", summary["by_family"])
    lines += _table(
        "Top Candidate Packages",
        ("Package", "Family", "Operation", "Planned", "Total", "Action", "Reason"),
        [(_c(row, "package_id"), _c(row, "family"), _c(row, "operation_id"), row["planned_safe_rows"], row["total_remaining_rows"], _c(row, "recommended_action"), row["reason"]) for row in summary["candidate_packages"][:25]],
    )
    lines += _table(
        "Known Office Boundary Packages",
        ("Package", "Status", "Office result"),
        [(_c(row, "package_id"), _c(row, "status"), _c(row, "office_result")) for row in summary["known_boundary_packages"][:25]],
    )
    lines += _table(
        "Known Replay Timeout Packages",
        ("Package", "Family", "Operation", "Scope", "Chunks", "State", "Reason"),
        [(_c(row, "package_id"), _c(row, "family"), _c(row, "operation_id"), "operation" if row.get("operation_id") else "package", len(row["chunk_ids"]), row.get("slow_replay_state", "") if row.get("operation_id") else "", row["reason"]) for row in summary["known_replay_timeout_packages"][:25]],
    )
    lines += _table(
        "Family Model Opportunities",
        ("Family", "Count", "Operation", "QName"),
        [(_c(row, "family"), row["count"], _c(row, "operation_needed"), _c(row, "qname")) for row in summary["family_model_opportunities"][:25]],
    )
    lines += _table(
        "Must Remain Unsupported For Now",
        ("Reason", "Count", "Why"),
        [(_c(row, "reason"), row["count"], row["why_not_safe_yet"]) for row in summary["must_remain_unsupported"]],
    )
    return "\n".join(lines).rstrip() + "\n"

def _section_counts(title: str, counts: dict[str, int]) -> list[str]:
    lines = [f"## {title}", ""]
    return lines + [f"- `{key}`: {value}" for key, value in counts.items()] + [""]

def _table(title: str, headers: tuple[str, ...], rows: list[tuple[Any, ...]]) -> list[str]:
    lines = [f"## {title}", "", "| " + " | ".join(headers) + " |"]
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    lines += ["| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |" for row in rows]
    return lines + [""]
def _c(row: dict[str, Any], key: str) -> str:
    return f"`{row[key]}`"

def _operation_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (str(row.get("package_id", "")), str(row.get("family", "")), str(row.get("operation_id", "")))

if __name__ == "__main__":
    raise SystemExit(main())
