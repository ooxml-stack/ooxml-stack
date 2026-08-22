from __future__ import annotations

import sys
from pathlib import Path
from zipfile import ZipFile

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import former_preserve_only_hydrate_operations as hydrate
from former_preserve_only_gap_rows import _direct_kind
from former_preserve_only_hydrate_operations import O_EXTRUSIONOK, _attr_name, _vml_operation


VML = "urn:schemas-microsoft-com:vml"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W10 = "urn:schemas-microsoft-com:office:word"
W14 = "http://schemas.microsoft.com/office/word/2010/wordml"


def _node(local: str) -> etree._Element:
    return etree.fromstring(f'<v:{local} xmlns:v="{VML}"/>'.encode())


def test_vml_stroke_joinstyle_is_not_color_operation():
    assert _vml_operation(_node("stroke"), "joinstyle") == ""


def test_vml_stroke_color_uses_stroke_color_operation():
    assert _vml_operation(_node("stroke"), "color") == "vml.shape.stroke.set_color"


def test_vml_shape_fillcolor_uses_fill_operation():
    assert _vml_operation(_node("shape"), "fillcolor") == "vml.shape.fill.set_color"


def test_vml_fill_color2_waits_for_attribute_specific_operation():
    assert _vml_operation(_node("fill"), "color2") == ""


def test_unsupported_vml_attribute_keeps_candidate_name():
    node = etree.fromstring(f'<v:fill xmlns:v="{VML}" color2="red"/>'.encode())
    result = hydrate._contract({"family": "vml_drawing"}, node.getroottree(), node)

    assert result["operation_hydration_status"] == "unsupported_mapping"
    assert result["attribute_name"] == "color2"


def test_vml_image_title_uses_narrow_metadata_operation():
    title = "{urn:schemas-microsoft-com:office:office}title"
    node = etree.fromstring(f'<v:imagedata xmlns:v="{VML}" xmlns:o="urn:schemas-microsoft-com:office:office" o:title="old"/>'.encode())

    assert _vml_operation(node, title) == "vml.image.metadata.set_title"


def test_empty_vml_path_uses_path_metadata_operation():
    node = _node("path")

    assert _attr_name({"semantic_value_kind": "direct_vml_path_metadata"}, node) == O_EXTRUSIONOK
    assert _vml_operation(node, O_EXTRUSIONOK) == "vml.path.metadata.set_value"


def test_empty_vml_path_is_not_hydrated_as_explicit_change():
    node = _node("path")

    result = hydrate._attr_contract({}, node.getroottree(), node, O_EXTRUSIONOK, "vml.path.metadata.set_value")
    assert result["operation_hydration_status"] == "unsupported_mapping"


@pytest.mark.parametrize("attribute_name", ["arrowok", "fillok", "gradientshapeok", "textpathok"])
def test_typed_vml_path_boolean_uses_path_operation(attribute_name):
    assert _vml_operation(_node("path"), attribute_name) == "vml.path.metadata.set_value"


@pytest.mark.parametrize(("local", "operation"), [
    ("shadow", "vml.shadow.set_enabled"),
    ("textpath", "vml.textpath.set_enabled"),
])
def test_typed_vml_on_boolean_uses_narrow_operation(local, operation):
    assert _vml_operation(_node(local), "on") == operation


def test_vml_formula_eqn_uses_formula_operation():
    node = etree.fromstring(f'<v:f xmlns:v="{VML}" eqn="val #0"/>'.encode())

    assert _attr_name({}, node) == "eqn"
    assert _vml_operation(node, "eqn") == "vml.formula.eqn.set_value"


def test_gap_classifier_models_empty_vml_path_metadata():
    node = _node("path")
    row = {"family": "vml_drawing", "qname": f"{{{VML}}}path"}

    assert _direct_kind(node, row) == "direct_vml_path_metadata"


