from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_family_model_unlock_candidates import build_candidates as build_family
from build_office_boundary_analysis import build_analysis
from build_schema_policy_unlock_candidates import build_candidates as build_policy
from build_targeted_unlock_replay_plan import build_plan
from build_unlock_blocker_taxonomy import build_taxonomy


def _gap(package: str, blocker: str, family: str = "office_extension") -> dict:
    return {
        "row_id": f"{package}:{blocker}",
        "blocker_type": blocker,
        "family": family,
        "format": "pptx",
        "package_id": package,
        "qname": "{urn:test}node",
        "attribute_name": "name",
        "operation_id": "office_extension.known_metadata.set_value",
        "operation_hydration_status": "hydrated",
    }


def test_unlock_taxonomy_counts_required_metrics() -> None:
    rows = [
        _gap("pkg-a", "semantic_value_available_pending_proof"),
        _gap("pkg-b", "needs_family_model", "vml_drawing"),
        _gap("pkg-c", "binary_payload_reference"),
    ]
    remaining = {
        "starting_remaining_count": 3,
        "family_model_opportunities": [],
        "known_boundary_packages": [{"package_id": "pkg-a"}],
        "known_replay_timeout_packages": [{"package_id": "pkg-c"}],
        "must_remain_unsupported": [{"reason": "binary_payload_reference", "count": 1}],
    }
    plan = {"skipped_counts": {"runner_schema_policy": 2}}

    summary = build_taxonomy(rows, remaining, {"rejected_count": 4}, plan)

    assert summary["row_count"] == 3
    assert summary["metrics"]["hydrated_not_promoted_count"] == 3
    assert summary["metrics"]["schema_policy_rejected_count"] == 4
    assert summary["metrics"]["requires_new_family_model_count"] == 0
    assert summary["metrics"]["planner_schema_policy_skipped_count"] == 2
    assert summary["metrics"]["office_boundary_package_blocked_count"] == 1
    assert summary["metrics"]["replay_timeout_package_blocked_count"] == 1
    assert "native Office boundary" in summary["by_package_id"][0]["why_remaining"]


def test_schema_policy_candidates_classify_actions() -> None:
    remaining = {
        "safe_policy_expansion_opportunities": [
            {"family": "office_extension", "qname": "{urn:test}node", "attribute_name": "enabled", "count": 2, "current_rejection_reason": "schema_policy_unsafe_untyped-attribute"},
            {"family": "office_extension", "qname": "{urn:test}node", "attribute_name": "shapeId", "count": 1, "current_rejection_reason": "schema_policy_unsafe_untyped-attribute"},
        ]
    }
    hydrated = [
        _hydrated("enabled", "true"),
        _hydrated("enabled", "false"),
        _hydrated("shapeId", "42"),
    ]

    summary = build_policy(remaining, hydrated)
    by_attr = {row["attribute_name"]: row for row in summary["candidates"]}

    assert by_attr["enabled"]["recommended_action"] == "unlock_now"
    assert by_attr["shapeId"]["recommended_action"] == "keep_blocked"
    assert by_attr["enabled"]["expected_packages_touched"] == 1


def test_family_model_candidates_include_user_terms() -> None:
    summary = build_family({
        "by_family": {"math_object": 7},
        "by_family_blocker": {"math_object": {"semantic_value_available_pending_proof": 5}},
        "family_model_opportunities": [
            {
                "family": "math_object",
                "operation_needed": "math_object.needs_family_model.model",
                "qname": "{math}argPr",
                "semantic_value_source": "direct_attr",
                "count": 5,
            }
        ],
    })

    row = summary["candidates"][0]
    assert row["family_id"] == "math_object"
    assert row["current_unsupported_count"] == 2
    assert row["first_small_batch_target"]["operation_id"] == "math_object.needs_family_model.model"


def test_family_model_vml_first_batch_uses_existing_operation() -> None:
    summary = build_family({
        "by_family": {"vml_drawing": 7},
        "by_family_blocker": {"vml_drawing": {"semantic_value_available_pending_proof": 5}},
        "family_model_opportunities": [
            {
                "family": "vml_drawing",
                "operation_needed": "vml_drawing.needs_family_model.model",
                "qname": "{urn:schemas-microsoft-com:vml}path",
                "semantic_value_source": "direct_vml_path_metadata",
                "count": 9,
            }
        ],
    })

    row = summary["candidates"][0]
    assert row["family_id"] == "vml_drawing"
    assert row["first_small_batch_target"]["operation_id"] == "vml_drawing.needs_family_model.model"
    assert row["first_small_batch_target"]["qname"] == "{urn:schemas-microsoft-com:vml}path"


