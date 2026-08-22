from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from former_preserve_only_value_policy import checked_requested_value, next_requested_value


THM15 = "http://schemas.microsoft.com/office/thememl/2012/main"


def _row(qname: str, attr: str) -> dict:
    return {
        "qname": qname,
        "attribute_name": attr,
        "operation_id": "office_extension.known_metadata.set_value",
        "value_kind": "attribute",
    }


def test_theme_family_name_uses_safe_string_value():
    row = _row(f"{{{THM15}}}themeFamily", "name")

    requested = next_requested_value("Office Theme", 4, row)

    assert requested == "Office Theme [semantic-edit-4]"
    assert checked_requested_value("Office Theme", requested, row) == requested


def test_theme_family_name_rejects_control_character():
    row = _row(f"{{{THM15}}}themeFamily", "name")

    with pytest.raises(ValueError, match="schema_policy_unsafe_untyped-attribute"):
        checked_requested_value("Office Theme", "Office\u0001Theme", row)
