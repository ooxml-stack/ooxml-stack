from __future__ import annotations

import sys
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from former_preserve_only_vml_stroke import FILL, STROKE, hydration_contract, is_candidate, promotion_allowed


def _row() -> dict:
    return {
        "qname": STROKE, "family": "vml_drawing", "semantic_value_kind": "direct_attr",
        "blocker_type": "semantic_value_available_pending_proof", "part_name": "word/document.xml",
    }


def test_hydrates_explicit_join_style_enum():
    node = etree.fromstring(b'<v:stroke xmlns:v="urn:schemas-microsoft-com:vml" joinstyle="miter"/>')

    assert is_candidate(_row())
    hydrated = hydration_contract(node.getroottree(), node)
    assert hydrated["before_semantic_value"] == "miter"
    assert hydrated["requested_semantic_value"] == "round"
    assert promotion_allowed(_row() | hydrated)


def test_rejects_missing_or_invalid_join_style():
    node = etree.fromstring(b'<v:stroke xmlns:v="urn:schemas-microsoft-com:vml"/>')

    hydrated = hydration_contract(node.getroottree(), node)
    assert hydrated["operation_hydration_status"] == "unsupported_mapping"


def test_hydrates_explicit_fill_boolean():
    node = etree.fromstring(b'<v:fill xmlns:v="urn:schemas-microsoft-com:vml" on="t"/>')

    hydrated = hydration_contract(node.getroottree(), node)
    assert is_candidate(_row() | {"qname": FILL})
    assert hydrated["operation_id"] == "vml.fill.set_enabled"
    assert hydrated["requested_semantic_value"] == "f"
    assert promotion_allowed((_row() | {"qname": FILL}) | hydrated)
