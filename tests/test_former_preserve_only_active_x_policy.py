from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from former_preserve_only_value_policy import checked_requested_value, next_requested_value

AX = "http://schemas.microsoft.com/office/2006/activeX"


def _row() -> dict[str, str]:
    return {
        "attribute_name": f"{{{AX}}}classid",
        "operation_id": "office_extension.known_metadata.set_value",
        "qname": f"{{{AX}}}ocx",
        "value_kind": "attribute",
    }


def test_active_x_ocx_classid_cycles_known_values() -> None:
    before = "{5512D110-5CC6-11CF-8D67-00AA00BDCE1D}"

    requested = next_requested_value(before, 0, _row())

    assert requested == "{5512D116-5CC6-11CF-8D67-00AA00BDCE1D}"
    assert checked_requested_value(before, requested, _row()) == requested


def test_active_x_ocx_classid_rejects_unknown_guid() -> None:
    before = "{5512D110-5CC6-11CF-8D67-00AA00BDCE1D}"

    with pytest.raises(ValueError, match="schema_policy_unsafe_safe-enum"):
        checked_requested_value(before, "{00000000-0000-0000-0000-000000000000}", _row())
