from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from former_preserve_only_numeric_leaf import checked_numeric_value, next_numeric_value, numeric_attribute_operation
from former_preserve_only_promote_hydrated import _payload


def _row(qname: str) -> dict:
    return {
        "qname": qname,
        "operation_id": "office_extension.position_percentage_offset.set_percentage",
    }


def test_position_percentage_uses_non_negative_integer_oracle():
    qname = "{http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing}pctPosVOffset"
    row = _row(qname)

    assert next_numeric_value("2300", row) == "2301"
    assert checked_numeric_value("2300", "2301", row) == "2301"


@pytest.mark.parametrize("value", ["-1", "1.5", "NaN"])
def test_position_percentage_rejects_non_integer_values(value: str):
    qname = "{http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing}pctPosVOffset"

    with pytest.raises(ValueError, match="schema_policy_unsafe_numeric_leaf|invalid numeric leaf"):
        checked_numeric_value("2300", value, _row(qname))


def test_media_trim_uses_explicit_non_negative_decimal_oracle():
    qname = "{http://schemas.microsoft.com/office/powerpoint/2010/main}trim"
    row = {"qname": qname, "semantic_value_kind": "direct_attr", "operation_id": "office_extension.media_trim.set_end"}

    assert numeric_attribute_operation(row, "end") == row["operation_id"]
    assert next_numeric_value("5652.700195", row) == "5652.700196"
    assert checked_numeric_value("5652.700195", "5652.700196", row) == "5652.700196"
    payload_row = row | {"attribute_name": "end", "part_name": "ppt/slides/slide1.xml", "operation_target_selector": "//p14:trim"}
    assert _payload({"row": payload_row, "requested": "5652.700196"})["params"] == {"value": "5652.700196"}


@pytest.mark.parametrize("value", ["-1", "NaN", "Infinity"])
def test_media_trim_rejects_invalid_numbers(value: str):
    row = {"operation_id": "office_extension.media_trim.set_end"}
    with pytest.raises(ValueError, match="schema_policy_unsafe_numeric_leaf|invalid numeric leaf"):
        checked_numeric_value("1", value, row)
