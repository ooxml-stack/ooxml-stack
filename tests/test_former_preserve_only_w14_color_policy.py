from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from former_preserve_only_value_policy import checked_requested_value, next_requested_value

W14 = "http://schemas.microsoft.com/office/word/2010/wordml"


def _row(local: str, attr: str = f"{{{W14}}}val", selector: str = "") -> dict[str, str]:
    return {
        "attribute_name": attr,
        "operation_id": "office_extension.known_metadata.set_value",
        "operation_target_selector": selector,
        "qname": f"{{{W14}}}{local}",
        "value_kind": "attribute",
    }


@pytest.mark.parametrize("local", ["extrusionClr", "contourClr"])
def test_w14_parent_color_container_uses_srgb_hex_value(local: str) -> None:
    row = _row(local, selector=f"/w:rPr/w14:props3d/w14:{local}/w14:srgbClr")

    requested = next_requested_value("000000", 0, row)

    assert requested == "00AA55"
    assert checked_requested_value("000000", requested, row) == requested


def test_w14_parent_color_container_rejects_non_srgb_selector() -> None:
    row = _row("extrusionClr", selector="/w:rPr/w14:props3d/w14:extrusionClr")

    with pytest.raises(ValueError, match="schema_policy_unsafe_integer"):
        checked_requested_value("000000", "00AA55", row)


def test_w14_round_empty_value_uses_on_off_domain() -> None:
    row = _row("round", attr="val")

    requested = next_requested_value("", 0, row)

    assert requested == "0"
    assert checked_requested_value("", requested, row) == requested


def test_w14_sat_mod_stays_integer_not_hex_color() -> None:
    row = _row("satMod", selector="/w14:schemeClr/w14:satMod")

    requested = next_requested_value("200000", 0, row)

    assert requested == "199999"
    assert checked_requested_value("200000", requested, row) == requested
