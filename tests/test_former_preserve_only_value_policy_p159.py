from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from former_preserve_only_value_policy import checked_requested_value, next_requested_value

P159 = "http://schemas.microsoft.com/office/powerpoint/2015/09/main"


def _row() -> dict:
    return {
        "qname": f"{{{P159}}}morph",
        "attribute_name": "option",
        "operation_id": "office_extension.known_metadata.set_value",
        "value_kind": "attribute",
    }


def test_p159_morph_option_uses_safe_enum():
    row = _row()

    actual = next_requested_value("byObject", 0, row)

    assert actual == "byWord"
    assert checked_requested_value("byObject", actual, row) == actual


def test_p159_morph_option_rejects_unknown_value():
    with pytest.raises(ValueError, match="schema_policy_unsafe_safe-enum"):
        checked_requested_value("byObject", "bySlide", _row())
