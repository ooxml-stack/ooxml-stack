from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from former_preserve_only_value_policy import checked_requested_value, next_requested_value

P15 = "http://schemas.microsoft.com/office/powerpoint/2012/main"


def _row() -> dict:
    return {
        "qname": f"{{{P15}}}prstTrans",
        "attribute_name": "prst",
        "operation_id": "office_extension.known_metadata.set_value",
        "value_kind": "attribute",
    }


def test_p15_prst_transition_uses_observed_safe_preset():
    row = _row()

    actual = next_requested_value("pageCurlDouble", 0, row)

    assert actual == "pageCurlSingle"
    assert checked_requested_value("pageCurlDouble", actual, row) == actual


def test_p15_prst_transition_rejects_unknown_preset():
    with pytest.raises(ValueError, match="schema_policy_unsafe_safe-enum"):
        checked_requested_value("pageCurlDouble", "notAPreset", _row())
