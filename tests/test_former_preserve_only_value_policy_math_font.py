from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from former_preserve_only_math_policy import math_metadata_allowed
from former_preserve_only_value_policy import checked_requested_value, next_requested_value

MATH = "http://schemas.openxmlformats.org/officeDocument/2006/math"


def _row(local: str = "mathFont") -> dict:
    return {
        "qname": f"{{{MATH}}}{local}",
        "attribute_name": f"{{{MATH}}}val",
        "operation_id": "math.object.metadata.set_value",
        "value_kind": "attribute",
    }


def test_math_font_uses_observed_safe_value():
    row = _row()

    actual = next_requested_value("Cambria Math", 0, row)

    assert actual == "Cambria Math-semantic"
    assert checked_requested_value("Cambria Math", actual, row) == actual
    assert math_metadata_allowed(row) is True


def test_math_font_rejects_unknown_value():
    with pytest.raises(ValueError, match="schema_policy_unsafe_safe-enum"):
        checked_requested_value("Cambria Math", "Unknown Math", _row())


def test_math_pr_parent_context_stays_blocked():
    assert math_metadata_allowed(_row("mathPr")) is False
