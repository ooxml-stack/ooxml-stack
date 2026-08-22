from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from former_preserve_only_promote_hydrated import _read_value
from vml_text_value import visible_vml_text

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
V_NS = "urn:schemas-microsoft-com:vml"
W10_NS = "urn:schemas-microsoft-com:office:word"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"


def test_visible_vml_text_ignores_field_instructions() -> None:
    xml = f"""
    <v:textbox xmlns:v="{V_NS}" xmlns:w="{W_NS}">
      <w:p>
        <w:r><w:instrText>REF Title</w:instrText></w:r>
        <w:r><w:t>Hello</w:t></w:r>
        <w:r><w:t> world</w:t></w:r>
      </w:p>
    </v:textbox>
    """
    node = etree.fromstring(xml.encode())

    assert visible_vml_text(node) == "Hello world"


def test_hydrated_vml_text_read_value_uses_visible_text(tmp_path: Path) -> None:
    path = tmp_path / "demo.docx"
    part = "word/header1.xml"
    xml = f"""
    <w:hdr xmlns:w="{W_NS}" xmlns:v="{V_NS}">
      <v:textbox>
        <w:p>
          <w:r><w:instrText>REF Title</w:instrText></w:r>
          <w:r><w:t>Visible</w:t></w:r>
        </w:p>
      </v:textbox>
    </w:hdr>
    """
    with ZipFile(path, "w") as package:
        package.writestr(part, xml)
    row = {
        "attribute_name": "",
        "operation_id": "vml.shape.text.set",
        "operation_target_selector": "/w:hdr/v:textbox",
        "part_name": part,
    }

    assert _read_value(path, row) == "Visible"


def test_anchorlock_presence_read_value_allows_absent_after_delete(tmp_path: Path) -> None:
    path = tmp_path / "demo.docx"
    part = "word/document.xml"
    before = (
        f'<w:document xmlns:w="{W_NS}" xmlns:v="{V_NS}" xmlns:w10="{W10_NS}">'
        "<w:body><w:p><w:r><w:pict><v:shape><w10:anchorlock/></v:shape></w:pict></w:r></w:p></w:body>"
        "</w:document>"
    )
    after = before.replace("<w10:anchorlock/>", "")
    row = {
        "attribute_name": "",
        "operation_id": "legacy_office_drawing.anchorlock.presence.set_enabled",
        "operation_target_selector": "/w:document/w:body/w:p/w:r/w:pict/v:shape/w10:anchorlock",
        "part_name": part,
    }
    with ZipFile(path, "w") as package:
        package.writestr(part, before)
    assert _read_value(path, row) == "true"

    with ZipFile(path, "w") as package:
        package.writestr(part, after)
    assert _read_value(path, row) == "false"


def test_no_fill_presence_read_value_allows_absent_after_delete(tmp_path: Path) -> None:
    path = tmp_path / "demo.docx"
    part = "word/document.xml"
    before = f'<w:document xmlns:w="{W_NS}" xmlns:w14="{W14_NS}"><w:body><w:p><w:r><w:rPr><w14:textOutline><w14:noFill/></w14:textOutline></w:rPr></w:r></w:p></w:body></w:document>'
    row = {"attribute_name": "", "operation_id": "office_extension.no_fill.presence.set_enabled", "operation_target_selector": "/w:document/w:body/w:p/w:r/w:rPr/w14:textOutline/w14:noFill", "part_name": part}
    with ZipFile(path, "w") as package:
        package.writestr(part, before)
    assert _read_value(path, row) == "true"
    with ZipFile(path, "w") as package:
        package.writestr(part, before.replace("<w14:noFill/>", ""))
    assert _read_value(path, row) == "false"


def test_bevel_presence_read_value_allows_absent_after_delete(tmp_path: Path) -> None:
    path = tmp_path / "demo.docx"
    part = "word/document.xml"
    before = f'<w:document xmlns:w="{W_NS}" xmlns:w14="{W14_NS}"><w:body><w:p><w:r><w:rPr><w14:textOutline><w14:bevel/></w14:textOutline></w:rPr></w:r></w:p></w:body></w:document>'
    row = {"attribute_name": "", "operation_id": "office_extension.text_outline.bevel.presence.set_enabled", "operation_target_selector": "/w:document/w:body/w:p/w:r/w:rPr/w14:textOutline/w14:bevel", "part_name": part}
    with ZipFile(path, "w") as package:
        package.writestr(part, before)
    assert _read_value(path, row) == "true"
    with ZipFile(path, "w") as package:
        package.writestr(part, before.replace("<w14:bevel/>", ""))
    assert _read_value(path, row) == "false"
