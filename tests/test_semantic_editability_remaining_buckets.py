from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_semantic_editability_remaining_buckets import _office_index
from build_semantic_editability_remaining_buckets import _markdown
from build_semantic_editability_remaining_buckets import build_summary
from chunk_timeout_boundaries import merge_office_timeout_boundaries, replay_timeout_packages


def _gap(package: str, blocker: str, family: str = "office_extension", semantic_kind: str = "direct_attr") -> dict[str, str]:
    return {
        "blocker_type": blocker,
        "family": family,
        "format": "pptx",
        "input_file": f"corpus/pptx/{package}.pptx",
        "next_operation_model": f"{family}.{blocker}.model",
        "owner_repo": "ooxml-test-framework",
        "package_id": package,
        "qname": "{urn:test}node",
        "required_oracle": "exact oracle",
        "row_id": f"{package}:{blocker}",
        "semantic_value_kind": semantic_kind,
    }


def _hydrated(package: str, status: str = "hydrated", operation: str = "office_extension.known_metadata.set_value") -> dict[str, str]:
    row = _gap(package, "semantic_value_available_pending_proof")
    row.update(
        {
            "attribute_name": "name",
            "operation_target_selector": f"/p:sld/{package}/{operation}",
            "part_name": "ppt/slides/slide1.xml",
            "operation_hydration_status": status,
            "operation_id": operation,
            "source_row_id": f"{package}:{status}:{operation}",
        }
    )
    return row


def test_remaining_bucket_summary_groups_candidates_and_blockers() -> None:
    gaps = [
        _gap("pkg-pass", "semantic_value_available_pending_proof"),
        _gap("pkg-fail", "semantic_value_available_pending_proof"),
        _gap("pkg-model", "needs_family_model", "vml_drawing"),
        _gap("pkg-empty", "needs_family_model", "vml_drawing", "no_descendant_value"),
        _gap("pkg-bin", "binary_payload_reference"),
    ]
    hydrated = [_hydrated("pkg-pass"), _hydrated("pkg-fail"), _hydrated("pkg-pass", "unsupported_mapping")]
    office = {
        "pkg-pass": {"status": "pass", "office_result": "pass.json"},
        "pkg-fail": {"status": "repair_dialog", "office_result": "fail.json"},
    }

    summary = build_summary(gaps, hydrated, {"semantic_editable_count": 7}, {}, {}, office, [], lambda _: 1.25)

    assert summary["schema_version"] == "semantic-editability-remaining-buckets-v1"
    assert "generated_at_utc" not in summary
    assert summary["starting_semantic_editable_count"] == 7
    assert summary["by_family_blocker"]["office_extension"]["semantic_value_available_pending_proof"] == 2
    assert summary["known_boundary_packages"] == [{"package_id": "pkg-fail", "status": "repair_dialog", "office_result": "fail.json"}]
    assert summary["known_replay_timeout_packages"] == []
    assert _candidate(summary, "pkg-pass")["recommended_action"] == "promote_batch"
    assert _candidate(summary, "pkg-pass")["skipped_policy_rows"] == 1
    assert _candidate(summary, "pkg-fail")["recommended_action"] == "skip_boundary"
    assert summary["family_model_opportunities"][0]["family"] == "vml_drawing"
    assert summary["must_remain_unsupported"][0]["reason"] == "binary_payload_reference"
    assert {row["reason"] for row in summary["must_remain_unsupported"]} == {
        "binary_payload_reference",
        "no_semantic_field_available",
    }


def test_policy_opportunities_include_rejection_examples() -> None:
    policy = {
        "rejection_by_attribute_top20": {"val": 3},
        "examples_by_reason": {"schema_policy_unsafe_integer": _hydrated("pkg-pass") | {"attribute_name": "val"}},
    }

    summary = build_summary([], [], {}, {}, policy, {}, [], lambda _: None)

    opportunity = summary["safe_policy_expansion_opportunities"][0]
    assert opportunity["attribute_name"] == "val"
    assert opportunity["current_rejection_reason"] == "schema_policy_unsafe_integer"
    assert opportunity["risk"] == "high"
    assert opportunity["sample_row_ids"]


