from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_semantic_editability_target_queue import _blocker_summary
from build_semantic_editability_target_queue import _gap_summary_from_rows
from build_semantic_editability_target_queue import _hydration_summary_from_rows
from build_semantic_editability_target_queue import _ranked_queue
from build_semantic_editability_target_queue import _target_summary


def _row(qname: str, family: str = "office_extension") -> dict[str, str]:
    return {
        "family": family,
        "qname": qname,
        "blocker_type": "semantic_value_available_pending_proof",
        "operation_id": "office_extension.known_metadata.set_value",
        "operation_hydration_status": "hydrated",
        "semantic_value_kind": "direct_attr",
        "package_id": "pkg",
    }


def test_plain_hydrated_metadata_can_promote() -> None:
    queue = _ranked_queue([_row("{urn:test}hiddenFill")])

    assert queue[0]["recommended_action"] == "promote"
    assert queue[0]["expected_row_gain"] == 1


def test_identity_like_qnames_require_policy_split() -> None:
    rows = [_row("{urn:test}rowId"), _row("{urn:test}colId"), _row("{urn:test}uniqueId"), _row("{urn:test}modId")]

    queue = _ranked_queue(rows)

    assert {row["recommended_action"] for row in queue} == {"identity_policy_split"}
    assert {row["expected_row_gain"] for row in queue} == {0}


def test_binary_like_qnames_require_reference_model() -> None:
    queue = _ranked_queue([_row("{urn:test}svgBlip"), _row("{urn:test}imgProps")])

    assert {row["recommended_action"] for row in queue} == {"reference_model_or_binary_blocker"}
    assert {row["office_risk"] for row in queue} == {"high"}


def test_target_summary_uses_current_rows_over_stale_summary() -> None:
    gaps = [
        _row("{urn:test}title") | {"source_row_id": "a"},
        _row("{urn:test}shapeId") | {"source_row_id": "b", "blocker_type": "relationship_identity_like"},
        _row("{urn:test}svgBlip") | {"source_row_id": "c", "blocker_type": "binary_payload_reference"},
    ]
    hydration = [
        gaps[0] | {"operation_hydration_status": "hydrated"},
        gaps[1] | {"operation_hydration_status": "not_applicable"},
        gaps[2] | {"operation_hydration_status": "not_applicable"},
    ]
    stale_gap = {"former_preserve_only_denominator": 10, "semantic_editable_count": 1, "object_level_gap_row_count": 9}
    stale_hydration = {"hydrated_count": 99, "status_counts": {"hydrated": 99}}

    live_gap = _gap_summary_from_rows(gaps, stale_gap)
    live_hydration = _hydration_summary_from_rows(hydration, stale_hydration)
    target = _target_summary([], live_gap, live_hydration)
    blockers = _blocker_summary(gaps, live_gap, live_hydration)

    assert target["starting_semantic_editable_count"] == 7
    assert target["starting_blocker_count"] == 3
    assert target["hydrated_count"] == 1
    assert blockers["total_blocker_count"] == 3
    assert blockers["source_gap_summary_count"] == 3
