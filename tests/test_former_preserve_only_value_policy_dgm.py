from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_schema_policy_unlock_candidates import build_candidates
from former_preserve_only_value_policy import checked_requested_value, next_requested_value

DSP = "http://schemas.microsoft.com/office/drawing/2008/diagram"
CDR = "http://schemas.openxmlformats.org/drawingml/2006/chartDrawing"


def _row(qname: str) -> dict:
    return {
        "qname": qname,
        "attribute_name": "name",
        "operation_id": "office_extension.known_metadata.set_value",
        "value_kind": "attribute",
    }


def test_diagram_shape_tree_name_uses_safe_string_value() -> None:
    row = _row(f"{{{DSP}}}spTree")

    requested = next_requested_value("", 4, row)

    assert requested == "Object [semantic-edit-4]"
    assert checked_requested_value("", requested, row) == requested


def test_diagram_drawing_name_uses_safe_string_value() -> None:
    row = _row(f"{{{DSP}}}drawing")

    requested = next_requested_value("", 5, row)

    assert requested == "Object [semantic-edit-5]"
    assert checked_requested_value("", requested, row) == requested


def test_diagram_name_rejects_control_characters() -> None:
    with pytest.raises(ValueError, match="schema_policy_unsafe_untyped-attribute"):
        checked_requested_value("", "bad\u0001name", _row(f"{{{DSP}}}spTree"))


def test_chart_drawing_shape_name_uses_safe_string_value() -> None:
    row = _row(f"{{{CDR}}}sp")

    requested = next_requested_value("Text Box 1", 6, row)

    assert requested == "Text Box 1 [semantic-edit-6]"
    assert checked_requested_value("Text Box 1", requested, row) == requested


def test_chart_drawing_group_shape_name_stays_blocked() -> None:
    with pytest.raises(ValueError, match="schema_policy_unsafe_untyped-attribute"):
        next_requested_value("Group 1", 1, _row(f"{{{CDR}}}grpSp"))


def test_schema_policy_surfaces_diagram_name_unlock_now() -> None:
    hydrated = [
        _hydrated(f"{{{DSP}}}spTree", "a"),
        _hydrated(f"{{{DSP}}}spTree", "b"),
        _hydrated(f"{{{DSP}}}drawing", "c"),
        _hydrated(f"{{{CDR}}}sp", "d"),
    ]

    summary = build_candidates({}, hydrated)
    by_qname = {row["qname"]: row for row in summary["candidates"]}

    assert by_qname[f"{{{DSP}}}spTree"]["recommended_action"] == "unlock_now"
    assert by_qname[f"{{{DSP}}}spTree"]["proposed_safe_replacement_value"] == "Object [semantic-edit-index]"
    assert by_qname[f"{{{DSP}}}drawing"]["recommended_action"] == "unlock_now"
    assert by_qname[f"{{{CDR}}}sp"]["recommended_action"] == "unlock_now"


def _hydrated(qname: str, row_id: str) -> dict:
    return _row(qname) | {
        "_policy_rejection_reason": "schema_policy_unsafe_untyped-attribute",
        "before_semantic_value": "",
        "operation_hydration_status": "hydrated",
        "package_id": "pkg-a",
        "row_id": row_id,
    }
