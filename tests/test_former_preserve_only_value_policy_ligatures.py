from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from former_preserve_only_value_policy import checked_requested_value, next_requested_value

W14 = "http://schemas.microsoft.com/office/word/2010/wordml"


def _row() -> dict:
    return {
        "qname": f"{{{W14}}}ligatures",
        "attribute_name": f"{{{W14}}}val",
        "operation_id": "office_extension.known_metadata.set_value",
        "value_kind": "attribute",
    }


def test_ligatures_uses_observed_safe_value():
    row = _row()

    actual = next_requested_value("standardContextual", 0, row)

    assert actual == "none"
    assert checked_requested_value("standardContextual", actual, row) == actual


def test_ligatures_rejects_unknown_value():
    with pytest.raises(ValueError, match="schema_policy_unsafe_safe-enum"):
        checked_requested_value("standardContextual", "historical", _row())