def test_hydrate_requires_local_gap_cache(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(hydrate, "LEDGER", tmp_path / "missing-gap-ledger.jsonl")

    assert hydrate.main() == 2
    assert "make campaign-gap-ledger" in capsys.readouterr().out


def test_hydrate_empty_anchorlock_presence_row(tmp_path: Path, monkeypatch):
    package = tmp_path / "anchor.docx"
    xml = (
        f'<w:document xmlns:w="{W_NS}" xmlns:v="{VML}" xmlns:w10="{W10}">'
        "<w:body><w:p><w:r><w:pict><v:shape><w10:anchorlock/></v:shape></w:pict></w:r></w:p></w:body>"
        "</w:document>"
    )
    with ZipFile(package, "w") as zf:
        zf.writestr("word/document.xml", xml)
    monkeypatch.setattr(hydrate, "CORPUS", tmp_path)
    row = {
        "input_file": "anchor.docx",
        "part_name": "word/document.xml",
        "selector": "/w:document/w:body/w:p/w:r/w:pict/v:shape/w10:anchorlock",
        "family": "legacy_office_drawing",
        "qname": f"{{{W10}}}anchorlock",
        "semantic_value_kind": "no_descendant_value",
        "blocker_type": "needs_family_model",
    }

    hydrated = hydrate._hydrate(row, {}, {})

    assert hydrated["operation_hydration_status"] == "hydrated"
    assert hydrated["operation_id"] == "legacy_office_drawing.anchorlock.presence.set_enabled"
    assert hydrated["value_kind"] == "presence"
    assert hydrated["before_semantic_value"] == "true"
    assert hydrated["requested_semantic_value"] == "false"


def test_hydrate_empty_text_outline_no_fill_presence(tmp_path: Path, monkeypatch):
    package = tmp_path / "outline.docx"
    xml = f'<w:document xmlns:w="{W_NS}" xmlns:w14="{W14}"><w:body><w:p><w:r><w:rPr><w14:textOutline><w14:noFill/></w14:textOutline></w:rPr></w:r></w:p></w:body></w:document>'
    with ZipFile(package, "w") as archive:
        archive.writestr("word/document.xml", xml)
    monkeypatch.setattr(hydrate, "CORPUS", tmp_path)
    row = {"input_file": "outline.docx", "part_name": "word/document.xml", "selector": "/w:document/w:body/w:p/w:r/w:rPr/w14:textOutline/w14:noFill", "family": "office_extension", "qname": f"{{{W14}}}noFill", "semantic_value_kind": "no_descendant_value", "blocker_type": "needs_family_model"}

    hydrated = hydrate._hydrate(row, {}, {})

    assert hydrated["operation_hydration_status"] == "hydrated"
    assert hydrated["operation_id"] == "office_extension.no_fill.presence.set_enabled"
    assert hydrated["requested_semantic_value"] == "false"


def test_hydrate_empty_text_outline_bevel_presence(tmp_path: Path, monkeypatch):
    package = tmp_path / "outline.docx"
    xml = f'<w:document xmlns:w="{W_NS}" xmlns:w14="{W14}"><w:body><w:p><w:r><w:rPr><w14:textOutline><w14:bevel/></w14:textOutline></w:rPr></w:r></w:p></w:body></w:document>'
    with ZipFile(package, "w") as archive:
        archive.writestr("word/document.xml", xml)
    monkeypatch.setattr(hydrate, "CORPUS", tmp_path)
    row = {"input_file": "outline.docx", "part_name": "word/document.xml", "selector": "/w:document/w:body/w:p/w:r/w:rPr/w14:textOutline/w14:bevel", "family": "office_extension", "qname": f"{{{W14}}}bevel", "semantic_value_kind": "no_descendant_value", "blocker_type": "needs_family_model"}

    hydrated = hydrate._hydrate(row, {}, {})

    assert hydrated["operation_hydration_status"] == "hydrated"
    assert hydrated["operation_id"] == "office_extension.text_outline.bevel.presence.set_enabled"
    assert hydrated["requested_semantic_value"] == "false"


def test_hydrates_only_exact_schema_numeric_leaf_qnames(tmp_path: Path, monkeypatch):
    package = tmp_path / "numeric.docx"
    wp14 = "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing"
    with ZipFile(package, "w") as archive:
        archive.writestr("word/document.xml", f'<root xmlns:wp14="{wp14}"><wp14:sizeRelH><wp14:pctWidth>50000</wp14:pctWidth></wp14:sizeRelH><wp14:pctPosVOffset>2300</wp14:pctPosVOffset><wp14:other>3</wp14:other></root>')
    monkeypatch.setattr(hydrate, "CORPUS", tmp_path)
    base = {"input_file": "numeric.docx", "part_name": "word/document.xml", "family": "office_extension", "semantic_value_kind": "direct_text", "blocker_type": "semantic_value_available_pending_proof"}
    width = hydrate._hydrate(base | {"selector": "/root/wp14:sizeRelH/wp14:pctWidth", "qname": f"{{{wp14}}}pctWidth"}, {}, {})
    other = hydrate._hydrate(base | {"selector": "/root/wp14:other", "qname": f"{{{wp14}}}other"}, {}, {})
    position = hydrate._hydrate(base | {"selector": "/root/wp14:pctPosVOffset", "qname": f"{{{wp14}}}pctPosVOffset"}, {}, {})
    assert width["operation_id"] == "office_extension.relative_size.set_percentage"
    assert width["before_semantic_value"] == "50000"
    assert position["operation_id"] == "office_extension.position_percentage_offset.set_percentage"
    assert position["before_semantic_value"] == "2300"
    assert other["operation_hydration_status"] == "unsupported_mapping"


def test_hydrates_only_direct_explicit_media_trim_end(tmp_path: Path, monkeypatch):
    package = tmp_path / "trim.pptx"
    p14 = "http://schemas.microsoft.com/office/powerpoint/2010/main"
    with ZipFile(package, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", f'<root xmlns:p14="{p14}"><p14:media><p14:trim end="5652.700195"/></p14:media></root>')
    monkeypatch.setattr(hydrate, "CORPUS", tmp_path)
    base = {"input_file": "trim.pptx", "part_name": "ppt/slides/slide1.xml", "family": "office_extension", "blocker_type": "semantic_value_available_pending_proof"}
    direct = hydrate._hydrate(base | {"selector": "/root/p14:media/p14:trim", "qname": f"{{{p14}}}trim", "semantic_value_kind": "direct_attr"}, {}, {})
    parent = hydrate._hydrate(base | {"selector": "/root/p14:media", "qname": f"{{{p14}}}media", "semantic_value_kind": "descendant_attr"}, {}, {})
    assert direct["operation_id"] == "office_extension.media_trim.set_end"
    assert direct["before_semantic_value"] == "5652.700195"
    assert parent["operation_id"] == "office_extension.known_metadata.set_value"


def test_hydrates_only_empty_pan_under_transition(tmp_path: Path, monkeypatch):
    package = tmp_path / "pan.pptx"
    p = "http://schemas.openxmlformats.org/presentationml/2006/main"
    p14 = "http://schemas.microsoft.com/office/powerpoint/2010/main"
    with ZipFile(package, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", f'<p:sld xmlns:p="{p}" xmlns:p14="{p14}"><p:transition><p14:pan/></p:transition></p:sld>')
    monkeypatch.setattr(hydrate, "CORPUS", tmp_path)
    row = {"input_file": "pan.pptx", "part_name": "ppt/slides/slide1.xml", "family": "office_extension", "semantic_value_kind": "no_descendant_value", "blocker_type": "needs_family_model", "selector": "/p:sld/p:transition/p14:pan", "qname": f"{{{p14}}}pan"}
    hydrated = hydrate._hydrate(row, {}, {})
    assert hydrated["operation_id"] == "office_extension.transition_pan.presence.set_enabled"
    assert hydrated["requested_semantic_value"] == "false"


def test_hydrates_only_empty_prism_under_transition(tmp_path: Path, monkeypatch):
    package = tmp_path / "prism.pptx"
    p = "http://schemas.openxmlformats.org/presentationml/2006/main"
    p14 = "http://schemas.microsoft.com/office/powerpoint/2010/main"
    with ZipFile(package, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", f'<p:sld xmlns:p="{p}" xmlns:p14="{p14}"><p:transition><p14:prism/></p:transition></p:sld>')
    monkeypatch.setattr(hydrate, "CORPUS", tmp_path)
    row = {"input_file": "prism.pptx", "part_name": "ppt/slides/slide1.xml", "family": "office_extension", "semantic_value_kind": "no_descendant_value", "blocker_type": "needs_family_model", "selector": "/p:sld/p:transition/p14:prism", "qname": f"{{{p14}}}prism"}
    hydrated = hydrate._hydrate(row, {}, {})
    assert hydrated["operation_id"] == "office_extension.transition_prism.presence.set_enabled"
    assert hydrated["requested_semantic_value"] == "false"


@pytest.mark.parametrize("local_name", ["ripple", "flythrough", "shred", "reveal"])
def test_hydrates_empty_transition_effect(tmp_path: Path, monkeypatch, local_name: str):
    package = tmp_path / f"{local_name}.pptx"
    p = "http://schemas.openxmlformats.org/presentationml/2006/main"
    p14 = "http://schemas.microsoft.com/office/powerpoint/2010/main"
    with ZipFile(package, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", f'<p:sld xmlns:p="{p}" xmlns:p14="{p14}"><p:transition><p14:{local_name}/></p:transition></p:sld>')
    monkeypatch.setattr(hydrate, "CORPUS", tmp_path)
    row = {"input_file": package.name, "part_name": "ppt/slides/slide1.xml", "family": "office_extension", "semantic_value_kind": "no_descendant_value", "blocker_type": "needs_family_model", "selector": f"/p:sld/p:transition/p14:{local_name}", "qname": f"{{{p14}}}{local_name}"}
    hydrated = hydrate._hydrate(row, {}, {})
    assert hydrated["operation_id"] == f"office_extension.transition_{local_name}.presence.set_enabled"
    assert hydrated["requested_semantic_value"] == "false"


def test_hydrates_exact_empty_cover_page_field(tmp_path: Path, monkeypatch):
    package = tmp_path / "cover.docx"
    cp = "http://schemas.microsoft.com/office/2006/coverPageProps"
    with ZipFile(package, "w") as archive:
        archive.writestr("customXml/item1.xml", f'<cp:CoverPageProperties xmlns:cp="{cp}"><cp:Abstract/></cp:CoverPageProperties>')
    monkeypatch.setattr(hydrate, "CORPUS", tmp_path)
    row = {"input_file": package.name, "part_name": "customXml/item1.xml", "family": "office_extension", "semantic_value_kind": "no_descendant_value", "blocker_type": "needs_family_model", "selector": "/cp:CoverPageProperties/cp:Abstract", "qname": f"{{{cp}}}Abstract"}
    hydrated = hydrate._hydrate(row, {}, {})
    assert hydrated["operation_id"] == "custom_xml.element.set_text"
    assert hydrated["requested_semantic_value"] == "Document summary"


@pytest.mark.parametrize("xml", ["<cp:Abstract>existing</cp:Abstract>", "<cp:Abstract code='x'/>", "<cp:Other><cp:Abstract/></cp:Other>"])
def test_rejects_non_exact_cover_page_field(tmp_path: Path, monkeypatch, xml: str):
    package = tmp_path / "cover.docx"
    cp = "http://schemas.microsoft.com/office/2006/coverPageProps"
    with ZipFile(package, "w") as archive:
        archive.writestr("customXml/item1.xml", f'<cp:CoverPageProperties xmlns:cp="{cp}">{xml}</cp:CoverPageProperties>')
    monkeypatch.setattr(hydrate, "CORPUS", tmp_path)
    selector = "/cp:CoverPageProperties/cp:Other/cp:Abstract" if "Other" in xml else "/cp:CoverPageProperties/cp:Abstract"
    row = {"input_file": package.name, "part_name": "customXml/item1.xml", "family": "office_extension", "semantic_value_kind": "no_descendant_value", "blocker_type": "needs_family_model", "selector": selector, "qname": f"{{{cp}}}Abstract"}
    hydrated = hydrate._hydrate(row, {}, {})
    assert hydrated["operation_hydration_status"] == "unsupported_mapping"


def test_hydrates_exact_empty_film_grain_effect(tmp_path: Path, monkeypatch):
    package = tmp_path / "film-grain.pptx"
    a14 = "http://schemas.microsoft.com/office/drawing/2010/main"
    with ZipFile(package, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", f'<root xmlns:a14="{a14}"><a14:imgEffect><a14:artisticFilmGrain/></a14:imgEffect></root>')
    monkeypatch.setattr(hydrate, "CORPUS", tmp_path)
    row = {"input_file": package.name, "part_name": "ppt/slides/slide1.xml", "family": "office_extension", "semantic_value_kind": "no_descendant_value", "blocker_type": "needs_family_model", "selector": "/root/a14:imgEffect/a14:artisticFilmGrain", "qname": f"{{{a14}}}artisticFilmGrain"}
    hydrated = hydrate._hydrate(row, {}, {})
    assert hydrated["operation_id"] == "office_extension.picture_effect.film_grain.presence.set_enabled"
    assert hydrated["requested_semantic_value"] == "false"


def test_hydrates_exact_empty_artistic_blur_effect(tmp_path: Path, monkeypatch):
    package = tmp_path / "artistic-blur.pptx"
    a14 = "http://schemas.microsoft.com/office/drawing/2010/main"
    with ZipFile(package, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", f'<root xmlns:a14="{a14}"><a14:imgEffect><a14:artisticBlur/></a14:imgEffect></root>')
    monkeypatch.setattr(hydrate, "CORPUS", tmp_path)
    row = {"input_file": package.name, "part_name": "ppt/slides/slide1.xml", "family": "office_extension", "semantic_value_kind": "no_descendant_value", "blocker_type": "needs_family_model", "selector": "/root/a14:imgEffect/a14:artisticBlur", "qname": f"{{{a14}}}artisticBlur"}
    hydrated = hydrate._hydrate(row, {}, {})
    assert hydrated["operation_id"] == "office_extension.picture_effect.artistic_blur.presence.set_enabled"
    assert hydrated["requested_semantic_value"] == "false"


@pytest.mark.parametrize("local,operation", [("lit", "math.run_property.literal.presence.set_enabled"), ("nor", "math.run_property.normal_text.presence.set_enabled")])
def test_hydrates_exact_empty_math_run_property(tmp_path: Path, monkeypatch, local: str, operation: str):
    package = tmp_path / "math.docx"
    m = "http://schemas.openxmlformats.org/officeDocument/2006/math"
    with ZipFile(package, "w") as archive:
        archive.writestr("word/document.xml", f'<root xmlns:m="{m}"><m:rPr><m:{local}/></m:rPr></root>')
    monkeypatch.setattr(hydrate, "CORPUS", tmp_path)
    row = {"input_file": package.name, "part_name": "word/document.xml", "family": "math_object", "semantic_value_kind": "no_descendant_value", "blocker_type": "needs_family_model", "selector": f"/root/m:rPr/m:{local}", "qname": f"{{{m}}}{local}"}
    hydrated = hydrate._hydrate(row, {}, {})
    assert hydrated["operation_id"] == operation
    assert hydrated["requested_semantic_value"] == "false"


def test_hydrates_exact_empty_contextual_alternates(tmp_path: Path, monkeypatch):
    package = tmp_path / "contextual.docx"
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    w14 = "http://schemas.microsoft.com/office/word/2010/wordml"
    with ZipFile(package, "w") as archive:
        archive.writestr("word/numbering.xml", f'<root xmlns:w="{w}" xmlns:w14="{w14}"><w:rPr><w14:cntxtAlts/></w:rPr></root>')
    monkeypatch.setattr(hydrate, "CORPUS", tmp_path)
    row = {"input_file": package.name, "part_name": "word/numbering.xml", "family": "office_extension", "semantic_value_kind": "no_descendant_value", "blocker_type": "needs_family_model", "selector": "/root/w:rPr/w14:cntxtAlts", "qname": f"{{{w14}}}cntxtAlts"}
    hydrated = hydrate._hydrate(row, {}, {})
    assert hydrated["operation_id"] == "office_extension.contextual_alternates.presence.set_enabled"
    assert hydrated["requested_semantic_value"] == "false"
