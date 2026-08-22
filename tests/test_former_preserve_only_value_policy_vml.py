from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from former_preserve_only_promote_hydrated import _payload
from former_preserve_only_value_policy import checked_requested_value, next_requested_value


def test_shape_defaults_fill_color_uses_spec_color_values():
    row = {
        "qname": "{urn:schemas-microsoft-com:office:office}shapedefaults",
        "attribute_name": "fillcolor",
        "operation_id": "office_extension.known_metadata.set_value",
        "value_kind": "attribute",
    }

    assert next_requested_value("#FFFFFF", 0, row) == "#00AA55"
    assert checked_requested_value("#FFFFFF", "#00AA55", row) == "#00AA55"
    with pytest.raises(ValueError, match="schema_policy_unsafe_safe-enum"):
        checked_requested_value("#FFFFFF", "not-a-color", row)


def test_vml_path_metadata_uses_t_f_policy():
    row = {
        "qname": "{urn:schemas-microsoft-com:vml}path",
        "attribute_name": "{urn:schemas-microsoft-com:office:office}extrusionok",
        "operation_id": "vml.path.metadata.set_value",
        "value_kind": "attribute",
    }

    assert next_requested_value("", 0, row) == "f"
    assert checked_requested_value("", "f", row) == "f"
    with pytest.raises(ValueError, match="schema_policy_unsafe_untyped-attribute"):
        checked_requested_value("", "maybe", row)


@pytest.mark.parametrize("operation_id", ["vml.shadow.set_enabled", "vml.textpath.set_enabled"])
def test_vml_boolean_operation_uses_t_f_policy_and_payload(operation_id):
    row = {
        "qname": "{urn:schemas-microsoft-com:vml}shadow",
        "attribute_name": "on",
        "operation_id": operation_id,
        "value_kind": "attribute",
        "part_name": "word/document.xml",
        "operation_target_selector": "/w:document/v:shadow[1]",
    }
    requested = next_requested_value("t", 0, row)

    assert requested == "f"
    assert checked_requested_value("t", requested, row) == requested
    assert _payload({"row": row, "requested": requested})["params"] == {"enabled": False}


def test_vml_image_title_uses_safe_string_policy_and_payload():
    row = {
        "qname": "{urn:schemas-microsoft-com:vml}imagedata",
        "attribute_name": "{urn:schemas-microsoft-com:office:office}title",
        "operation_id": "vml.image.metadata.set_title",
        "value_kind": "attribute",
        "part_name": "word/document.xml",
        "operation_target_selector": "/w:document/v:imagedata[1]",
    }
    requested = next_requested_value("", 0, row)

    assert checked_requested_value("", requested, row) == requested
    assert _payload({"row": row, "requested": requested})["params"] == {"title": requested}


def test_vml_numeric_image_title_remains_string_metadata():
    row = {
        "qname": "{urn:schemas-microsoft-com:vml}imagedata",
        "attribute_name": "{urn:schemas-microsoft-com:office:office}title",
        "operation_id": "vml.image.metadata.set_title",
        "value_kind": "attribute",
    }

    assert checked_requested_value("123", "123 [semantic-edit-0]", row) == "123 [semantic-edit-0]"


def test_vml_formula_eqn_uses_allowlisted_formula_policy():
    row = {
        "qname": "{urn:schemas-microsoft-com:vml}f",
        "attribute_name": "eqn",
        "operation_id": "vml.formula.eqn.set_value",
        "value_kind": "attribute",
    }

    assert next_requested_value("val #0", 0, row) == "sum #0 0 0"
    assert checked_requested_value("val #0", "sum #0 0 0", row) == "sum #0 0 0"
    with pytest.raises(ValueError, match="schema_policy_unsafe_untyped-attribute"):
        checked_requested_value("val #0", "bad formula", row)


