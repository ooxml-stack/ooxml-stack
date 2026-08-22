from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from former_preserve_only_value_policy import checked_requested_value, next_requested_value

W14 = "http://schemas.microsoft.com/office/word/2010/wordml"


def _row(local: str = "srgbClr") -> dict:
    return {
        "qname": f"{{{W14}}}{local}",
        "attribute_name": f"{{{W14}}}val",
        "operation_id": "office_extension.known_metadata.set_value",
        "value_kind": "attribute",
    }


def test_srgbclr_all_digit_hex_uses_color_oracle():
    requested = next_requested_value("000000", 0, _row())

    assert requested == "00AA55"
    assert checked_requested_value("000000", requested, _row()) == requested


def test_srgbclr_rejects_non_hex_color_value():
    with pytest.raises(ValueError, match="schema_policy_unsafe_hex-color"):
        checked_requested_value("000000", "00GG55", _row())


def test_unrelated_integer_val_still_uses_integer_policy():
    with pytest.raises(ValueError, match="schema_policy_unsafe_integer"):
        checked_requested_value("000000", "00AA55", _row("docId"))
