from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from former_preserve_only_promote_hydrated import _plans, _select_rows
from former_preserve_only_office_boundaries import failed_office_packages
from former_preserve_only_promoted_index import row_target_key
from former_preserve_only_value_policy import checked_requested_value, next_requested_value


W14 = "http://schemas.microsoft.com/office/word/2010/wordml"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
A14 = "http://schemas.microsoft.com/office/drawing/2010/main"
DSP = "http://schemas.microsoft.com/office/drawing/2008/diagram"
CDR = "http://schemas.openxmlformats.org/drawingml/2006/chartDrawing"
P14 = "http://schemas.microsoft.com/office/powerpoint/2010/main"
P15 = "http://schemas.microsoft.com/office/powerpoint/2012/main"
WPS = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"


def _row(qname: str, attr: str, value_kind: str = "attribute") -> dict:
    return {
        "qname": qname,
        "attribute_name": attr,
        "operation_id": "office_extension.known_metadata.set_value",
        "value_kind": value_kind,
    }


def test_enum_value_uses_schema_legal_successor():
    row = _row(f"{{{W14}}}camera", "prst")

    assert next_requested_value("orthographicFront", 0, row) == "perspectiveFront"


def test_hidden_scene_camera_uses_schema_legal_successor():
    row = _row(f"{{{A14}}}hiddenScene3d", "prst")

    requested = next_requested_value("orthographicFront", 0, row)

    assert requested == "perspectiveFront"
    assert checked_requested_value("orthographicFront", requested, row) == requested


def test_hidden_scene_camera_rejects_illegal_preset():
    row = _row(f"{{{A14}}}hiddenScene3d", "prst")

    with pytest.raises(ValueError, match="schema_policy_unsafe_enum-value"):
        checked_requested_value("orthographicFront", "not-a-camera-preset", row)


def test_explicit_illegal_enum_value_is_rejected():
    row = _row(f"{{{W14}}}camera", "prst")

    with pytest.raises(ValueError, match="schema_policy_unsafe_enum-value"):
        checked_requested_value("orthographicFront", "orthographicFront-campaign-0", row)


def test_unknown_attribute_string_does_not_get_campaign_suffix():
    row = _row("{urn:example}privateThing", "name")

    with pytest.raises(ValueError, match="schema_policy_unsafe_untyped-attribute"):
        next_requested_value("before", 7, row)


def test_powerpoint_section_name_uses_safe_string_value():
    row = _row(f"{{{P14}}}section", "name")

    requested = next_requested_value("Intro", 7, row)

    assert requested == "Intro [semantic-edit-7]"
    assert checked_requested_value("Intro", requested, row) == requested


def test_powerpoint_section_list_name_uses_safe_string_value():
    row = _row(f"{{{P14}}}sectionLst", "name")

    requested = next_requested_value("默认节", 3, row)

    assert requested == "默认节 [semantic-edit-3]"
    assert checked_requested_value("默认节", requested, row) == requested


def test_powerpoint_guide_orientation_uses_safe_enum_value():
    row = _row(f"{{{P15}}}guide", "orient")

    requested = next_requested_value("horz", 0, row)

    assert requested == "vert"
    assert checked_requested_value("horz", requested, row) == requested


def test_powerpoint_guide_orientation_rejects_unknown_value():
    row = _row(f"{{{P15}}}sldGuideLst", "orient")

    with pytest.raises(ValueError, match="schema_policy_unsafe_safe-enum"):
        checked_requested_value("horz", "diagonal", row)


def test_non_visual_object_name_uses_safe_string_value():
    row = _row(f"{{{WPS}}}cNvPr", "name")

    requested = next_requested_value("Rectangle 19", 5, row)

    assert requested == "Rectangle 19 [semantic-edit-5]"
    assert checked_requested_value("Rectangle 19", requested, row) == requested


