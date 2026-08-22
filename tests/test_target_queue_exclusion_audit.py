from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_target_queue_exclusion_audit import build_audit


def _target() -> dict:
    return {
        "rank": 1,
        "family": "office_extension",
        "qname": "{urn:test}node",
        "blocker_reason": "semantic_value_available_pending_proof",
        "operation_id": "office_extension.known_metadata.set_value",
        "hydration_status": "hydrated",
        "semantic_value_kind": "direct_attr",
        "recommended_action": "promote",
        "remaining_count": 1,
        "hydrated_count": 1,
        "expected_row_gain": 1,
    }


def _row(package: str = "pkg-a") -> dict:
    return {
        "package_id": package,
        "format": "pptx",
        "family": "office_extension",
        "qname": "{urn:test}node",
        "blocker_type": "semantic_value_available_pending_proof",
        "operation_id": "office_extension.known_metadata.set_value",
        "operation_hydration_status": "hydrated",
        "semantic_value_kind": "direct_attr",
        "part_name": "ppt/slides/slide1.xml",
    }


def test_office_boundary_explains_missing_quickproof() -> None:
    remaining = {
        "known_boundary_packages": [{"package_id": "pkg-a"}],
        "known_replay_timeout_packages": [],
        "candidate_packages": [{"recommended_action": "skip_boundary"}],
    }

    audit = build_audit({"ranked_targets": [_target()]}, remaining, [_row()], runner_planner=lambda _: {"planned_safe_rows": 1})

    assert audit["remaining_candidate_action_counts"] == {"skip_boundary": 1}
    assert audit["targets"][0]["dominant_exclusion"] == "known_office_boundary"


def test_large_runner_batch_explains_missing_quickproof() -> None:
    rows = [_row() | {"part_name": f"ppt/slides/slide{i}.xml"} for i in range(30)]

    audit = build_audit({"ranked_targets": [_target()]}, {}, rows, runner_planner=lambda items: {"planned_safe_rows": len(items)})

    assert audit["targets"][0]["dominant_exclusion"] == "quickproof_batch_too_large"
    assert audit["targets"][0]["planned_safe_rows_seen"] == 30


def test_candidate_outside_remaining_top100_is_visible() -> None:
    audit = build_audit({"ranked_targets": [_target()]}, {}, [_row()], runner_planner=lambda _: {"planned_safe_rows": 1})

    assert audit["targets"][0]["dominant_exclusion"] == "candidate_outside_remaining_top100"


def test_target_match_follows_queue_key_not_semantic_kind() -> None:
    rows = [_row(), _row("pkg-b") | {"semantic_value_kind": "descendant_attr"}]

    audit = build_audit({"ranked_targets": [_target()]}, {}, rows, runner_planner=lambda items: {"planned_safe_rows": len(items)})

    assert audit["targets"][0]["matching_row_count"] == 2


def test_promoted_rows_do_not_become_audit_quickproof_candidates() -> None:
    row = _row() | {"source_row_id": "source-a"}

    audit = build_audit(
        {"ranked_targets": [_target()]},
        {},
        [row],
        runner_planner=lambda _: {"planned_safe_rows": 1},
        promoted_sources={"source-a"},
    )

    assert audit["targets"][0]["dominant_exclusion"] == "already_promoted"
