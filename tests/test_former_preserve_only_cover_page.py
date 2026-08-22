from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from former_preserve_only_promote_hydrated import _eligible
from former_preserve_only_cover_page import hydration_contract, is_candidate
from lxml import etree


def test_custom_xml_eligibility_allows_only_exact_cover_page_contract(monkeypatch):
    cp = "http://schemas.microsoft.com/office/2006/coverPageProps"
    row = {
        "row_id": "cover",
        "source_row_id": "cover",
        "package_id": "same",
        "part_name": "customXml/item1.xml",
        "qname": f"{{{cp}}}Abstract",
        "operation_id": "custom_xml.element.set_text",
        "operation_hydration_status": "hydrated",
        "value_kind": "text",
        "before_semantic_value": "",
        "requested_semantic_value": "Document summary",
        "semantic_contract_version": "cover-page-properties-empty-string-v1",
    }
    args = type("Args", (), {"family": "", "operation_id": "", "package_id": "", "qname": "", "attribute_name": "", "max_package_mb": 5.0})()
    monkeypatch.setattr("former_preserve_only_promote_hydrated._size_mb", lambda candidate: 1.0)
    assert _eligible(row, args, set(), set())
    assert not _eligible(row | {"qname": "{urn:other}Abstract"}, args, set(), set())
    assert not _eligible(row | {"requested_semantic_value": "arbitrary"}, args, set(), set())


def test_publish_date_contract_requires_explicit_iso_text():
    cp = "http://schemas.microsoft.com/office/2006/coverPageProps"
    root = etree.fromstring(f'<cp:CoverPageProperties xmlns:cp="{cp}"><cp:PublishDate>2013-02-22T00:00:00</cp:PublishDate></cp:CoverPageProperties>')
    tree = root.getroottree()
    row = {"qname": f"{{{cp}}}PublishDate", "family": "office_extension", "semantic_value_kind": "direct_text", "blocker_type": "semantic_value_available_pending_proof", "part_name": "customXml/item1.xml"}

    assert is_candidate(row)
    hydrated = hydration_contract(row, tree, root[0])
    assert hydrated["before_semantic_value"] == "2013-02-22T00:00:00"
    assert hydrated["requested_semantic_value"] == "2013-02-23T00:00:00"


def test_publish_date_contract_rejects_non_iso_text():
    cp = "http://schemas.microsoft.com/office/2006/coverPageProps"
    root = etree.fromstring(f'<cp:CoverPageProperties xmlns:cp="{cp}"><cp:PublishDate>yesterday</cp:PublishDate></cp:CoverPageProperties>')
    row = {"qname": f"{{{cp}}}PublishDate"}

    hydrated = hydration_contract(row, root.getroottree(), root[0])
    assert hydrated["operation_hydration_status"] == "unsupported_mapping"