def test_empty_diagram_non_visual_name_uses_object_label():
    row = _row(f"{{{DSP}}}cNvPr", "name")

    requested = next_requested_value("", 2, row)

    assert requested == "Object [semantic-edit-2]"
    assert checked_requested_value("", requested, row) == requested


def test_chart_drawing_non_visual_name_uses_safe_string_value():
    row = _row(f"{{{CDR}}}cNvPr", "name")

    requested = next_requested_value("Text Box 1", 8, row)

    assert requested == "Text Box 1 [semantic-edit-8]"
    assert checked_requested_value("Text Box 1", requested, row) == requested


def test_hidden_fill_scheme_color_uses_safe_successor():
    row = _row(f"{{{A14}}}hiddenFill", "val")

    requested = next_requested_value("accent1", 0, row)

    assert requested == "accent2"
    assert checked_requested_value("accent1", requested, row) == requested


def test_hidden_fill_scheme_color_rejects_unknown_value():
    row = _row(f"{{{A14}}}hiddenFill", "val")

    with pytest.raises(ValueError, match="schema_policy_unsafe_scheme-color"):
        checked_requested_value("accent1", "not-a-scheme-color", row)


def test_schema_boolean_attribute_allows_absent_to_boolean():
    row = _row(f"{{{A14}}}useLocalDpi", "val")
    assert next_requested_value("", 0, row) == "true"
    assert checked_requested_value("", "true", row) == "true"
    with pytest.raises(ValueError, match="schema_policy_unsafe_boolean"):
        checked_requested_value("", "maybe", row)


def test_wordprocessing_shape_bw_mode_uses_black_white_enum():
    row = _row(f"{{{WPS}}}spPr", "bwMode")
    requested = next_requested_value("auto", 0, row)

    assert requested == "clr"
    assert checked_requested_value("auto", requested, row) == requested


def test_omml_break_binary_uses_spec_enum_fallback():
    row = _row(f"{{{M}}}brkBin", "val")

    requested = next_requested_value("before", 0, row)

    assert requested == "after"
    assert checked_requested_value("before", requested, row) == requested


def test_text_rows_can_still_use_campaign_text():
    row = _row("{urn:example}privateThing", "", "text")

    assert next_requested_value("before", 7, row) == "before-campaign-7"


def test_boolean_attribute_still_toggles():
    row = _row("{urn:example}privateThing", "enabled")

    requested = next_requested_value("true", 0, row)

    assert checked_requested_value("true", requested, row) == "false"


def test_unicode_digit_text_is_not_treated_as_integer():
    row = _row("{urn:example}privateThing", "", "text")

    assert next_requested_value("²", 0, row) == "²-campaign-0"


def test_hydrated_planner_skips_schema_policy_unsafe_rows(monkeypatch):
    unsafe = _plan_row(f"{{{W14}}}docId", f"{{{W14}}}val", "attribute")
    safe = _plan_row("{urn:example}privateThing", "", "text")

    monkeypatch.setattr("former_preserve_only_promote_hydrated._read_value", lambda path, row: "before")

    args = type("Args", (), {"requested_value": "", "package_id": "", "max_rows": 20})()
    plans = _plans([unsafe, safe], args)

    assert args.skipped_policy_rows == 1
    assert [item["row"] for item in plans] == [safe]


def test_hydrated_planner_skips_math_container_text_targets(monkeypatch):
    unsafe = _plan_row("{urn:math}sSup", "", "text") | {
        "operation_id": "math.run.set_text",
        "operation_target_selector": "/w:document/w:body/m:oMath/m:sSup",
    }
    safe = _plan_row("{urn:math}r", "", "text") | {
        "operation_id": "math.run.set_text",
        "operation_target_selector": "/w:document/w:body/m:oMath/m:r[1]",
    }
    monkeypatch.setattr("former_preserve_only_promote_hydrated._read_value", lambda path, row: "before")

    args = type("Args", (), {"requested_value": "", "package_id": "", "max_rows": 20})()
    plans = _plans([unsafe, safe], args)

    assert args.skipped_policy_rows == 1
    assert [item["row"] for item in plans] == [safe]


