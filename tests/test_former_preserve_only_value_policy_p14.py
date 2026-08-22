from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from former_preserve_only_value_policy import checked_requested_value, next_requested_value

P14 = "http://schemas.microsoft.com/office/powerpoint/2010/main"


def _row(qname: str, attr: str) -> dict:
    return {
        "qname": qname,
        "attribute_name": attr,
        "operation_id": "office_extension.known_metadata.set_value",
        "value_kind": "attribute",
    }


@pytest.mark.parametrize(("local", "before", "requested"), [
    ("conveyor", "l", "r"),
    ("doors", "vert", "horz"),
    ("flip", "r", "l"),
    ("gallery", "l", "r"),
    ("flythrough", "out", "in"),
    ("pan", "u", "d"),
    ("prism", "u", "d"),
    ("switch", "r", "l"),
    ("vortex", "r", "l"),
    ("warp", "in", "out"),
])
def test_p14_transition_dir_uses_safe_enum(local, before, requested):
    row = _row(f"{{{P14}}}{local}", "dir")

    actual = next_requested_value(before, 0, row)

    assert actual == requested
    assert checked_requested_value(before, actual, row) == actual


def test_p14_conveyor_dir_rejects_unknown_value():
    row = _row(f"{{{P14}}}conveyor", "dir")

    with pytest.raises(ValueError, match="schema_policy_unsafe_safe-enum"):
        checked_requested_value("l", "diagonal", row)
