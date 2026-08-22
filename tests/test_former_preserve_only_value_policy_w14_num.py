from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from former_preserve_only_value_policy import checked_requested_value, next_requested_value

W14 = "http://schemas.microsoft.com/office/word/2010/wordml"


def _row(local: str, attr_uri: str = W14) -> dict:
    return {
        "qname": f"{{{W14}}}{local}",
        "attribute_name": f"{{{attr_uri}}}val",
        "operation_id": "office_extension.known_metadata.set_value",
        "value_kind": "attribute",
    }


def test_w14_num_spacing_uses_sdk_enum_allowlist():
    row = _row("numSpacing")

    requested = next_requested_value("default", 0, row)

    assert requested == "proportional"
    assert checked_requested_value("default", requested, row) == requested
    assert checked_requested_value("tabular", "default", row) == "default"


def test_w14_num_form_uses_sdk_enum_allowlist():
    row = _row("numForm")

    requested = next_requested_value("default", 0, row)

    assert requested == "lining"
    assert checked_requested_value("default", requested, row) == requested
    assert checked_requested_value("lining", "oldStyle", row) == "oldStyle"


def test_w14_num_spacing_rejects_unknown_value():
    with pytest.raises(ValueError, match="schema_policy_unsafe_safe-enum"):
        checked_requested_value("default", "monospace", _row("numSpacing"))


def test_unrelated_w14_val_attribute_stays_locked():
    with pytest.raises(ValueError, match="schema_policy_unsafe_safe-enum"):
        checked_requested_value("default", "lining", _row("round"))


def test_w14_num_form_requires_w14_val_attribute():
    with pytest.raises(ValueError, match="schema_policy_unsafe_untyped-attribute"):
        checked_requested_value("default", "lining", _row("numForm", "urn:test"))