def test_office_index_preserves_any_prior_boundary_failure(tmp_path: Path) -> None:
    _write_office(tmp_path / "api-a.json", "pass", "api-a-pptx_pkg.pptx")
    _write_office(tmp_path / "api-z.json", "repair_dialog", "api-z-pptx_pkg.pptx")
    _write_office(tmp_path / "api-zz.json", "pass", "api-zz-pptx_pkg.pptx")

    assert _office_index(tmp_path)["pptx_pkg"]["status"] == "repair_dialog"


def test_chunk_timeout_without_office_evidence_is_replay_timeout(tmp_path: Path) -> None:
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text(
        json.dumps({"records": [{"status": "timeout", "package_id": "pkg-timeout", "chunk_id": "chunk-a"}]}),
        encoding="utf-8",
    )

    merged = merge_office_timeout_boundaries({"pkg-pass": {"status": "pass"}}, checkpoint)
    replay = replay_timeout_packages(checkpoint)

    assert "pkg-timeout" not in merged
    assert replay[0]["package_id"] == "pkg-timeout"
    assert replay[0]["status"] == "replay_timeout"
    assert replay[0]["chunk_ids"] == ["chunk-a"]


def test_small_chunk_canary_marks_replay_timeout_eligible(tmp_path: Path) -> None:
    checkpoint = tmp_path / "checkpoint.json"
    _write_checkpoint(checkpoint, [_timeout_record(), _promoted_record(duration=447.8)])

    replay = replay_timeout_packages(checkpoint)
    summary = build_summary([_gap("pkg-a", "semantic_value_available_pending_proof")], [_hydrated("pkg-a")], {}, {}, {}, {}, replay, lambda _: 1.0)

    assert replay[0]["slow_replay_state"] == "small_chunk_canary_passed"
    assert replay[0]["operation_id"] == "office_extension.known_metadata.set_value"
    assert summary["candidate_packages"][0]["recommended_action"] == "slow_replay_eligible"


def test_remaining_candidates_scope_slow_replay_by_operation(tmp_path: Path) -> None:
    checkpoint = tmp_path / "checkpoint.json"
    _write_checkpoint(checkpoint, [_timeout_record(), _promoted_record()])
    hydrated = [
        _hydrated("pkg-a", operation="office_extension.known_metadata.set_value"),
        _hydrated("pkg-a", operation="office_extension.other_metadata.set_value"),
    ]

    summary = build_summary([], hydrated, {}, {}, {}, {}, replay_timeout_packages(checkpoint), lambda _: 1.0)
    by_operation = {row["operation_id"]: row for row in summary["candidate_packages"]}

    assert by_operation["office_extension.known_metadata.set_value"]["planned_safe_rows"] == 1
    assert by_operation["office_extension.known_metadata.set_value"]["recommended_action"] == "slow_replay_eligible"
    assert by_operation["office_extension.other_metadata.set_value"]["planned_safe_rows"] == 1
    assert by_operation["office_extension.other_metadata.set_value"]["recommended_action"] == "skip_replay_timeout"


def test_remaining_candidates_exclude_promoted_targets_and_public_unsupported() -> None:
    promoted = _hydrated("pkg-a")
    public_unsupported = _hydrated("pkg-a") | {"part_name": "customXml/item1.xml"}
    live = _hydrated("pkg-a") | {"operation_target_selector": "/p:sld/live"}
    target = ("pkg-a", "office_extension.known_metadata.set_value", f"{promoted['part_name']}::{promoted['operation_target_selector']}", "name")

    summary = build_summary([], [promoted, public_unsupported, live], {}, {}, {}, {}, [], lambda _: 1.0, promoted_targets={target})

    assert summary["candidate_packages"][0]["planned_safe_rows"] == 1
    assert summary["candidate_packages"][0]["total_remaining_rows"] == 1


def test_remaining_candidates_apply_runner_preflight() -> None:
    rows = [_hydrated("pkg-a"), _hydrated("pkg-a") | {"operation_target_selector": "/p:sld/other"}]

    def runner_planner(items: list[dict]) -> dict[str, int]:
        return {"planned_safe_rows": 1, "runner_schema_policy_skipped_rows": len(items) - 1}

    summary = build_summary([], rows, {}, {}, {}, {}, [], lambda _: 1.0, runner_planner=runner_planner)

    assert summary["candidate_packages"][0]["planned_safe_rows"] == 1
    assert summary["candidate_packages"][0]["runner_schema_policy_skipped_rows"] == 1