def test_hydrated_planner_skips_math_metadata_targets(monkeypatch):
    unsafe = _plan_row("{urn:math}unknownVal", "{urn:math}val", "attribute") | {
        "operation_id": "math.object.metadata.set_value",
    }
    allowed = _plan_row(f"{{{M}}}brkBin", f"{{{M}}}val", "attribute") | {
        "operation_id": "math.object.metadata.set_value",
        "row_id": "allowed-math",
    }
    safe = _plan_row("{urn:math}r", "", "text") | {
        "operation_id": "math.run.set_text",
        "operation_target_selector": "/w:document/w:body/m:oMath/m:r",
    }
    monkeypatch.setattr("former_preserve_only_promote_hydrated._read_value", lambda path, row: "before" if row is allowed else "after")

    args = type("Args", (), {"requested_value": "", "package_id": "", "max_rows": 20})()
    plans = _plans([unsafe, allowed, safe], args)

    assert args.skipped_policy_rows == 1
    assert [item["row"] for item in plans] == [allowed, safe]


def test_explicit_package_selection_does_not_pretruncate(monkeypatch):
    rows = [_select_row("same", "a"), _select_row("same", "b"), _select_row("same", "c")]
    rows[1]["qname"] = "{urn:example}filtered"
    monkeypatch.setattr("former_preserve_only_promote_hydrated._size_mb", lambda row: 1.0)
    monkeypatch.setattr("former_preserve_only_promote_hydrated.promoted_index", lambda path: (set(), set()))
    monkeypatch.setattr(
        "former_preserve_only_promote_hydrated._read_jsonl",
        lambda path: [] if path.name == "promotion-rows.jsonl" else rows,
    )

    args = type("Args", (), {"package_id": "same", "family": "", "operation_id": "", "qname": "{urn:example}filtered", "attribute_name": "", "max_package_mb": 5.0})()

    assert [row["row_id"] for row in _select_rows(args)] == ["b"]


def test_hydrated_selection_skips_already_promoted_target(monkeypatch):
    row = _select_row("same", "a")
    monkeypatch.setattr("former_preserve_only_promote_hydrated._size_mb", lambda row: 1.0)
    monkeypatch.setattr("former_preserve_only_promote_hydrated.promoted_index", lambda path: (set(), {row_target_key(row)}))
    monkeypatch.setattr("former_preserve_only_promote_hydrated._read_jsonl", lambda path: [row])

    args = type("Args", (), {"package_id": "same", "family": "", "operation_id": "", "max_package_mb": 5.0})()

    assert _select_rows(args) == []


def test_failed_office_packages_reads_boundary_json(tmp_path):
    _write_office_json(tmp_path / "api-fail.json", False, "api-b1-docx_ms_expansion_189_fly-minimal-wrap.docx")
    _write_office_json(tmp_path / "api-pass.json", True, "api-b1-pptx_ms_expansion_093_ppt-10-6.pptx")

    assert failed_office_packages(tmp_path) == {"docx_ms_expansion_189_fly-minimal-wrap"}


def _plan_row(qname: str, attr: str, value_kind: str) -> dict:
    return _row(qname, attr, value_kind) | {
        "input_file": "unused.docx",
        "package_id": "unused",
        "part_name": "word/document.xml",
        "operation_target_selector": "/root/item",
    }


def _select_row(package_id: str, row_id: str) -> dict:
    return _plan_row("{urn:example}thing", "", "text") | {
        "row_id": row_id,
        "source_row_id": row_id,
        "package_id": package_id,
        "operation_hydration_status": "hydrated",
    }


def _write_office_json(path: Path, gate_pass: bool, file_name: str) -> None:
    data = {"summary": {"gate_pass": gate_pass}, "results": [{"file": file_name}]}
    path.write_text(json.dumps(data), encoding="utf-8")
