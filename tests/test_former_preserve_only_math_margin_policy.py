from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from former_preserve_only_math_policy import math_metadata_allowed
from former_preserve_only_value_policy import checked_requested_value, next_requested_value

M = "http://schemas.openxmlformats.org/officeDocument/2006/math"


def _row(local: str) -> dict[str, str]:
    return {
        "attribute_name": f"{{{M}}}val",
        "operation_id": "math.object.metadata.set_value",
        "operation_target_selector": f"/w:document/w:body/m:oMathPara/m:{local}",
        "qname": f"{{{M}}}{local}",
        "value_kind": "attribute",
    }


@pytest.mark.parametrize(
    "local,before,expected",
    [("lMargin", "0", "1"), ("rMargin", "0", "1"), ("wrapIndent", "1440", "1441")],
)
def test_math_margin_val_allows_integer_edit(local: str, before: str, expected: str) -> None:
    row = _row(local)

    requested = next_requested_value(before, 0, row)

    assert math_metadata_allowed(row)
    assert requested == expected
    assert checked_requested_value(before, requested, row) == requested


def test_math_margin_val_rejects_non_integer() -> None:
    with pytest.raises(ValueError, match="schema_policy_unsafe_integer"):
        checked_requested_value("1440", "1440pt", _row("wrapIndent"))