def test_vml_formula_eqn_payload_omits_attribute_name():
    row = {
        "part_name": "word/header1.xml",
        "operation_target_selector": "/w:hdr/v:formulas/v:f[1]",
        "attribute_name": "eqn",
        "operation_id": "vml.formula.eqn.set_value",
        "value_kind": "attribute",
    }

    payload = _payload({"row": row, "requested": "sum #0 0 0"})

    assert payload["params"] == {"value": "sum #0 0 0"}


def test_anchorlock_presence_is_delete_only_policy():
    row = {
        "qname": "{urn:schemas-microsoft-com:office:word}anchorlock",
        "attribute_name": "",
        "operation_id": "legacy_office_drawing.anchorlock.presence.set_enabled",
        "value_kind": "presence",
    }

    assert next_requested_value("true", 0, row) == "false"
    assert checked_requested_value("true", "false", row) == "false"
    with pytest.raises(ValueError, match="schema_policy_unsafe_untyped-attribute"):
        checked_requested_value("false", "true", row)


def test_anchorlock_presence_payload_uses_enabled_false():
    row = {
        "part_name": "word/document.xml",
        "operation_target_selector": "/w:document/w:body/w:p/w:r/w:pict/v:shape/w10:anchorlock",
        "attribute_name": "",
        "operation_id": "legacy_office_drawing.anchorlock.presence.set_enabled",
        "value_kind": "presence",
    }

    payload = _payload({"row": row, "requested": "false"})

    assert payload["params"] == {"enabled": False}


def test_no_fill_presence_is_delete_only_and_uses_enabled_false():
    row = {"qname": "{http://schemas.microsoft.com/office/word/2010/wordml}noFill", "attribute_name": "", "operation_id": "office_extension.no_fill.presence.set_enabled", "value_kind": "presence", "part_name": "word/document.xml", "operation_target_selector": "/w:document/w:body/w:p/w:r/w:rPr/w14:textOutline/w14:noFill"}

    assert next_requested_value("true", 0, row) == "false"
    assert checked_requested_value("true", "false", row) == "false"
    assert _payload({"row": row, "requested": "false"})["params"] == {"enabled": False}


def test_bevel_presence_is_delete_only_and_uses_enabled_false():
    row = {"qname": "{http://schemas.microsoft.com/office/word/2010/wordml}bevel", "attribute_name": "", "operation_id": "office_extension.text_outline.bevel.presence.set_enabled", "value_kind": "presence", "part_name": "word/document.xml", "operation_target_selector": "/w:document/w:body/w:p/w:r/w:rPr/w14:textOutline/w14:bevel"}

    assert next_requested_value("true", 0, row) == "false"
    assert checked_requested_value("true", "false", row) == "false"
    assert _payload({"row": row, "requested": "false"})["params"] == {"enabled": False}


def test_numeric_leaf_text_uses_bounded_value_parameter():
    relative = {"qname": "{http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing}pctWidth", "attribute_name": "", "operation_id": "office_extension.relative_size.set_percentage", "value_kind": "text", "part_name": "word/document.xml", "operation_target_selector": "//wp14:pctWidth"}
    marker = {"qname": "{http://schemas.openxmlformats.org/drawingml/2006/chartDrawing}x", "attribute_name": "", "operation_id": "chart.drawing.marker_coordinate.set_value", "value_kind": "text", "part_name": "ppt/drawings/drawing1.xml", "operation_target_selector": "//cdr:x"}
    assert next_requested_value("50000", 0, relative) == "50001"
    with pytest.raises(ValueError, match="numeric"):
        checked_requested_value("50000", "-1", relative)
    assert next_requested_value("0.99", 0, marker) == "1"
    assert _payload({"row": marker, "requested": "1"})["params"] == {"value": "1"}


def test_pan_presence_is_delete_only():
    row = {"operation_id": "office_extension.transition_pan.presence.set_enabled", "part_name": "ppt/slides/slide1.xml", "operation_target_selector": "//p14:pan"}
    assert next_requested_value("true", 0, row) == "false"
    assert checked_requested_value("true", "false", row) == "false"
    assert _payload({"row": row, "requested": "false"})["params"] == {"enabled": False}


