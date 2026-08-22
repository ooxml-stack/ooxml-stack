from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from former_preserve_only_math_policy import math_metadata_allowed
from former_preserve_only_value_policy import checked_requested_value, next_requested_value


def _row(uri: str, local: str, attr: str) -> dict:
    return {
        "qname": f"{{{uri}}}{local}",
        "attribute_name": attr if attr.startswith("{") else attr,
        "operation_id": "office_extension.known_metadata.set_value",
        "value_kind": "attribute",
    }


def test_idmap_ext_uses_vml_schema_enum():
    row = _row("urn:schemas-microsoft-com:office:office", "idmap", "{urn:schemas-microsoft-com:vml}ext")

    requested = next_requested_value("edit", 0, row)

    assert requested == "view"
    assert checked_requested_value("edit", requested, row) == requested


def test_idmap_ext_rejects_unknown_value():
    row = _row("urn:schemas-microsoft-com:office:office", "idmap", "{urn:schemas-microsoft-com:vml}ext")

    with pytest.raises(ValueError, match="schema_policy_unsafe_safe-enum"):
        checked_requested_value("edit", "author", row)


def test_wps_text_frame_type_is_exact_observed_allowlist():
    row = _row("http://www.wps.cn/officeDocument/2022/drawingmlCustomData", "textFrameExt", "type")

    requested = next_requested_value("text", 0, row)

    assert requested == "text-semantic"
    assert checked_requested_value("text", requested, row) == requested


def test_model3d_raster_renderer_name_is_exact_allowlist():
    row = _row("http://schemas.microsoft.com/office/drawing/2017/model3d", "raster", "rName")

    requested = next_requested_value("Office3DRenderer", 0, row)

    assert requested == "Office3DRenderer-semantic"
    assert checked_requested_value("Office3DRenderer", requested, row) == requested


def test_c15_sppr_prst_uses_preset_geometry_values():
    row = _row("http://schemas.microsoft.com/office/drawing/2012/chart", "spPr", "prst")

    requested = next_requested_value("rect", 0, row)

    assert requested == "wedgeRectCallout"
    assert checked_requested_value("rect", requested, row) == requested


def test_unrelated_type_attribute_stays_locked():
    row = _row("http://www.wps.cn/officeDocument/2022/drawingmlCustomData", "otherExt", "type")

    with pytest.raises(ValueError, match="schema_policy_unsafe_untyped-attribute"):
        checked_requested_value("text", "text-semantic", row)


def test_math_ctrlpr_ascii_is_exact_font_allowlist():
    row = _row("http://schemas.openxmlformats.org/officeDocument/2006/math", "ctrlPr", "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}ascii")
    row["operation_id"] = "math.object.metadata.set_value"

    requested = next_requested_value("Cambria Math", 0, row)

    assert requested == "Cambria Math-semantic"
    assert checked_requested_value("Cambria Math", requested, row) == requested
    assert math_metadata_allowed(row) is True


def test_math_ctrlpr_lang_is_exact_observed_allowlist():
    row = _row("http://schemas.openxmlformats.org/officeDocument/2006/math", "ctrlPr", "lang")
    row["operation_id"] = "math.object.metadata.set_value"

    requested = next_requested_value("pt-BR", 0, row)

    assert requested == "en-US"
    assert checked_requested_value("pt-BR", requested, row) == requested
    assert math_metadata_allowed(row) is True


def test_word2010_fill_values_are_scheme_colors_only():
    row = _row("http://schemas.microsoft.com/office/word/2010/wordml", "textFill", "{http://schemas.microsoft.com/office/word/2010/wordml}val")

    requested = next_requested_value("tx1", 0, row)

    assert requested == "accent1"
    assert checked_requested_value("tx1", requested, row) == requested
    with pytest.raises(ValueError, match="schema_policy_unsafe_scheme-color"):
        checked_requested_value("tx1", "not-a-scheme-color", row)
