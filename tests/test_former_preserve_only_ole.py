from __future__ import annotations

import sys
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from former_preserve_only_ole import LOCKED_FIELD, hydration_contract, is_candidate, promotion_allowed


def _row() -> dict:
    return {
        "qname": LOCKED_FIELD, "family": "legacy_office_drawing",
        "semantic_value_kind": "direct_text", "blocker_type": "semantic_value_available_pending_proof",
        "part_name": "word/document.xml",
    }


def test_hydrates_only_explicit_false_under_ole_object():
    root = etree.fromstring(b'<o:OLEObject xmlns:o="urn:schemas-microsoft-com:office:office"><o:LockedField>false</o:LockedField></o:OLEObject>')

    assert is_candidate(_row())
    hydrated = hydration_contract(root.getroottree(), root[0])
    assert hydrated["before_semantic_value"] == "false"
    assert hydrated["requested_semantic_value"] == "true"
    assert promotion_allowed(_row() | hydrated)


def test_rejects_implicit_or_wrong_parent_locked_field():
    root = etree.fromstring(b'<o:Other xmlns:o="urn:schemas-microsoft-com:office:office"><o:LockedField/></o:Other>')

    hydrated = hydration_contract(root.getroottree(), root[0])
    assert hydrated["operation_hydration_status"] == "unsupported_mapping"