def test_legacy_timeout_canary_still_scopes_by_operation(tmp_path: Path) -> None:
    checkpoint = tmp_path / "checkpoint.json"
    _write_checkpoint(checkpoint, [_timeout_record(operation=""), _promoted_record()])
    hydrated = [
        _hydrated("pkg-a", operation="office_extension.known_metadata.set_value"),
        _hydrated("pkg-a", operation="office_extension.other_metadata.set_value"),
    ]

    summary = build_summary([], hydrated, {}, {}, {}, {}, replay_timeout_packages(checkpoint), lambda _: 1.0)
    by_operation = {row["operation_id"]: row for row in summary["candidate_packages"]}

    assert by_operation["office_extension.known_metadata.set_value"]["recommended_action"] == "slow_replay_eligible"
    assert by_operation["office_extension.other_metadata.set_value"]["recommended_action"] == "skip_replay_timeout"

    dashboard = _markdown(summary)
    assert "| Package | Family | Operation | Scope | Chunks | State | Reason |" in dashboard
    assert "`office_extension.known_metadata.set_value` | operation | 0 | small_chunk_canary_passed" in dashboard
    assert "`office_extension.other_metadata.set_value` | operation" not in dashboard


def test_small_chunk_canary_requires_matching_operation(tmp_path: Path) -> None:
    checkpoint = tmp_path / "checkpoint.json"
    _write_checkpoint(
        checkpoint,
        [_timeout_record(), _promoted_record(operation="office_extension.other_metadata.set_value")],
    )

    replay = replay_timeout_packages(checkpoint)

    assert replay[0].get("slow_replay_state") is None


def test_office_stage_timeout_becomes_office_boundary(tmp_path: Path) -> None:
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text(
        json.dumps(
            {"records": [{"status": "timeout", "stage": "office_gate", "package_id": "pkg-timeout", "chunk_id": "a"}]}
        ),
        encoding="utf-8",
    )

    merged = merge_office_timeout_boundaries({}, checkpoint)

    assert merged["pkg-timeout"]["status"] == "timeout"
    assert not replay_timeout_packages(checkpoint)


def test_office_summary_timeout_becomes_office_boundary(tmp_path: Path) -> None:
    office = tmp_path / "office.json"
    office.write_text(json.dumps({"summary": {"by_status": {"timeout": 1}}}), encoding="utf-8")
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "status": "timeout",
                        "office_result_file": str(office),
                        "package_id": "pkg-timeout",
                        "chunk_id": "a",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    merged = merge_office_timeout_boundaries({}, checkpoint)

    assert merged["pkg-timeout"]["status"] == "timeout"
    assert not replay_timeout_packages(checkpoint)


def _candidate(summary: dict, package_id: str) -> dict:
    return next(row for row in summary["candidate_packages"] if row["package_id"] == package_id)


def _write_office(path: Path, status: str, file_name: str) -> None:
    path.write_text(json.dumps({"results": [{"file": file_name, "status": status}]}), encoding="utf-8")


def _write_checkpoint(path: Path, records: list[dict]) -> None:
    path.write_text(json.dumps({"records": records}), encoding="utf-8")


def _timeout_record(operation: str = "office_extension.known_metadata.set_value") -> dict:
    record = {"status": "timeout", "package_id": "pkg-a", "family": "office_extension", "chunk_id": "old-a"}
    if operation:
        record["operation_ids"] = [operation]
    return record


def _promoted_record(operation: str = "office_extension.known_metadata.set_value", duration: float | None = None) -> dict:
    record = {
        "status": "promoted",
        "label": "canary-0001-abc",
        "package_id": "pkg-a",
        "family": "office_extension",
        "operation_ids": [operation],
        "chunk_id": "new-a",
        "planned_row_count": 5,
        "promoted_row_count": 5,
    }
    if duration is not None:
        record["duration_s"] = duration
    return record