def test_targeted_plan_skips_family_without_real_model_rows() -> None:
    family = {
        "candidates": [
            {
                "family_id": "vml_drawing",
                "current_remaining_count": 7,
                "current_pending_proof_count": 7,
                "first_small_batch_target": {
                    "operation_id": "vml_drawing.needs_family_model.model",
                    "row_count": 5,
                    "semantic_value_source": "no_descendant_value",
                },
            }
        ]
    }

    summary = build_plan({"candidate_packages": []}, {"candidates": []}, family)

    assert summary["plans"][2]["candidate_count"] == 0


def test_office_boundary_analysis_marks_boundary_only(tmp_path: Path, monkeypatch) -> None:
    office = tmp_path / "office.json"
    office.write_text(json.dumps({"results": [{"app": "Microsoft PowerPoint", "status": "repair_dialog"}]}))
    record = {
        "status": "office_boundary",
        "package_id": "pkg-a",
        "family": "office_extension",
        "operation_ids": ["office_extension.known_metadata.set_value"],
        "planned_row_count": 8,
        "office_result_file": str(office),
        "public_path_file": "public.jsonl",
    }

    summary = build_analysis([record], [_hydrated("label", "Quarterly") | {"package_id": "pkg-a"}])

    row = summary["records"][0]
    assert row["edited_package_native_office_status"] == "repair_dialog"
    assert row["remain_boundary_only"] is True
    assert row["smaller_chunk_size_recommended"] is False


def test_targeted_plan_keeps_three_distinct_plans() -> None:
    remaining = {
        "starting_semantic_editable_count": 7,
        "starting_remaining_count": 3,
        "by_blocker": {"semantic_value_available_pending_proof": 3},
        "candidate_packages": [{"package_id": "pkg-a", "family": "office_extension", "operation_id": "op", "planned_safe_rows": 5, "recommended_action": "promote_batch"}],
    }
    policy = {"candidates": [{"recommended_action": "unlock_now", "expected_candidate_row_count": 9, "attribute_name": "label"}]}
    family = {"candidates": [{"family_id": "math_object", "current_remaining_count": 7, "current_pending_proof_count": 7, "first_small_batch_target": {"operation_id": "math.token.set_text", "row_count": 5}}]}

    summary = build_plan(remaining, policy, family)

    assert summary["source_counts"]["starting_semantic_editable_count"] == 7
    assert summary["source_counts"]["starting_remaining_count"] == 3
    assert [plan["plan_id"] for plan in summary["plans"]] == [
        "quick_proof_batch",
        "schema_policy_unlock_batch",
        "family_model_implementation_batch",
    ]
    assert summary["plans"][0]["expected_row_count"] == 5
    assert summary["plans"][1]["requires_code_change"] is True


def test_targeted_plan_uses_target_level_audit_fallback() -> None:
    audit = {
        "targets": [
            {
                "rank": 7,
                "qname": "{urn:test}safe",
                "package_examples": [
                    {
                        "package_id": "pkg-safe",
                        "format": "pptx",
                        "family": "office_extension",
                        "operation_id": "office_extension.known_metadata.set_value",
                        "reason": "candidate_outside_remaining_top100",
                        "planned_safe_rows": 12,
                        "row_count": 12,
                    },
                    {
                        "package_id": "pkg-big",
                        "family": "office_extension",
                        "operation_id": "office_extension.known_metadata.set_value",
                        "reason": "candidate_outside_remaining_top100",
                        "planned_safe_rows": 30,
                    },
                ],
            }
        ]
    }

    summary = build_plan({"candidate_packages": []}, {"candidates": []}, {"candidates": []}, audit)
    quick = summary["plans"][0]

    assert quick["candidate_count"] == 1
    assert quick["expected_row_count"] == 12
    assert quick["candidates"][0]["recommended_action"] == "target_level_quickproof"
    assert quick["candidates"][0]["qname"] == "{urn:test}safe"


def test_targeted_plan_surfaces_schema_spec_check_candidates() -> None:
    policy = {"candidates": [{"recommended_action": "needs_spec_check", "expected_candidate_row_count": 17, "attribute_name": "name"}]}

    summary = build_plan({"candidate_packages": []}, policy, {"candidates": []})
    schema = summary["plans"][1]

    assert schema["candidate_count"] == 1
    assert schema["expected_row_count"] == 17
    assert schema["candidates"][0]["recommended_action"] == "needs_spec_check"


def _hydrated(attr: str, value: str) -> dict:
    return {
        "family": "office_extension",
        "qname": "{urn:test}node",
        "attribute_name": attr,
        "before_semantic_value": value,
        "_policy_rejection_reason": "schema_policy_unsafe_untyped-attribute",
        "operation_hydration_status": "hydrated",
        "package_id": "pkg-a",
        "row_id": f"row-{attr}-{value}",
    }
