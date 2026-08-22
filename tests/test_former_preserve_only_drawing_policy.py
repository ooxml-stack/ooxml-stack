from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from former_preserve_only_value_policy import checked_requested_value, next_requested_value

CDR = "http://schemas.openxmlformats.org/drawingml/2006/chartDrawing"
AHYP = "http://schemas.microsoft.com/office/drawing/2018/hyperlinkcolor"
DGM1612 = "http://schemas.microsoft.com/office/drawing/2016/12/diagram"


def _row(selector: str = "/c:userShapes/cdr:relSizeAnchor/cdr:sp/cdr:txBody/a:bodyPr") -> dict[str, str]:
    return {
        "attribute_name": "vertOverflow",
        "operation_id": "chart.drawing.metadata.set_value",
        "operation_target_selector": selector,
        "qname": f"{{{CDR}}}txBody",
        "value_kind": "attribute",
    }


def test_chart_drawing_text_vert_overflow_uses_spec_enum_values() -> None:
    requested = next_requested_value("clip", 0, _row())

    assert requested == "overflow"
    assert checked_requested_value("clip", requested, _row()) == requested


def test_chart_drawing_text_vert_overflow_rejects_unknown_value() -> None:
    with pytest.raises(ValueError, match="schema_policy_unsafe_safe-enum"):
        checked_requested_value("clip", "clip-semantic", _row())


def test_chart_drawing_text_vert_overflow_requires_bodypr_selector() -> None:
    with pytest.raises(ValueError, match="schema_policy_unsafe_untyped-attribute"):
        next_requested_value("clip", 0, _row("/c:userShapes/cdr:sp/cdr:txBody"))


def test_hyperlink_color_uses_office_2019_enum_values() -> None:
    row = {
        "attribute_name": "val",
        "operation_id": "office_extension.known_metadata.set_value",
        "operation_target_selector": "/p:sld/p:cSld/p:spTree/p:sp/a:hlinkClick/a:extLst/a:ext/ahyp:hlinkClr",
        "qname": f"{{{AHYP}}}hlinkClr",
        "value_kind": "attribute",
    }

    assert next_requested_value("tx", 0, row) == "hlink"
    assert checked_requested_value("tx", "hlink", row) == "hlink"
    with pytest.raises(ValueError, match="schema_policy_unsafe_safe-enum"):
        checked_requested_value("tx", "tx-semantic", row)


def test_diagram_shape_descendant_preset_dash_uses_drawing_enum() -> None:
    row = {
        "attribute_name": "val",
        "operation_id": "office_extension.known_metadata.set_value",
        "operation_target_selector": "/dgm:layoutDef/dgm:layoutNode/dgm:extLst/a:ext/dgm1612:spPr/a:ln/a:prstDash",
        "qname": f"{{{DGM1612}}}spPr",
        "value_kind": "attribute",
    }

    assert next_requested_value("dash", 0, row) == "solid"
    assert checked_requested_value("dash", "solid", row) == "solid"
    with pytest.raises(ValueError, match="schema_policy_unsafe_safe-enum"):
        checked_requested_value("dash", "dash-semantic", row)


def test_hidden_effects_descendant_alignment_uses_drawing_enum() -> None:
    row = {
        "attribute_name": "algn",
        "operation_id": "office_extension.known_metadata.set_value",
        "operation_target_selector": "/p:sldLayout/p:cSld/p:spTree/p:sp/p:spPr/a:extLst/a:ext/a14:hiddenEffects/a:effectLst/a:outerShdw",
        "qname": "{http://schemas.microsoft.com/office/drawing/2010/main}hiddenEffects",
        "value_kind": "attribute",
    }

    requested = next_requested_value("ctr", 0, row)
    assert requested in {"tl", "t", "tr", "l", "r", "bl", "b", "br"}
    assert checked_requested_value("ctr", requested, row) == requested
    with pytest.raises(ValueError, match="schema_policy_unsafe_enum-value"):
        checked_requested_value("ctr", "center", row)
