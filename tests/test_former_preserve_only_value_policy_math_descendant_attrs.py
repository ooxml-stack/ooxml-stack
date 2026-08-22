from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from former_preserve_only_math_policy import math_metadata_allowed
from former_preserve_only_value_policy import checked_requested_value, next_requested_value

MATH = "http://schemas.openxmlformats.org/officeDocument/2006/math"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML = "http://www.w3.org/XML/1998/namespace"


def _row(local: str, attr: str, selector: str) -> dict:
    return {
        "qname": f"{{{MATH}}}{local}",
        "attribute_name": attr,
        "operation_id": "math.object.metadata.set_value",
        "operation_target_selector": selector,
        "value_kind": "attribute",
    }


def test_mathpr_descendant_mathfont_uses_exact_font_allowlist():
    row = _row("mathPr", f"{{{MATH}}}val", "/w:settings/m:mathPr/m:mathFont")

    requested = next_requested_value("Cambria Math", 0, row)

    assert requested == "Cambria Math-semantic"
    assert checked_requested_value("Cambria Math", requested, row) == requested
    assert math_metadata_allowed(row) is True


def test_mathpr_val_without_descendant_target_stays_blocked():
    row = _row("mathPr", f"{{{MATH}}}val", "/w:settings/m:mathPr")

    assert math_metadata_allowed(row) is False
    with pytest.raises(ValueError, match="schema_policy_unsafe_untyped-attribute"):
        checked_requested_value("Cambria Math", "Cambria Math-semantic", row)


def test_rpr_descendant_style_uses_exact_style_allowlist():
    row = _row("rPr", f"{{{MATH}}}val", "/w:p/m:oMath/m:r/m:rPr/m:sty")

    requested = next_requested_value("p", 0, row)

    assert requested == "bi"
    assert checked_requested_value("p", requested, row) == requested
    assert math_metadata_allowed(row) is True


def test_rpr_descendant_script_uses_exact_script_allowlist():
    row = _row("rPr", f"{{{MATH}}}val", "/w:p/m:oMath/m:r/m:rPr/m:scr")

    requested = next_requested_value("double-struck", 0, row)

    assert requested == "script"
    assert checked_requested_value("double-struck", requested, row) == requested
    assert math_metadata_allowed(row) is True


def test_direct_script_target_uses_same_script_allowlist():
    row = _row("scr", f"{{{MATH}}}val", "/w:p/m:oMath/m:r/m:rPr/m:scr")

    requested = next_requested_value("double-struck", 0, row)

    assert requested == "script"
    assert checked_requested_value("double-struck", requested, row) == requested
    assert math_metadata_allowed(row) is True


def test_descendant_ctrlpr_font_attrs_are_allowed_with_context():
    row = _row("dPr", f"{{{W}}}ascii", "/w:p/m:oMath/m:d/m:dPr/m:ctrlPr/w:rPr/w:rFonts")

    requested = next_requested_value("Cambria Math", 0, row)

    assert requested == "Cambria Math-semantic"
    assert checked_requested_value("Cambria Math", requested, row) == requested
    assert math_metadata_allowed(row) is True


def test_lang_attr_without_ctrlpr_context_stays_blocked():
    row = _row("dPr", "lang", "/w:p/m:oMath/m:d/m:dPr")

    assert math_metadata_allowed(row) is False
    with pytest.raises(ValueError, match="schema_policy_unsafe_untyped-attribute"):
        checked_requested_value("en-US", "pt-BR", row)


def test_math_dispdef_empty_onoff_can_toggle_to_boolean():
    row = _row("dispDef", "val", "/w:settings/m:mathPr/m:dispDef")

    requested = next_requested_value("", 0, row)

    assert requested == "on"
    assert checked_requested_value("", requested, row) == requested
    assert math_metadata_allowed(row) is True


def test_math_onoff_rejects_unknown_value():
    row = _row("dispDef", "val", "/w:settings/m:mathPr/m:dispDef")

    with pytest.raises(ValueError, match="schema_policy_unsafe_safe-enum"):
        checked_requested_value("", "maybe", row)


def test_math_delimiter_child_uses_bounded_char_values():
    row = _row("begChr", f"{{{MATH}}}val", "/w:p/m:oMath/m:d/m:dPr/m:begChr")

    requested = next_requested_value("{", 0, row)

    assert requested == "["
    assert checked_requested_value("{", requested, row) == requested
    assert math_metadata_allowed(row) is True


def test_math_delimiter_parent_selector_uses_child_char_values():
    row = _row("dPr", f"{{{MATH}}}val", "/w:p/m:oMath/m:d/m:dPr/m:endChr")

    requested = next_requested_value("", 0, row)

    assert requested == "}"
    assert checked_requested_value("", requested, row) == requested
    assert math_metadata_allowed(row) is True


def test_math_jc_uses_spec_enum_values():
    row = _row("jc", f"{{{MATH}}}val", "/w:p/m:oMathPara/m:oMathParaPr/m:jc")

    requested = next_requested_value("centerGroup", 0, row)

    assert requested == "left"
    assert checked_requested_value("centerGroup", requested, row) == requested
    assert math_metadata_allowed(row) is True


def test_math_fraction_type_uses_spec_enum_values():
    row = _row("type", f"{{{MATH}}}val", "/w:p/m:oMath/m:f/m:fPr/m:type")

    requested = next_requested_value("noBar", 0, row)

    assert requested == "bar"
    assert checked_requested_value("noBar", requested, row) == requested
    assert math_metadata_allowed(row) is True


def test_math_text_space_uses_xml_space_domain():
    row = _row("t", f"{{{XML}}}space", "/w:p/m:oMath/m:r/m:t")

    requested = next_requested_value("preserve", 0, row)

    assert requested == "default"
    assert checked_requested_value("preserve", requested, row) == requested
    assert math_metadata_allowed(row) is True


def test_math_run_font_attr_uses_font_allowlist():
    row = _row("r", f"{{{W}}}ascii", "/w:p/m:oMath/m:r/w:rPr/w:rFonts")

    requested = next_requested_value("Cambria Math", 0, row)

    assert requested == "Cambria Math-semantic"
    assert checked_requested_value("Cambria Math", requested, row) == requested
    assert math_metadata_allowed(row) is True