def test_prism_presence_is_delete_only():
    row = {"operation_id": "office_extension.transition_prism.presence.set_enabled", "part_name": "ppt/slides/slide1.xml", "operation_target_selector": "//p14:prism"}
    assert next_requested_value("true", 0, row) == "false"
    assert checked_requested_value("true", "false", row) == "false"
    assert _payload({"row": row, "requested": "false"})["params"] == {"enabled": False}


@pytest.mark.parametrize("local_name", ["ripple", "flythrough", "shred", "reveal"])
def test_transition_effect_presence_is_delete_only(local_name: str):
    operation = f"office_extension.transition_{local_name}.presence.set_enabled"
    row = {"operation_id": operation, "part_name": "ppt/slides/slide1.xml", "operation_target_selector": f"//p14:{local_name}"}
    assert next_requested_value("true", 0, row) == "false"
    assert checked_requested_value("true", "false", row) == "false"
    assert _payload({"row": row, "requested": "false"})["params"] == {"enabled": False}


def test_film_grain_presence_is_delete_only():
    operation = "office_extension.picture_effect.film_grain.presence.set_enabled"
    row = {"operation_id": operation, "part_name": "ppt/slides/slide1.xml", "operation_target_selector": "//a14:artisticFilmGrain"}
    assert next_requested_value("true", 0, row) == "false"
    assert checked_requested_value("true", "false", row) == "false"
    assert _payload({"row": row, "requested": "false"})["params"] == {"enabled": False}


def test_artistic_blur_presence_is_delete_only():
    operation = "office_extension.picture_effect.artistic_blur.presence.set_enabled"
    row = {"operation_id": operation, "part_name": "ppt/slides/slide1.xml", "operation_target_selector": "//a14:artisticBlur"}
    assert next_requested_value("true", 0, row) == "false"
    assert checked_requested_value("true", "false", row) == "false"
    assert _payload({"row": row, "requested": "false"})["params"] == {"enabled": False}


@pytest.mark.parametrize("operation,local", [("math.run_property.literal.presence.set_enabled", "lit"), ("math.run_property.normal_text.presence.set_enabled", "nor")])
def test_math_run_property_presence_is_delete_only(operation: str, local: str):
    row = {"operation_id": operation, "part_name": "word/document.xml", "operation_target_selector": f"//m:{local}"}
    assert next_requested_value("true", 0, row) == "false"
    assert checked_requested_value("true", "false", row) == "false"
    assert _payload({"row": row, "requested": "false"})["params"] == {"enabled": False}


def test_contextual_alternates_presence_is_delete_only():
    operation = "office_extension.contextual_alternates.presence.set_enabled"
    row = {"operation_id": operation, "part_name": "word/numbering.xml", "operation_target_selector": "//w14:cntxtAlts"}
    assert next_requested_value("true", 0, row) == "false"
    assert checked_requested_value("true", "false", row) == "false"
    assert _payload({"row": row, "requested": "false"})["params"] == {"enabled": False}


def test_textbox_flag_rejects_missing_attribute() -> None:
    row = {
        "qname": "{http://schemas.microsoft.com/office/word/2010/wordprocessingShape}cNvSpPr",
        "attribute_name": "txBox",
    }
    with pytest.raises(ValueError, match="schema_policy_unsafe_textbox-flag"):
        checked_requested_value("", "0", row)


@pytest.mark.parametrize("uri", ["http://schemas.microsoft.com/office/word/2010/wordprocessingShape", "http://schemas.microsoft.com/office/drawing/2008/diagram", "http://schemas.openxmlformats.org/drawingml/2006/chartDrawing"])
def test_textbox_flag_disables_explicit_true(uri: str) -> None:
    row = {"qname": f"{{{uri}}}cNvSpPr", "attribute_name": "txBox", "operation_id": "office_extension.known_metadata.set_value"}
    requested = next_requested_value("1", 0, row)
    assert requested == "0"
    assert checked_requested_value("1", requested, row) == requested
