from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from former_preserve_only_value_policy import checked_requested_value, next_requested_value

WPS = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"


def _row(attr: str) -> dict:
    return {
        "qname": f"{{{WPS}}}bodyPr",
        "attribute_name": attr,
        "operation_id": "office_extension.known_metadata.set_value",
        "value_kind": "attribute",
    }


@pytest.mark.parametrize(
    ("attr", "before", "expected"),
    [("wrap", "square", "none"), ("vert", "horz", "vert"), ("anchor", "ctr", "t")],
)
def test_bodypr_enum_attrs_use_schema_successor(attr, before, expected):
    requested = next_requested_value(before, 0, _row(attr))

    assert requested == expected
    assert checked_requested_value(before, requested, _row(attr)) == requested


@pytest.mark.parametrize("attr", ["wrap", "vert", "anchor"])
def test_bodypr_enum_attrs_reject_unknown_value(attr):
    with pytest.raises(ValueError, match="schema_policy_unsafe_enum-value"):
        checked_requested_value("square" if attr == "wrap" else "horz", "diagonal", _row(attr))
